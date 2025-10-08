from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.models.schemas import UserCreate, Token
from app.services.supabase_client import supabase # We need our Supabase client
from dotenv import load_dotenv
import os

# Create the router for authentication endpoints
router = APIRouter(
    tags=["Authentication"] # This helps group endpoints in the API docs
)

@router.post("/signup", status_code=201, response_model=dict)
def sign_up(user_credentials: UserCreate):
    """
    Handles new user registration by creating a user in Supabase Auth.
    Stores questionnaire data in user metadata.
    """
    load_dotenv()
    environment = os.getenv("ENVIRONMENT", "dev")
    
    frontend_urls = {
        "dev": "http://localhost:8081",
        "prod": "https://yourdomain.com"
    }
    
    frontend_url = frontend_urls.get(environment, "http://localhost:8081")
    
    try:
        # Prepare user metadata
        user_metadata = {
            "name": user_credentials.name
        }
        
        # Add questionnaire data if provided
        if user_credentials.questionnaire_data:
            user_metadata["questionnaire"] = user_credentials.questionnaire_data
            print(f"📋 Storing questionnaire data in user metadata for: {user_credentials.email}")
        
        response = supabase.auth.sign_up({
            "email": user_credentials.email,
            "password": user_credentials.password,
            "options": {
                "email_redirect_to": f"{frontend_url}/onboarding/loading",
                "data": user_metadata  # Store all metadata including questionnaire
            }
        })
        
        if response.user:
            print(f"✅ User created with metadata: {user_credentials.email}")
            return {"message": "User created successfully. Please check your email for verification."}
        else:
            raise HTTPException(status_code=400, detail="Could not create user for an unknown reason.")
            
    except Exception as e:
        print(f"❌ Signup failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Handles user login. It takes form data (not JSON) and returns a JWT access token.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": form_data.username, # Note: OAuth2 form uses 'username' for the email field
            "password": form_data.password
        })
        return {
            "access_token": response.session.access_token,
            "token_type": "bearer"
        }
    except Exception:
        # Avoid leaking specific error info, just say login failed.
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )