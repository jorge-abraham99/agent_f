from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.services.supabase_client import supabase # We need this to talk to Supabase
from gotrue.errors import AuthApiError
from gotrue.types import User

# Part 1: Define HOW to find the token in a request.
# We're telling FastAPI: "The token (our key) will be in an 'Authorization' header.
# If a client wants to know HOW to log in to GET a token, the login endpoint is at '/token'."
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Part 2: Define the logic to VALIDATE the token.
# This is our reusable "lock checker" function.
def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    This is a FastAPI dependency. It will automatically:
    1. Look for an 'Authorization: Bearer <token>' header (thanks to oauth2_scheme).
    2. Pass the <token> string into this function as the 'token' argument.
    3. Run our validation logic.
    """
    try:
        # Step 2a: We ask Supabase to validate the token.
        # This is the most important line. It checks the signature and expiration.
        user = supabase.auth.get_user(token)
        
        # Step 2b: If the token is valid, Supabase returns the user's data.
        # We return this user object, and the dependency succeeds.
        return user
        
    except AuthApiError:
        # Step 2c: If the token is invalid (expired, fake, etc.), Supabase
        # throws an error. We catch it.
        # We then tell FastAPI to immediately stop everything and send back a
        # 401 Unauthorized error. This is the standard, secure way to deny access.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )