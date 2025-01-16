from fastapi import Request, HTTPException, Depends
from supabase import create_client, Client
from ..config.settings import SUPABASE_URL, SUPABASE_KEY, JWT_SECRET
from jose import jwt
from typing import Optional

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def auth_middleware(request: Request):
    """
    Middleware to handle authentication using Supabase JWT tokens.
    
    Args:
        request (Request): The incoming FastAPI request
        
    Raises:
        HTTPException: If authentication fails
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        raise HTTPException(status_code=401, detail="No authorization header")
    
    try:
        # Extract the JWT token
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        # Return the user_id
        return payload["sub"]

        
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token format")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token format")
    

async def verify_app_token(request: Request) -> str:
    """
    Verify access token from Authorization header.
    Returns the user_id if valid.
    Raises HTTPException if invalid.
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        raise HTTPException(status_code=401, detail="No authorization header")
        
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
            
        # Verify JWT token
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        # Return the user_id
        return payload["sub"]
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token format")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
