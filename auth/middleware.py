from fastapi import Request, HTTPException
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY

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
        
        # Verify the JWT token with Supabase
        user = supabase.auth.get_user(token)
        
        # Add the user to request state for use in route handlers
        request.state.user = user
        
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token format")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) 