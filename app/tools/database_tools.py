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
    
    This creates a new meal plan entry with a timestamp. Each user can have multiple
    meal plans saved over time.

    Args:
        user_id: The UUID of the user
        plan_data: The complete JSON object of the meal plan with all meals and recipes
        user_targets: The user's nutritional targets (calories, protein, fat, carbs, etc.)

    Returns:
        JSON string with success status and the saved plan ID, or an error message
    """
    try:
        response = supabase.table('meal_plans').insert({
            'user_id': user_id,
            'plan_data': plan_data,
            'user_targets': user_targets
        }).execute()
        
        # Check if the insert was successful
        if response.data and len(response.data) > 0:
            return json.dumps({
                "success": True,
                "message": "Meal plan saved successfully.",
                "plan_id": response.data[0].get('id')
            })
        else:
            return json.dumps({
                "success": False,
                "error": f"Failed to save meal plan: {response.error}"
            })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"An error occurred while saving the plan: {str(e)}"
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