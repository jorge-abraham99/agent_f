import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

# --- UPDATED IMPORTS ---
from app.models.schemas import MealPlanRequest
from app.models.user_logic import user
from app.services.agent_service import generate_meal_plan_with_agent, map_workouts_to_activity_level,convert_questionnaire_to_meal_plan_request,generate_weekly_meal_plan

from fastapi import Depends       # We need 'Depends' to use our dependency
from gotrue.types import User     # This is the data type for the user object Supabase returns
from app.core.security import get_current_user # Import our lock checker!
from app.tools.database_tools import get_current_meal_plan
from app.services.supabase_client import supabase
from app.models.user_logic import user 

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
        questionnaire_data = get_user_questionnaire(current_user)
        
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

@router.post("/generate_weekly_plan", response_class=JSONResponse)
def generate_weekly_plan_endpoint(current_user: User = Depends(get_current_user)):
    """
    Generate a complete 7-day weekly meal plan.
    Called after user completes payment.
    
    Returns:
        {
            "status": "success",
            "weekly_plan_id": 123,
            "week_start_date": "2025-10-20",
            "days_generated": 7,
            "message": "Weekly meal plan generated successfully"
        }
    """
    try:
        user_id = str(current_user.user.id)
        print(f"📅 Generating weekly meal plan for user: {user_id}")
        
        # 1. Get user's questionnaire data
        questionnaire_data = get_user_questionnaire(current_user)
        
        # 2. Get user profile from database (for additional data)
        profile_response = supabase.table('profiles')\
            .select('*')\
            .eq('id', user_id)\
            .single()\
            .execute()
        
        if not profile_response.data:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        profile = profile_response.data
        
        # 3. Merge questionnaire and profile data
        profile_data = {
            'gender': profile['gender'],
            'height': profile['height'],
            'age': profile['age'],
            'weight': profile['weight'],
            'workouts_per_week': profile['workouts_per_week'],
            'goal': profile['goal'],
            'weight_goal': profile['weight_goal'],
            'planned_weekly_weight_loss': profile['planned_weekly_weight_loss'],
        }
        
        # 4. Build preferences
        preferences = {
            'diet': questionnaire_data.get('specificDiet', 'balanced'),
            'foodsToAvoid': questionnaire_data.get('foodsToAvoid', []),
            'cuisinePreferences': questionnaire_data.get('cuisinePreferences', []),
            'additional_considerations': build_additional_considerations(questionnaire_data)
        }
        
        print(f"📊 Profile data: {profile_data}")
        print(f"🍽️ Preferences: {preferences}")
        
        # 5. Generate weekly meal plan (this calls the agent 7 times)
        weekly_plan_id = generate_weekly_meal_plan(
            user_id=user_id,
            profile_data=profile_data,
            preferences=preferences
        )
        
        # 6. Get the created plan details
        weekly_plan = supabase.table('weekly_plans')\
            .select('*')\
            .eq('id', weekly_plan_id)\
            .single()\
            .execute()
        
        print(f"✅ Weekly meal plan {weekly_plan_id} generated successfully!")
        
        return {
            "status": "success",
            "weekly_plan_id": weekly_plan_id,
            "week_start_date": str(weekly_plan.data['week_start_date']),
            "days_generated": 7,
            "weekly_targets": {
                "calories": weekly_plan.data['weekly_target_calories'],
                "protein": weekly_plan.data['weekly_target_protein'],
                "carbs": weekly_plan.data['weekly_target_carbs'],
                "fat": weekly_plan.data['weekly_target_fat']
            },
            "message": "Weekly meal plan generated successfully!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating weekly meal plan: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error generating weekly meal plan: {str(e)}"
        )


