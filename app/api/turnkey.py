from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import json
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from cryptography.exceptions import InvalidKey
import binascii
from typing import Tuple, Dict
import os
import time
import httpx
from ..config.settings import TURNKEY_API_PUBLIC_KEY, TURNKEY_API_PRIVATE_KEY, TURNKEY_ORGANIZATION_ID

router = APIRouter()

class InitOTPRequest(BaseModel):
    email: EmailStr

class InitOTPResponse(BaseModel):
    success: bool
    message: str
    otp_id: str | None = None

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str
    otp_id: str
    target_public_key: str

class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    user_id: str
    api_key_id: str
    credential_bundle: str

def int_to_bytes(value: int, length: int = 32) -> bytes:
    """Convert integer to bytes with fixed length."""
    return value.to_bytes(length, byteorder='big')

def bytes_to_int(value: bytes) -> int:
    """Convert bytes to integer."""
    return int.from_bytes(value, byteorder='big')

def hex_to_bytes(hex_str: str) -> bytes:
    """Convert hex string to bytes, handling odd-length strings."""
    hex_str = hex_str.strip()
    if len(hex_str) % 2:
        hex_str = '0' + hex_str
    return bytes.fromhex(hex_str)

def bytes_to_hex(bytes_val: bytes) -> str:
    """Convert bytes to hex string."""
    return binascii.hexlify(bytes_val).decode('ascii')

def base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url without padding."""
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')

def encode_der_signature(r: int, s: int) -> bytes:
    """Encode signature in DER format."""
    def encode_int(x: int) -> bytes:
        x_bytes = int_to_bytes(x, 32)
        # Remove leading zeros
        x_bytes = x_bytes.lstrip(b'\x00')
        # Add back one zero if highest bit is set
        if x_bytes[0] & 0x80:
            x_bytes = b'\x00' + x_bytes
        return b'\x02' + bytes([len(x_bytes)]) + x_bytes

    r_encoded = encode_int(r)
    s_encoded = encode_int(s)
    
    total_len = len(r_encoded) + len(s_encoded)
    return b'\x30' + bytes([total_len]) + r_encoded + s_encoded

def import_api_key(private_key_hex: str, public_key_hex: str) -> Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """Import API key and create key pair."""
    jwk = convert_turnkey_api_key_to_jwk({
        'uncompressedPrivateKeyHex': private_key_hex,
        'compressedPublicKeyHex': public_key_hex
    })
    
    private_key_bytes = base64.urlsafe_b64decode(jwk['d'] + '=' * (-len(jwk['d']) % 4))
    private_value = bytes_to_int(private_key_bytes)
    
    private_key = ec.derive_private_key(private_value, ec.SECP256R1())
    public_key = private_key.public_key()
    
    return private_key, public_key

def convert_turnkey_api_key_to_jwk(input_data: Dict[str, str]) -> Dict[str, str]:
    """Convert Turnkey API key to JWK format."""
    private_key_bytes = hex_to_bytes(input_data['uncompressedPrivateKeyHex'])
    public_key_bytes = hex_to_bytes(input_data['compressedPublicKeyHex'])
    
    # Create EC key from private key bytes
    private_value = bytes_to_int(private_key_bytes)
    private_key = ec.derive_private_key(private_value, ec.SECP256R1())
    public_key = private_key.public_key()
    
    # Get public point coordinates
    public_numbers = public_key.public_numbers()
    
    return {
        'kty': 'EC',
        'crv': 'P-256',
        'x': base64url_encode(int_to_bytes(public_numbers.x)),
        'y': base64url_encode(int_to_bytes(public_numbers.y)),
        'd': base64url_encode(private_key_bytes),
        'ext': 'true'
    }

async def generate_api_key_stamp(json_body: str, private_key: str, public_key: str) -> str:
    """Generate API key stamp for Turnkey authentication."""
    try:
        # Import the key pair
        private_key_obj, _ = import_api_key(private_key, public_key)
        
        # Sign the message
        signature_bytes = private_key_obj.sign(
            json_body.encode(),
            ec.ECDSA(hashes.SHA256())
        )
        
        # Extract r and s from the signature
        r, s = decode_dss_signature(signature_bytes)
        
        # Create DER signature
        der_signature = encode_der_signature(r, s)
        
        # Create stamp object
        stamp = {
            'publicKey': public_key,
            'signature': bytes_to_hex(der_signature),
            'scheme': 'SIGNATURE_SCHEME_TK_API_P256'
        }
        
        # Convert to base64url
        stamp_json = json.dumps(stamp)
        stamp_base64 = base64url_encode(stamp_json.encode())
        
        return stamp_base64
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate stamp: {str(e)}")

def decode_dss_signature(signature: bytes) -> Tuple[int, int]:
    """Decode signature to get r and s values."""
    # Find r and s within DER structure
    if len(signature) < 8 or signature[0] != 0x30:
        raise ValueError("Invalid signature format")
    
    # Skip sequence header
    pos = 2
    # Get r
    if signature[pos] != 0x02:
        raise ValueError("Invalid r marker")
    r_len = signature[pos + 1]
    pos += 2
    r = bytes_to_int(signature[pos:pos + r_len])
    pos += r_len
    
    # Get s
    if signature[pos] != 0x02:
        raise ValueError("Invalid s marker")
    s_len = signature[pos + 1]
    pos += 2
    s = bytes_to_int(signature[pos:pos + s_len])
    
    return r, s

async def get_sub_org_id(email: str) -> str:
    """Get sub-organization ID for a given email."""
    request_body = {
        "organizationId": TURNKEY_ORGANIZATION_ID,  # This is the parent org ID
        "filterType": "EMAIL",
        "filterValue": email
    }
    
    json_body = json.dumps(request_body)
    stamp = await generate_api_key_stamp(json_body, TURNKEY_API_PRIVATE_KEY, TURNKEY_API_PUBLIC_KEY)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.turnkey.com/public/v1/query/list_verified_suborgs",
            content=json_body,
            headers={
                "X-Stamp": stamp,
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to list sub orgs: {response.text}"
            )
        
        response_data = response.json()
        organization_ids = response_data.get("organizationIds", [])
        
        if not organization_ids:
            # create a new sub org
            organization_id = await create_sub_org(email)
            return organization_id
        
        return organization_ids[0]

async def create_sub_org(email: str) -> str:
    """Create a new sub-organization for a given email."""
    timpestamp = str(int(time.time() * 1000))
    request_body = {
        "type": "ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
        "timestampMs": timpestamp,
        "organizationId": TURNKEY_ORGANIZATION_ID,
        "parameters": {
          "subOrganizationName": email,
          "rootUsers": [
            {
              "userName": email,
              "userEmail": email,
              "apiKeys": [],
              "authenticators": [],
              "oauthProviders": []
            }
          ],
          "rootQuorumThreshold": 1,
          "wallet": {
            "walletName": email,
            "accounts": [
              {
                "pathFormat": "PATH_FORMAT_BIP32",
                "path": "m/44'/501'/0'/0'",
                "curve": "CURVE_ED25519",
                "addressFormat": "ADDRESS_FORMAT_SOLANA",
              }
            ]
          }
        }
      }

    json_body = json.dumps(request_body)
    stamp = await generate_api_key_stamp(json_body, TURNKEY_API_PRIVATE_KEY, TURNKEY_API_PUBLIC_KEY)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.turnkey.com/public/v1/submit/create_sub_organization",
            content=json_body,
            headers={
                "X-Stamp": stamp,
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to create sub org: {response.text}"
            )
        
        response_data = response.json()
        '''
          return createSubOrgResponse['activity']['result']
      ['createSubOrganizationResultV7']['subOrganizationId'] as String;
        '''
        organization_id = response_data['activity']['result']['createSubOrganizationResultV7']['subOrganizationId']
        print("new sub org created and its id", organization_id)

        if not organization_id:
            raise Exception('Failed to create sub-organization')

        return organization_id

@router.post("/initotp", response_model=InitOTPResponse)
async def init_otp(request: InitOTPRequest):
    """
    Initialize OTP for turnkey authentication.
    """
    try:
        # First get the sub-organization ID for the email
        sub_org_id = await get_sub_org_id(request.email)
        
        # Prepare request body with sub-org ID
        request_body = {
            "type": "ACTIVITY_TYPE_INIT_OTP_AUTH",
            "timestampMs": str(int(time.time() * 1000)),
            "organizationId": sub_org_id,  # Use sub-org ID instead of parent org ID
            "parameters": {
                "otpType": "OTP_TYPE_EMAIL",
                "contact": request.email,
            }
        }
        
        # Convert request body to JSON string
        json_body = json.dumps(request_body)
        
        # Generate API key stamp
        stamp = await generate_api_key_stamp(json_body, TURNKEY_API_PRIVATE_KEY, TURNKEY_API_PUBLIC_KEY)
        
        # Make request to Turnkey API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.turnkey.com/public/v1/submit/init_otp_auth",
                content=json_body,
                headers={
                    "X-Stamp": stamp,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Turnkey API error: {response.text}"
                )
            
            response_data = response.json()
            print(response_data)
            otp_id = response_data.get("activity", {}).get("result", {}).get("initOtpAuthResult", {}).get("otpId")
            
            if not otp_id:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get OTP ID from response"
                )
            
            return {
                "success": True,
                "message": "OTP initialization successful",
                "otp_id": otp_id
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verifyotp", response_model=VerifyOTPResponse)
async def verify_otp(request: VerifyOTPRequest):
    """
    Verify OTP for turnkey authentication.
    """
    try:
        # First get the sub-organization ID for the email
        sub_org_id = await get_sub_org_id(request.email)
        
        # Prepare request body
        request_body = {
            "type": "ACTIVITY_TYPE_OTP_AUTH",
            "timestampMs": str(int(time.time() * 1000)),
            "organizationId": sub_org_id,
            "parameters": {
                "otpId": request.otp_id,
                "otpCode": request.otp,
                "targetPublicKey": request.target_public_key,
                "apiKeyName": f"OTP Auth - {time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            }
        }
        
        # Convert request body to JSON string
        json_body = json.dumps(request_body)
        
        # Generate API key stamp
        stamp = await generate_api_key_stamp(json_body, TURNKEY_API_PRIVATE_KEY, TURNKEY_API_PUBLIC_KEY)
        
        # Make request to Turnkey API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.turnkey.com/public/v1/submit/otp_auth",
                content=json_body,
                headers={
                    "X-Stamp": stamp,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Turnkey API error: {response.text}"
                )
            
            response_data = response.json()
            print("Verify OTP Response:", response_data)
            
            # Extract user_id and api_key_id from response
            result = response_data.get("activity", {}).get("result", {}).get("otpAuthResult", {})
            user_id = result.get("userId")
            api_key_id = result.get("apiKeyId")
            credential_bundle = result.get("credentialBundle")
            
            if not all([user_id, api_key_id, credential_bundle]):
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get authentication details from response"
                )
            
            return {
                "success": True,
                "message": "OTP verification successful",
                "user_id": user_id,
                "api_key_id": api_key_id,
                "credential_bundle": credential_bundle
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 


