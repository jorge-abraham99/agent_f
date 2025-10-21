import json
from app.services.supabase_client import supabase
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import pandas as pd

# Cache the recipes DataFrame to avoid repeated DB queries
_recipes_cache = None

def load_recipes_from_supabase():
    """Load all recipes into a pandas DataFrame (cached after first load)"""
    global _recipes_cache
    if _recipes_cache is None:
        print("📥 Loading recipes from Supabase (first time)...")
        response = supabase.table('recipes').select('*').execute()
        _recipes_cache = pd.DataFrame(response.data)
        print(f"✅ Loaded {len(_recipes_cache)} recipes into cache")
    return _recipes_cache

def fuzzy_search_rows(query: str, column_name: str = "name", threshold: int = 85):
    """Performs a fuzzy search on recipe names and returns first 15 matching rows with nutritional information per serving, 
    including calories, protein, fat, carbohydrates, and sodium.
    
    Args: 
        query: The search term to match against recipe names (e.g., "chicken curry", "salmon bowl")
        column_name: The column to search in (default: "name")
        threshold: Minimum similarity score from 0 to 100 (default: 85)
    
    Returns:
        JSON string with matching recipes
    """
    try:
        df = load_recipes_from_supabase()
        matches = process.extract(query, df[column_name], scorer=fuzz.token_set_ratio, limit=len(df))
        matched_indices = [idx for (name, score, idx) in matches if score >= threshold]
        
        matched_df = df.iloc[matched_indices].reset_index(drop=True)
        
        matched_df = matched_df.head(15)
        return json.dumps({
            "success": True,
            "count": len(matched_df),
            "results": matched_df.to_dict(orient='records')  # DataFrame -> dict -> JSON
        })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": str(e),
            "results": []
        })

def search_recipes(query: str, threshold: float = 0.80) -> str:
    """
    Searches recipes using PostgreSQL fuzzy matching.
    
    Args:
        query: Search term for recipe name
        threshold: Similarity threshold (0-1). Default 0.80 = 80% match
    
    Returns:
        JSON string of matching recipes with nutritional info
    """
    try:
        response = supabase.rpc(
            'search_recipes_fuzzy',
            {
                'search_query': query,
                'similarity_threshold': threshold
            }
        ).execute()
        
        return json.dumps(response.data)
    
    except Exception as e:
        return json.dumps({"error": str(e), "results": []})
    

def save_meal_plan(user_id: str, plan_data: dict, user_targets: dict) -> str:
    """
    Saves a generated meal plan to the database for a specific user.
    
    Args:
        user_id: The UUID of the user
        plan_data: The complete meal plan object (will be converted to dict if needed)
        user_targets: Dict with keys: calories, protein, fat, carbs (all numbers)

    Returns:
        JSON string with success status and plan ID, or error details
    """
    try:
        # Validate user_id
        if not user_id or not isinstance(user_id, str):
            return json.dumps({
                "success": False,
                "error": "Invalid user_id. Must be a non-empty string."
            })
        
        # Handle plan_data - convert from string if needed
        if isinstance(plan_data, str):
            try:
                plan_data = json.loads(plan_data)
            except json.JSONDecodeError:
                return json.dumps({
                    "success": False,
                    "error": "plan_data is a string but not valid JSON"
                })
        
        # Handle user_targets - convert from string if needed
        if isinstance(user_targets, str):
            try:
                user_targets = json.loads(user_targets)
            except json.JSONDecodeError:
                return json.dumps({
                    "success": False,
                    "error": "user_targets is a string but not valid JSON"
                })
        
        # Validate plan_data structure
        if not isinstance(plan_data, dict):
            return json.dumps({
                "success": False,
                "error": f"plan_data must be a dict, got {type(plan_data).__name__}"
            })
        
        # Validate user_targets structure
        if not isinstance(user_targets, dict):
            return json.dumps({
                "success": False,
                "error": f"user_targets must be a dict, got {type(user_targets).__name__}"
            })
        
        required_target_keys = ['calories', 'protein', 'fat', 'carbs']
        missing_keys = [key for key in required_target_keys if key not in user_targets]
        if missing_keys:
            return json.dumps({
                "success": False,
                "error": f"user_targets missing required keys: {missing_keys}"
            })
        
        # Ensure all target values are numbers
        for key in required_target_keys:
            if not isinstance(user_targets[key], (int, float)):
                return json.dumps({
                    "success": False,
                    "error": f"user_targets['{key}'] must be a number, got {type(user_targets[key]).__name__}"
                })
        
        # Insert into database
        response = supabase.table('meal_plans').insert({
            'user_id': user_id,
            'plan_data': plan_data,
            'user_targets': user_targets
        }).execute()
        
        # Check if the insert was successful
        if response.data and len(response.data) > 0:
            plan_id = response.data[0].get('id')
            return json.dumps({
                "success": True,
                "message": "Meal plan saved successfully",
                "plan_id": plan_id
            })
        else:
            error_msg = getattr(response, 'error', 'Unknown error')
            return json.dumps({
                "success": False,
                "error": f"Database insert failed: {error_msg}"
            })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Exception while saving plan: {str(e)}",
            "error_type": type(e).__name__
        })


def get_current_meal_plan(user_id: str) -> str:
    """
    Retrieves the most recent meal plan for a specific user.
    
    This is useful for reviewing the current plan, making modifications, or checking
    what the user is currently following.

    Args:
        user_id: The UUID of the user whose meal plan to retrieve

    Returns:
        JSON string containing the most recent meal plan with all details, or an error message
    """
    try:
        response = supabase.table('meal_plans')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
        
        if response.data and len(response.data) > 0:
            plan = response.data[0]
            return json.dumps({
                "success": True,
                "plan": {
                    "id": plan.get('id'),
                    "plan_data": plan.get('plan_data'),
                    "user_targets": plan.get('user_targets'),
                    "created_at": plan.get('created_at')
                }
            })
        else:
            return json.dumps({
                "success": False,
                "message": "No meal plan found for this user."
            })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"An error occurred while retrieving the meal plan: {str(e)}"
        })
    
# app/tools/database_tools.py

def get_previous_recipes_in_week(weekly_plan_id: int) -> str:
    """
    Retrieves all recipe names used so far in the current weekly plan
    to help avoid repetition when generating new days.
    
    Args:
        weekly_plan_id: The ID of the weekly plan being generated
    
    Returns:
        JSON string with list of recipe names already used
    """
    try:
        # Query all meals from daily plans in this weekly plan
        response = supabase.table('meals')\
            .select('recipe_id, recipes(name)')\
            .in_('daily_plan_id', 
                supabase.table('daily_plans')
                    .select('id')
                    .eq('weekly_plan_id', weekly_plan_id)
                    .execute().data
            )\
            .execute()
        
        # Extract unique recipe names
        recipe_names = list(set([
            meal['recipes']['name'] 
            for meal in response.data 
            if meal.get('recipes')
        ]))
        
        return json.dumps({
            "success": True,
            "recipes_used": recipe_names,
            "count": len(recipe_names)
        })
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })