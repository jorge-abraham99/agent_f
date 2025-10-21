from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.models.schemas import UserCreate, Token, ProfileCreate
from app.services.supabase_client import supabase # We need our Supabase client
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
from app.core.security import get_current_user 
from gotrue.types import User

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
        "prod": "https://nutriwise-onboard-ace.vercel.app"
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
                "email_redirect_to": f"{frontend_url}/onboarding/account",
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


@router.post("/profile", response_class=JSONResponse)
def create_or_update_profile(
    profile_data: ProfileCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create or update user profile after onboarding.
    This is called after the user completes the questionnaire.
    
    The profile data is needed for generating meal plans.
    """
    try:
        user_id = str(current_user.user.id)
        print(f"📝 Creating/updating profile for user: {user_id}")
        
        # Map frontend goal to backend goal
        goal_map = {
            'lose': 'Fat Loss',
            'build': 'Build Muscle',
            'maintain': 'General Health / Maintenance',
        }
        mapped_goal = goal_map.get(profile_data.goal.lower(), 'General Health / Maintenance')
        
        # Validate data
        if profile_data.gender not in ['male', 'female']:
            raise HTTPException(status_code=400, detail="Gender must be 'male' or 'female'")
        
        if not 0 <= profile_data.workouts_per_week <= 7:
            raise HTTPException(status_code=400, detail="Workouts per week must be between 0 and 7")
        
        if profile_data.height <= 0 or profile_data.weight <= 0 or profile_data.age <= 0:
            raise HTTPException(status_code=400, detail="Height, weight, and age must be positive")
        
        # Prepare profile data
        profile_record = {
            'id': user_id,
            'gender': profile_data.gender,
            'height': profile_data.height,
            'weight': profile_data.weight,
            'age': profile_data.age,
            'workouts_per_week': profile_data.workouts_per_week,
            'goal': mapped_goal,
            'weight_goal': profile_data.weight_goal,
            'planned_weekly_weight_loss': profile_data.planned_weekly_weight_loss,
            'updated_at': 'now()'
        }
        
        # Check if profile exists
        try:
            existing_profile = supabase.table('profiles')\
                .select('id')\
                .eq('id', user_id)\
                .execute()

            print(f"🔍 Existing profile check result: {existing_profile.data}")
        except Exception as check_error:
            print(f"⚠️ Error checking existing profile: {str(check_error)}")
            existing_profile = None

        if existing_profile and existing_profile.data and len(existing_profile.data) > 0:
            # Update existing profile
            print(f"🔄 Updating existing profile for user {user_id}")
            response = supabase.table('profiles')\
                .update(profile_record)\
                .eq('id', user_id)\
                .execute()
            print(f"📤 Update response: {response}")
        else:
            # Insert new profile
            print(f"✨ Creating new profile for user {user_id}")
            response = supabase.table('profiles')\
                .insert(profile_record)\
                .execute()
            print(f"📤 Insert response: {response}")

        # Check for errors in the response
        if hasattr(response, 'error') and response.error:
            print(f"❌ Supabase error: {response.error}")
            raise HTTPException(status_code=500, detail=f"Database error: {response.error}")

        if not response.data:
            print(f"⚠️ Empty response data. Full response: {response}")
            raise HTTPException(status_code=500, detail="Failed to save profile - empty response")
        
        print(f"✅ Profile saved successfully for user {user_id}")
        
        return {
            "status": "success",
            "message": "Profile saved successfully",
            "profile": response.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error saving profile: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error saving profile: {str(e)}"
        )


@router.get("/profile", response_class=JSONResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    """
    Get the current user's profile.
    """
    try:
        user_id = str(current_user.user.id)
        
        response = supabase.table('profiles')\
            .select('*')\
            .eq('id', user_id)\
            .single()\
            .execute()
        
        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Profile not found. Please complete onboarding."
            )
        
        return {
            "status": "success",
            "profile": response.data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving profile: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving profile: {str(e)}"
        )
    
@router.put("/profile", response_class=JSONResponse)
def update_profile(
    profile_data: ProfileCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Update user profile.
    This is the same as create_or_update_profile but semantically clearer for updates.
    """
    return create_or_update_profile(profile_data, current_user)