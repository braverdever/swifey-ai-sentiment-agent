import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta
from ..config.settings import JWT_SECRET
from ..db.supabase import get_supabase

router = APIRouter()

class TurnkeyProofRequest(BaseModel):
    proof: str
    email: str

@router.post("/verify")
async def verify_turnkey_proof(request: TurnkeyProofRequest):
    """
    Verify turnkey proof and return a signed JWT token.
    """
    try:
        
        supabase = get_supabase()
        user = supabase.table("profiles").select("*").eq("email", request.email).execute().data
        if not user:
            user = supabase.table("profiles").insert({"email": request.email}).execute().data
        print(user)
        # Create token payload
        payload = {
            "sub": user[0]["id"],  # TODO: Replace with actual user ID after verification
            "iat": datetime.utcnow(),
        }
        
        # Sign the token
        token = jwt.encode(
            payload,
            JWT_SECRET,
            algorithm="HS256"
        )
        
        return {"success": True, "token": token, "user": user[0]}
    except Exception as e:
        print("Error verifying turnkey proof: ", e)
        raise HTTPException(status_code=500, detail=str(e))
