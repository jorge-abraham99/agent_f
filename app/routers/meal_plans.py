import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

# --- UPDATED IMPORTS ---
from app.models.schemas import MealPlanRequest
from app.models.user_logic import user
from app.services.agent_service import generate_meal_plan_with_agent, map_workouts_to_activity_level,convert_questionnaire_to_meal_plan_request

from fastapi import Depends       # We need 'Depends' to use our dependency
from gotrue.types import User     # This is the data type for the user object Supabase returns
from app.core.security import get_current_user # Import our lock checker!
from app.tools.database_tools import get_current_meal_plan
from app.services.supabase_client import supabase

# Create an APIRouter
router = APIRouter(
    prefix="/plans",  # Optional: adds /plans before each endpoint path
    tags=["Meal Plans"] # Groups endpoints in the API docs
)

# NOTE: The endpoint path is now just "/", because the prefix is added automatically.
# Full path will be /plans/generate_meal_plan
@router.post("/generate_meal_plan", response_class=JSONResponse)
def generate_meal_plan(current_user: User = Depends(get_current_user)):
    """
    Generate a personalized meal plan based on user's questionnaire data 
    stored in their Supabase auth metadata.
    """
    try:
        print(f"📋 Generating meal plan for user: {str(current_user.user.id)}")
        
        # Get questionnaire data from user metadata
        questionnaire_data = get_user_questionnaire(str(current_user.user.id))
        
        # Convert to MealPlanRequest format
        request = convert_questionnaire_to_meal_plan_request(questionnaire_data)
        
        print(f"📊 Meal plan request: {request.dict()}")
        
        # Map workouts per week to activity level
        activity_level = map_workouts_to_activity_level(request.workouts_per_week)
        user_id = str(current_user.user.id)
        
        # Create user instance
        user_instance = user(
            sex=request.gender,
            height=request.height,
            age=request.age,
            weight=request.weight,
            activity_level=activity_level,
            planned_weekly_weight_loss=request.planned_weekly_weight_loss,
            desired_weight=request.weight_goal
        )
        
        # Calculate nutritional targets
        goal_calories = round(user_instance.goal_based_bmr(request.goal))
        protein_grams = round(user_instance.protein_intake(request.goal), 1)
        fat_grams = round(user_instance.fat_intake(request.goal), 1)
        carbs_grams = round(user_instance.carbs_intake(request.goal), 1)
        
        print(f"🎯 Nutritional targets - Calories: {goal_calories}, Protein: {protein_grams}g, Fat: {fat_grams}g, Carbs: {carbs_grams}g")
        
        # Create prompt for the AI agent
        prompt = f"""
Hi NutriWise AI, I need a personalized daily meal plan.

**CRITICAL: My user ID is: {user_id}**

**My Daily Targets:**
- Calories: {goal_calories}
- Protein: {protein_grams}g
- Fat: {fat_grams}g
- Carbs: {carbs_grams}g

**Dietary Preference:** {request.diet}
**Additional Preferences:** {request.additional_considerations}

**YOUR TASK (complete ALL steps):**
1. Calculate meal targets (20% breakfast, 32.5% lunch, 32.5% dinner, 15% snacks)
2. Search for appropriate recipes
3. Create and display the complete meal plan
4. **MANDATORY: Call save_meal_plan() with:**
   - user_id: "{user_id}"
   - plan_data: your complete meal_plan object
   - user_targets: {{"calories": {goal_calories}, "protein": {protein_grams}, "fat": {fat_grams}, "carbs": {carbs_grams}}}
5. Confirm the save was successful

Do NOT end your response until save_meal_plan has been called.
"""
        
        # Generate meal plan using the agent
        print(f"🤖 Calling AI agent to generate meal plan...")
        agent_response = generate_meal_plan_with_agent(prompt)
        
        print(f"📥 Fetching saved meal plan from database...")
        meal_plan_json_string = get_current_meal_plan(user_id=user_id)
        
        # The tool returns a JSON string, so we need to parse it
        meal_plan_response = json.loads(meal_plan_json_string)

        meal_plan_data = None
        if meal_plan_response.get("success"):
            # Extract just the plan data to return in the response
            meal_plan_data = meal_plan_response.get("plan")
            print(f"✅ Meal plan generated and saved successfully!")
        else:
            print(f"⚠️ Meal plan response: {meal_plan_response}")

        return {
            "status": "success",
            "user_info": {
                "gender": request.gender,
                "height": request.height,
                "age": request.age,
                "weight": request.weight,
                "workouts_per_week": request.workouts_per_week,
                "activity_level": activity_level,
                "goal": request.goal,
                "diet": request.diet,
                "additional_considerations": request.additional_considerations
            },
            "nutritional_targets": {
                "calories": goal_calories,
                "protein_grams": protein_grams,
                "fat_grams": fat_grams,
                "carbs_grams": carbs_grams
            },
            "agent_response": agent_response,
            "meal_plan": meal_plan_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating meal plan: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating meal plan: {str(e)}")

@router.get("/current", response_class=JSONResponse)
def read_current_meal_plan(current_user: User = Depends(get_current_user)):
    """
    Retrieves the most recent meal plan for the authenticated user.
    """
    try:
        # Get the user_id from the nested .user attribute of the response object
        # <<< FIX IS HERE
        user_id = str(current_user.user.id)

        # Query the database for the most recent plan for this user
        response = supabase.table('meal_plans')\
            .select('id, plan_data, user_targets, created_at')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
        
        # Check if any data was returned
        if response.data and len(response.data) > 0:
            # If a plan is found, return it with a 200 OK status
            return response.data[0]
        else:
            # If no plan is found, raise a 404 Not Found error
            raise HTTPException(
                status_code=404, 
                detail="No meal plan found for this user."
            )

    except HTTPException as he:
        # Re-raise HTTPExceptions so FastAPI can handle them correctly
        raise he
    except Exception as e:
        # For any other unexpected errors (e.g., database connection issue),
        # return a 500 Internal Server Error.
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred while retrieving the meal plan: {str(e)}"
        )

def get_user_questionnaire(user_id: str) -> dict:
    """
    Retrieve questionnaire data from the authenticated user's metadata.
    Returns the questionnaire dict or raises an exception if not found.
    """
    try:
        # Get the full user data from Supabase including metadata
        user_response = supabase.auth.admin.get_user_by_id(user_id)
        
        if not user_response or not user_response.user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Extract questionnaire from user_metadata
        user_metadata = user_response.user.user_metadata or {}
        questionnaire_data = user_metadata.get('questionnaire', {})
        
        if not questionnaire_data:
            raise HTTPException(
                status_code=400,
                detail="No questionnaire data found. Please complete the onboarding process."
            )
        
        print(f"✅ Retrieved questionnaire data for user: {user_id}")
        return questionnaire_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving questionnaire: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve questionnaire: {str(e)}"
        )