@router.get("/weekly/current", response_class=JSONResponse)
def get_current_weekly_plan(current_user: User = Depends(get_current_user)):
    """
    Get the user's most recent active weekly plan.
    Useful for showing "Your Current Plan" in the UI.
    """
    try:
        user_id = str(current_user.user.id)

        # Get most recent active weekly plan
        weekly_plan_response = supabase.table('weekly_plans')\
            .select('id, week_start_date, status, created_at')\
            .eq('user_id', user_id)\
            .eq('status', 'active')\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()

        if not weekly_plan_response.data or len(weekly_plan_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="No active weekly plan found. Generate one first."
            )

        weekly_plan = weekly_plan_response.data[0]

        # Return basic info (frontend can call /weekly/{id} for full details)
        return {
            "weekly_plan_id": weekly_plan['id'],
            "week_start_date": weekly_plan['week_start_date'],
            "status": weekly_plan['status'],
            "created_at": weekly_plan['created_at']
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving current weekly plan: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving current weekly plan: {str(e)}"
        )


@router.get("/weekly/{weekly_plan_id}", response_class=JSONResponse)
def get_weekly_plan(
    weekly_plan_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get weekly plan overview with all 7 days.
    
    Returns:
        {
            "weekly_plan": {...},
            "daily_plans": [
                {
                    "date": "2025-10-20",
                    "day_of_week": 1,
                    "total_calories": 2005,
                    "meal_count": 4,
                    ...
                },
                ...
            ]
        }
    """
    try:
        user_id = str(current_user.user.id)
        
        # 1. Get weekly plan
        weekly_plan_response = supabase.table('weekly_plans')\
            .select('*')\
            .eq('id', weekly_plan_id)\
            .eq('user_id', user_id)\
            .single()\
            .execute()
        
        if not weekly_plan_response.data:
            raise HTTPException(
                status_code=404,
                detail="Weekly plan not found or you don't have access"
            )
        
        # 2. Get all daily plans for this week
        daily_plans_response = supabase.table('daily_plans')\
            .select('*')\
            .eq('weekly_plan_id', weekly_plan_id)\
            .order('date')\
            .execute()
        
        # 3. For each daily plan, get meal count
        daily_plans_with_meals = []
        for daily_plan in daily_plans_response.data:
            meals_response = supabase.table('meals')\
                .select('id, meal_type, recipe_id')\
                .eq('daily_plan_id', daily_plan['id'])\
                .execute()
            
            daily_plans_with_meals.append({
                **daily_plan,
                'meal_count': len(meals_response.data),
                'meals_preview': meals_response.data  # Just IDs and types
            })
        
        return {
            "weekly_plan": weekly_plan_response.data,
            "daily_plans": daily_plans_with_meals,
            "total_days": len(daily_plans_with_meals)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving weekly plan: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving weekly plan: {str(e)}"
        )


@router.get("/daily/{daily_plan_id}/meals", response_class=JSONResponse)
def get_daily_meals(
    daily_plan_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get all meals for a specific day with full recipe details.
    
    Returns:
        {
            "daily_plan": {...},
            "meals": [
                {
                    "id": 1,
                    "meal_type": "breakfast",
                    "servings": 1.2,
                    "actual_calories": 480,
                    "recipe": {
                        "id": 42,
                        "name": "Veggie Omelette",
                        "calories": 400,
                        ...
                    }
                },
                ...
            ]
        }
    """
    try:
        user_id = str(current_user.user.id)
        
        # 1. Verify access - check if daily plan belongs to user
        daily_plan_response = supabase.table('daily_plans')\
            .select('*, weekly_plans!inner(user_id)')\
            .eq('id', daily_plan_id)\
            .single()\
            .execute()
        
        if not daily_plan_response.data:
            raise HTTPException(status_code=404, detail="Daily plan not found")
        
        if daily_plan_response.data['weekly_plans']['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # 2. Get all meals with recipe details
        meals_response = supabase.table('meals')\
            .select('*, recipes(*)')\
            .eq('daily_plan_id', daily_plan_id)\
            .order('meal_type')\
            .execute()
        
        # 3. Sort meals by meal type order
        meal_order = {'breakfast': 1, 'lunch': 2, 'dinner': 3, 'snack': 4}
        sorted_meals = sorted(
            meals_response.data,
            key=lambda m: (meal_order.get(m['meal_type'], 5), m.get('meal_order', 1))
        )
        
        return {
            "daily_plan": {
                "id": daily_plan_response.data['id'],
                "date": daily_plan_response.data['date'],
                "day_of_week": daily_plan_response.data['day_of_week'],
                "daily_target_calories": daily_plan_response.data['daily_target_calories'],
                "total_calories": daily_plan_response.data['total_calories'],
                "total_protein": daily_plan_response.data['total_protein'],
                "total_carbs": daily_plan_response.data['total_carbs'],
                "total_fat": daily_plan_response.data['total_fat']
            },
            "meals": sorted_meals,
            "meal_count": len(sorted_meals)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving daily meals: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving daily meals: {str(e)}"
        )


@router.get("/meals/{meal_id}", response_class=JSONResponse)
def get_meal_detail(
    meal_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information for a specific meal including full recipe.
    This is called when user clicks on a meal to see ingredients and instructions.
    
    Returns:
        {
            "meal": {
                "id": 1,
                "meal_type": "breakfast",
                "servings": 1.2,
                "actual_calories": 480,
                ...
            },
            "recipe": {
                "id": 42,
                "name": "Veggie Omelette",
                "calories": 400,
                "protein": 25,
                "carbohydrates": 12,
                "fat": 18,
                "ingredients": [...],  // When you add this later
                "dietary_tags": ["vegetarian", "high-protein"]
            }
        }
    """
    try:
        user_id = str(current_user.user.id)
        
        # 1. Get meal with recipe and verify access
        meal_response = supabase.table('meals')\
            .select('*, recipes(*), daily_plans!inner(weekly_plans!inner(user_id))')\
            .eq('id', meal_id)\
            .single()\
            .execute()
        
        if not meal_response.data:
            raise HTTPException(status_code=404, detail="Meal not found")
        
        # Verify user owns this meal
        if meal_response.data['daily_plans']['weekly_plans']['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        meal_data = meal_response.data
        recipe_data = meal_data.pop('recipes')
        daily_plans_data = meal_data.pop('daily_plans')
        
        return {
            "meal": meal_data,
            "recipe": recipe_data,
            "serving_info": {
                "servings": meal_data['servings'],
                "calories_per_serving": recipe_data['calories'],
                "actual_calories": meal_data['actual_calories'],
                "scaling_factor": meal_data['servings']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving meal detail: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving meal detail: {str(e)}"
        )


def get_user_questionnaire(current_user: User) -> dict:
    """
    Retrieve questionnaire data from the authenticated user's metadata.
    Returns the questionnaire dict or raises an exception if not found.
    """
    try:
        # Extract questionnaire from user_metadata (already available in current_user)
        user_metadata = current_user.user.user_metadata or {}
        questionnaire_data = user_metadata.get('questionnaire', {})

        if not questionnaire_data:
            raise HTTPException(
                status_code=400,
                detail="No questionnaire data found. Please complete the onboarding process."
            )

        print(f"✅ Retrieved questionnaire data for user: {current_user.user.id}")
        return questionnaire_data

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving questionnaire: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve questionnaire: {str(e)}"
        )
def map_goal_from_questionnaire(goal_key: str) -> str:
    """Map frontend goal keys to backend goal strings"""
    goal_map = {
        'lose': 'Fat Loss',
        'build': 'Build Muscle',
        'maintain': 'General Health / Maintenance',
    }
    return goal_map.get(goal_key.lower(), 'General Health / Maintenance')


def build_additional_considerations(questionnaire: dict) -> str:
    """Build a string of additional considerations from questionnaire"""
    parts = []
    
    if questionnaire.get('foodsToAvoid'):
        foods = ', '.join(questionnaire['foodsToAvoid'])
        parts.append(f"Avoid: {foods}")
    
    if questionnaire.get('cuisinePreferences'):
        cuisines = ', '.join(questionnaire['cuisinePreferences'])
        parts.append(f"Prefers {cuisines} cuisine")
    
    if questionnaire.get('mealPreferences'):
        meals = ', '.join(questionnaire['mealPreferences'])
        parts.append(f"Meal preferences: {meals}")
    
    if questionnaire.get('fasting'):
        parts.append("Interested in intermittent fasting")
    
    if questionnaire.get('motivation'):
        parts.append(f"Motivation: {questionnaire['motivation']}")
    
    if questionnaire.get('otherNotes'):
        parts.append(questionnaire['otherNotes'])
    
    return '; '.join(filter(None, parts))