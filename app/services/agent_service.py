import os
from fastapi import HTTPException
from google import genai
from google.genai import types
from dotenv import load_dotenv
import json

from app.core.prompts import system_prompt,weekly_day_system_prompt
from app.tools.call_function import call_function

# Import the actual functions we will be describing and calling
from app.tools.database_tools import search_recipes, save_meal_plan, get_current_meal_plan
from app.tools.calculator import calculate
from app.models.schemas import MealPlanRequest
from app.services.supabase_client import supabase
from app.models.user_logic import user 

# --- THIS IS THE CORRECTED TOOL DEFINITION BLOCK ---
# We manually define the schema for each function the model can call.

tools = [
    types.Tool(
        function_declarations=[
            # Schema for search_recipes(query: str, threshold: float = 0.80)
            types.FunctionDeclaration(
                name="search_recipes",
                description=search_recipes.__doc__,
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="The search term for the recipe name."),
                        "threshold": types.Schema(type=types.Type.NUMBER, description="Optional similarity threshold from 0 to 1 (e.g., 0.8).")
                    },
                    required=["query"]
                )
            ),
            
            # Schema for save_meal_plan(user_id: str, plan_data: dict, user_targets: dict)
            types.FunctionDeclaration(
                name="save_meal_plan",
                description=save_meal_plan.__doc__,
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING, 
                            description="The user's unique identifier (UUID string)."
                        ),
                        "plan_data": types.Schema(
                            type=types.Type.OBJECT, 
                            description="The complete meal plan object containing all meals, snacks, and daily totals. Must include the full meal_plan structure with distribution, meals, and nutritional information."
                        ),
                        "user_targets": types.Schema(
                            type=types.Type.OBJECT, 
                            description="Object with user's nutritional targets. Required fields: calories (number), protein (number), fat (number), carbs (number).",
                            properties={
                                "calories": types.Schema(type=types.Type.NUMBER),
                                "protein": types.Schema(type=types.Type.NUMBER),
                                "fat": types.Schema(type=types.Type.NUMBER),
                                "carbs": types.Schema(type=types.Type.NUMBER)
                            },
                            required=["calories", "protein", "fat", "carbs"]
                        )
                    },
                    required=["user_id", "plan_data", "user_targets"]
                )
            ),
            
            # Schema for get_current_meal_plan(user_id: str)
            types.FunctionDeclaration(
                name="get_current_meal_plan",
                description=get_current_meal_plan.__doc__,
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="The user's unique identifier (UUID).")
                    },
                    required=["user_id"] # <-- Correctly noting that user_id is required
                )
            ),

            # Schema for calculate(expression: str)
            types.FunctionDeclaration(
                name="calculate",
                description=calculate.__doc__,
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "expression": types.Schema(type=types.Type.STRING, description="The mathematical expression to evaluate, e.g., '2000 * 0.2'.")
                    },
                    required=["expression"]
                )
            ),
            types.FunctionDeclaration(
                name="fuzzy_search_rows",
                description="Performs a fuzzy search on recipe names and returns matching rows with nutritional information per serving, including calories, protein, fat, carbohydrates, and sodium.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(
                            type=types.Type.STRING, 
                            description="The search term to match against recipe names (e.g., 'chicken curry', 'salmon bowl', 'omelette')."
                        ),
                        "column_name": types.Schema(
                            type=types.Type.STRING, 
                            description="The column to search in. Default is 'name'. Other options might include 'ingredients' if available."
                        ),
                        "threshold": types.Schema(
                            type=types.Type.INTEGER, 
                            description="Minimum similarity score from 0 to 100. Default is 85. Lower values (e.g., 70) return more results."
                        )
                    },
                    required=["query"]
                )
            ),
            types.FunctionDeclaration(
                name="get_previous_recipes_in_week",
                description="Retrieves recipe names already used in the current weekly plan to avoid repetition. Call this BEFORE searching for new recipes.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "weekly_plan_id": types.Schema(
                            type=types.Type.INTEGER,
                            description="The ID of the weekly plan being generated"
                        )
                    },
                    required=["weekly_plan_id"]
                )
            ),
        ]
    )
]

def map_workouts_to_activity_level(workouts_per_week: int) -> str:
    """Map workouts per week to activity level"""
    # ... (this function is correct and remains the same)
    if workouts_per_week <= 2:
        return "lightly active"
    elif workouts_per_week <= 5:
        return "moderately active"
    else:
        return "extra active"

def generate_meal_plan_with_agent(prompt: str, use_weekly_prompt: bool = False) -> str:
    """
    Generate meal plan using the AI agent with detailed logging.
    
    Args:
        prompt: The user prompt
        use_weekly_prompt: If True, use weekly_day_system_prompt instead of system_prompt
    """
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not found")

    # Choose which system prompt to use
    selected_system_prompt = weekly_day_system_prompt if use_weekly_prompt else system_prompt

    client = genai.Client(api_key=api_key)
    messages = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    
    max_iters = 40
    iters = 0

    print("\n--- STARTING NEW AGENT SESSION ---")
    print(f"Using: {'WEEKLY' if use_weekly_prompt else 'PREVIEW'} system prompt")
    print(f"Initial Prompt: {prompt[:200]}...")

    while iters < max_iters:
        iters += 1
        print(f"\n--- AGENT ITERATION {iters} ---")

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=messages,
                config=types.GenerateContentConfig(
                    tools=tools,
                    system_instruction=selected_system_prompt
                ),
            )

            candidate = response.candidates[0]

            # ADD DIAGNOSTIC LOGGING
            print(f"Finish reason: {candidate.finish_reason}")
            print(f"Safety ratings: {candidate.safety_ratings if hasattr(candidate, 'safety_ratings') else 'N/A'}")
            print(f"Content present: {candidate.content is not None}")
            print(f"Parts present: {candidate.content.parts if candidate.content else 'No content'}")
            print(f"Message history length: {len(messages)}")

            if hasattr(candidate, 'grounding_metadata'):
                print(f"Grounding metadata: {candidate.grounding_metadata}")
            if hasattr(response, 'prompt_feedback'):
                print(f"Prompt feedback: {response.prompt_feedback}")

            if not candidate.content or not candidate.content.parts:
                print("!!! Model returned an empty response. Stopping. !!!")
                print(f"Finish reason was: {candidate.finish_reason}")
                print(f"Iteration: {iters}")

                if str(candidate.finish_reason) == "FinishReason.MALFORMED_FUNCTION_CALL":
                    print("⚠️ Model generated a malformed function call. Attempting recovery...")
                    print(f"   Iteration {iters}: This might be a save_meal_plan call with invalid JSON structure.")

                    if iters >= max_iters - 5:
                        print("❌ Too many malformed calls near max iterations. Stopping.")
                        raise HTTPException(status_code=500, detail="Agent repeatedly generated malformed function calls")

                    messages.append(types.Content(
                        role="user",
                        parts=[types.Part(text="Error: Your last function call was malformed. Please retry with valid JSON arguments. For save_meal_plan, ensure plan_data is a properly formatted dict with all required fields. Double-check all quotes, commas, and brackets.")]
                    ))
                    continue

                # If we get STOP with empty content on first iteration, it might be a rate limit or safety issue
                if iters == 1:
                    print("❌ Empty response on first iteration - possible rate limit or prompt issue")
                    raise HTTPException(
                        status_code=429,
                        detail="AI service returned empty response. This may be due to rate limiting or prompt safety filters. Please try again in a moment."
                    )

                print(f"⚠️ Returning empty response after {iters} iterations")
                return "Agent returned an empty response."

            messages.append(candidate.content)

            # --- PROCESS ALL PARTS ---
            parts = candidate.content.parts
            print(f"📦 Response has {len(parts)} part(s)")

            has_function_calls = False
            all_text_parts = []  # ⭐ Collect ALL text parts

            for idx, part in enumerate(parts):
                print(f"\n  Part {idx}: ", end="")

                if hasattr(part, 'function_call') and part.function_call and part.function_call.name:
                    has_function_calls = True
                    function_call = part.function_call

                    print(f"Function call: '{function_call.name}'")
                    args_dict = dict(function_call.args)
                    print(f"    Arguments: {json.dumps(args_dict, indent=2)[:100]}...")

                    tool_response = call_function(function_call, verbose=True)
                    messages.append(tool_response)

                elif hasattr(part, 'text') and part.text:
                    print(f"Text: {part.text[:100]}...")
                    all_text_parts.append(part.text)  # ⭐ Collect this text
                else:
                    print(f"Unknown part type: {type(part)}")

            # If there were function calls, continue the loop
            if has_function_calls:
                print("✅ Processed function call(s), continuing...")
                continue

            # ⭐ If we only got text and no function calls, concatenate ALL text parts
            if all_text_parts:
                final_text = "\n".join(all_text_parts)  # ⭐ Combine all text parts
                print(f"✅ Agent finished. Final response: {final_text[:200]}...")
                return final_text

            print("⚠️ Response had no function calls and no text. Continuing...")
            continue

        except Exception as e:
            print(f"!!! ERROR in agent loop: {e} !!!")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Error in agent processing: {str(e)}")

    print("!!! Maximum iterations reached. Stopping. !!!")
    raise HTTPException(status_code=508, detail="Maximum iterations")

def convert_questionnaire_to_meal_plan_request(questionnaire: dict) -> MealPlanRequest:
    """
    Convert questionnaire data from metadata into MealPlanRequest format.
    """
    # Map frontend goal values to backend expected values
    goal_map = {
        'lose': 'Fat Loss',
        'build': 'Build Muscle',
        'maintain': 'General Health / Maintenance',
    }
    
    # Build additional considerations string
    additional_considerations_parts = []
    
    if questionnaire.get('foodsToAvoid'):
        foods = ', '.join(questionnaire['foodsToAvoid'])
        additional_considerations_parts.append(f"Avoid: {foods}")
    
    if questionnaire.get('cuisinePreferences'):
        cuisines = ', '.join(questionnaire['cuisinePreferences'])
        additional_considerations_parts.append(f"Prefers {cuisines} cuisine")
    
    if questionnaire.get('mealPreferences'):
        meals = ', '.join(questionnaire['mealPreferences'])
        additional_considerations_parts.append(f"Meal preferences: {meals}")
    
    if questionnaire.get('fasting'):
        additional_considerations_parts.append("Interested in intermittent fasting")
    
    if questionnaire.get('motivation'):
        additional_considerations_parts.append(f"Motivation: {questionnaire['motivation']}")
    
    if questionnaire.get('otherNotes'):
        additional_considerations_parts.append(questionnaire['otherNotes'])
    
    additional_considerations = '; '.join(filter(None, additional_considerations_parts))
    
    # Create and return MealPlanRequest object
    meal_plan_request = MealPlanRequest(
        gender=questionnaire.get('gender', 'male'),
        height=float(questionnaire.get('height', 170)),
        age=int(questionnaire.get('age', 30)),
        weight=float(questionnaire.get('weight', 70)),
        workouts_per_week=int(questionnaire.get('workoutFrequency', 0)),
        goal=goal_map.get(questionnaire.get('overallGoal', '').lower(), 'General Health / Maintenance'),
        diet=questionnaire.get('specificDiet', 'balanced'),
        additional_considerations=additional_considerations,
        weight_goal=float(questionnaire.get('weightGoal', questionnaire.get('weight', 70))),
        planned_weekly_weight_loss=float(questionnaire.get('weeklyWeightLoss', 0.5)),
    )
    
    print(f"✅ Converted questionnaire to MealPlanRequest")
    return meal_plan_request

def generate_weekly_meal_plan(user_id: str, profile_data: dict, preferences: dict):
    """
    Generate a complete 7-day meal plan for a user.
    
    Args:
        user_id: User's UUID
        profile_data: User profile info (height, weight, age, etc.)
        preferences: Diet preferences and restrictions
    
    Returns:
        weekly_plan_id: ID of the created weekly plan
    """
    from datetime import date, timedelta
    
    # 1. Calculate nutritional targets (same as your current code)
    activity_level = map_workouts_to_activity_level(profile_data['workouts_per_week'])
    
    user_instance = user(
        sex=profile_data['gender'],
        height=profile_data['height'],
        age=profile_data['age'],
        weight=profile_data['weight'],
        activity_level=activity_level,
        planned_weekly_weight_loss=profile_data.get('planned_weekly_weight_loss', 0.5),
        desired_weight=profile_data.get('weight_goal', profile_data['weight'])
    )
    
    goal = profile_data.get('goal', 'General Health / Maintenance')
    
    daily_calories = round(user_instance.goal_based_bmr(goal))
    daily_protein = round(user_instance.protein_intake(goal), 1)
    daily_fat = round(user_instance.fat_intake(goal), 1)
    daily_carbs = round(user_instance.carbs_intake(goal), 1)
    
    # 2. Create weekly plan container
    week_start = get_next_monday()
    
    weekly_plan = supabase.table('weekly_plans').insert({
        'user_id': user_id,
        'week_start_date': str(week_start),
        'status': 'generating',
        'weekly_target_calories': daily_calories * 7,
        'weekly_target_protein': daily_protein * 7,
        'weekly_target_carbs': daily_carbs * 7,
        'weekly_target_fat': daily_fat * 7,
    }).execute()
    
    weekly_plan_id = weekly_plan.data[0]['id']
    
    print(f"📅 Created weekly plan {weekly_plan_id} starting {week_start}")
    
    # 3. Generate all 7 days
    try:
        print(f"\n🔄 Starting 7-day generation loop...")
        print(f"   Preferences type: {type(preferences)}")
        print(f"   Preferences content: {preferences}")

        for day_num in range(7):
            day_date = week_start + timedelta(days=day_num)

            print(f"\n{'='*60}")
            print(f"🗓️ Generating Day {day_num + 1} of 7 ({day_date.strftime('%A, %B %d')})")
            print(f"{'='*60}")

            try:
                print(f"   Calling generate_single_day_for_weekly_plan...")
                print(f"   Parameters:")
                print(f"     - weekly_plan_id: {weekly_plan_id}")
                print(f"     - day_number: {day_num + 1}")
                print(f"     - day_date: {day_date}")
                print(f"     - user_id: {user_id}")
                print(f"     - daily_targets: {{'calories': {daily_calories}, 'protein': {daily_protein}, 'carbs': {daily_carbs}, 'fat': {daily_fat}}}")
                print(f"     - preferences type: {type(preferences)}")

                generate_single_day_for_weekly_plan(
                    weekly_plan_id=weekly_plan_id,
                    day_number=day_num + 1,
                    day_date=day_date,
                    user_id=user_id,
                    daily_targets={
                        'calories': daily_calories,
                        'protein': daily_protein,
                        'carbs': daily_carbs,
                        'fat': daily_fat
                    },
                    preferences=preferences
                )
                print(f"✅ Day {day_num + 1} completed successfully!")

            except Exception as day_error:
                print(f"❌ ERROR generating day {day_num + 1}: {str(day_error)}")
                print(f"   Error type: {type(day_error).__name__}")
                import traceback
                traceback.print_exc()
                raise
        
        # 4. Mark as active
        supabase.table('weekly_plans').update({
            'status': 'active'
        }).eq('id', weekly_plan_id).execute()
        
        print(f"✅ Weekly plan {weekly_plan_id} completed successfully!")
        
        return weekly_plan_id
        
    except Exception as e:
        print(f"❌ Error generating weekly plan: {e}")
        
        # Mark as failed
        supabase.table('weekly_plans').update({
            'status': 'failed'
        }).eq('id', weekly_plan_id).execute()
        
        raise e


def generate_single_day_for_weekly_plan(
    weekly_plan_id: int,
    day_number: int,
    day_date,
    user_id: str,
    daily_targets: dict,
    preferences: dict
):
    """
    Generate meals for a single day within a weekly plan.
    Uses the SAME agent but with different prompt context.
    """

    print(f"🔧 generate_single_day_for_weekly_plan called")
    print(f"   Received preferences type: {type(preferences)}")
    print(f"   Received preferences value: {preferences}")

    # 1. Create daily plan
    try:
        print(f"   Creating daily plan in database...")
        daily_plan = supabase.table('daily_plans').insert({
            'weekly_plan_id': weekly_plan_id,
            'date': str(day_date),
            'day_of_week': day_number,
            'daily_target_calories': daily_targets['calories'],
            'daily_target_protein': daily_targets['protein'],
            'daily_target_carbs': daily_targets['carbs'],
            'daily_target_fat': daily_targets['fat'],
        }).execute()

        daily_plan_id = daily_plan.data[0]['id']
        print(f"   ✅ Daily plan created with ID: {daily_plan_id}")
    except Exception as dp_error:
        print(f"   ❌ ERROR creating daily plan: {str(dp_error)}")
        raise

    # 2. Create prompt for THIS day (includes weekly_plan_id for context)
    try:
        print(f"   Building prompt with preferences...")
        print(f"   Extracting diet preference...")

        # Defensive checks
        if preferences is None:
            print(f"   ⚠️ WARNING: preferences is None!")
            diet = 'balanced'
            foods_to_avoid = []
            additional = ''
        elif not isinstance(preferences, dict):
            print(f"   ⚠️ WARNING: preferences is not a dict, it's {type(preferences)}")
            diet = 'balanced'
            foods_to_avoid = []
            additional = ''
        else:
            diet = preferences.get('diet', 'balanced')
            foods_to_avoid = preferences.get('foodsToAvoid', [])
            additional = preferences.get('additional_considerations', '')

        print(f"   Diet: {diet}")
        print(f"   Foods to avoid: {foods_to_avoid}")
        print(f"   Additional: {additional[:50] if additional else 'None'}...")

        prompt = f"""
Hi NutriWise AI, I need a meal plan for Day {day_number} of my 7-day weekly plan.

**CONTEXT:**
- This is day {day_number}/7 of weekly_plan_id: {weekly_plan_id}
- **CRITICAL:** Call get_previous_recipes_in_week({weekly_plan_id}) FIRST to see what recipes I've already had
- Avoid repeating any recipes from previous days

**My Daily Targets:**
- Calories: {daily_targets['calories']}
- Protein: {daily_targets['protein']}g
- Fat: {daily_targets['fat']}g
- Carbs: {daily_targets['carbs']}g

**Dietary Preference:** {diet}
**Foods to Avoid:** {foods_to_avoid}
**Additional Preferences:** {additional}

**YOUR TASK:**
1. **FIRST:** Call get_previous_recipes_in_week({weekly_plan_id}) to check what recipes were used
2. Calculate meal targets (20% breakfast, 32.5% lunch, 32.5% dinner, 15% snacks)
3. Search for recipes that are DIFFERENT from previous days
4. Return the meal_plan JSON with recipe_id included

**IMPORTANT:**
- Do NOT call save_meal_plan (this is a weekly plan, not a preview)
- Return ONLY the meal_plan JSON structure
- Include recipe_id for each meal
"""
        print(f"   ✅ Prompt built successfully")
    except AttributeError as prompt_error:
        print(f"   ❌ AttributeError building prompt: {str(prompt_error)}")
        print(f"   preferences type: {type(preferences)}")
        print(f"   preferences value: {preferences}")
        import traceback
        traceback.print_exc()
        raise
    except Exception as prompt_error:
        print(f"   ❌ ERROR building prompt: {str(prompt_error)}")
        import traceback
        traceback.print_exc()
        raise
    
    # 3. Call your EXISTING agent function with weekly prompt
    print(f"🤖 Calling agent for day {day_number}...")
    print(f"   Using weekly_day_system_prompt (use_weekly_prompt=True)")

    try:
        agent_response = generate_meal_plan_with_agent(prompt, use_weekly_prompt=True)

        # Check if we got an empty response
        if agent_response == "Agent returned an empty response.":
            print(f"⚠️ Agent returned empty response, retrying with simplified prompt...")

            # Retry with simpler prompt
            simplified_prompt = f"""
Create a meal plan for Day {day_number}.

Daily Targets: {daily_targets['calories']} calories, {daily_targets['protein']}g protein, {daily_targets['fat']}g fat, {daily_targets['carbs']}g carbs
Diet: {diet}

Return ONLY the meal_plan JSON with recipe_id for each meal.
"""
            agent_response = generate_meal_plan_with_agent(simplified_prompt, use_weekly_prompt=True)

            if agent_response == "Agent returned an empty response.":
                raise ValueError(f"Agent failed to generate meal plan for day {day_number} after retry")

    except Exception as agent_error:
        print(f"❌ Agent error for day {day_number}: {str(agent_error)}")
        raise

    # 4. Parse response and insert meals
    print(f"   Parsing agent response...")
    try:
        meal_plan_json = extract_meal_plan_from_response(agent_response)
        print(f"   ✅ Meal plan JSON extracted successfully")
    except ValueError as parse_error:
        print(f"   ❌ Failed to parse agent response: {str(parse_error)}")
        print(f"   Response preview: {agent_response[:300]}...")
        raise

    print(f"   Inserting meals into database...")
    insert_meals_from_json(daily_plan_id, meal_plan_json)

    print(f"✅ Day {day_number} completed with {len(meal_plan_json.get('meal_plan', {}))} meals")


def extract_meal_plan_from_response(agent_response: str) -> dict:
    """
    Extract JSON meal plan from agent's response.
    Agent might return text + JSON, so we need to parse it.
    """
    import re

    print(f"📋 Extracting meal plan from response...")
    print(f"   Response length: {len(agent_response)} characters")
    print(f"   Response preview: {agent_response[:200]}...")

    # Try to find JSON in code blocks (use greedy matching to capture full JSON)
    json_match = re.search(r'```json\s*(\{.*\})\s*```', agent_response, re.DOTALL)
    if json_match:
        print(f"   ✅ Found JSON in code block")
        json_str = json_match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON decode error: {str(e)}")
            print(f"   Problematic JSON preview: {json_str[:300]}...")
            raise ValueError(f"Invalid JSON in code block: {str(e)}")

    # Try to find raw JSON (greedy match for nested structures)
    json_match = re.search(r'\{[^{}]*"meal_plan"[^{}]*\{.*\}\s*\}', agent_response, re.DOTALL)
    if json_match:
        print(f"   ✅ Found raw JSON")
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON decode error: {str(e)}")
            raise ValueError(f"Invalid raw JSON: {str(e)}")

    # If we can't find JSON, raise error with more context
    print(f"   ❌ No valid JSON found in response")
    raise ValueError(f"Could not extract meal plan JSON from agent response: {agent_response[:500]}")


def insert_meals_from_json(daily_plan_id: int, meal_plan_json: dict):
    """
    Parse the agent's meal plan JSON and insert into meals table.
    
    Includes a defensive check to handle cases where the LLM returns 'null'
    or an incorrect type for a meal entry.
    """
    meal_plan = meal_plan_json.get('meal_plan', {})
    
    meals_to_insert = []
    
    meal_type_map = {
        'Breakfast': 'breakfast',
        'Lunch': 'lunch',
        'Dinner': 'dinner',
        'Snack 1': 'snack',
        'Snack 2': 'snack',
    }
    
    snack_order = 1
    
    for meal_name, meal_data in meal_plan.items():
        if meal_name in ['Daily Totals', 'distribution']:
            continue
        
        # ===================================================
        # 🛑 CRITICAL FIX: Ensure meal_data is a dictionary
        # This prevents the 'NoneType' object has no attribute 'get' error
        # ===================================================
        if not isinstance(meal_data, dict):
            print(f"❌ Skipping {meal_name}: Expected dictionary for meal data, but received {type(meal_data)}. LLM likely returned 'null' or a string.")
            continue
        # ===================================================
        
        meal_type = meal_type_map.get(meal_name)
        if not meal_type:
            print(f"⚠️ Unknown meal type: {meal_name}, skipping")
            continue
        
        # Extract data from agent response
        # This line (which was line 666) is now safe
        recipe_id = meal_data.get('recipe_id')
        if not recipe_id:
            print(f"❌ Missing recipe_id for {meal_name}, skipping")
            continue
        
        # Ensure robust type conversion for servings and nutrition
        try:
            servings = float(meal_data.get('servings', 1.0))
        except (TypeError, ValueError):
            print(f"⚠️ Invalid servings value for {meal_name}: {meal_data.get('servings')}. Defaulting to 1.0.")
            servings = 1.0
            
        total_nutrition = meal_data.get('total_nutrition', {})
        
        meal_record = {
            'daily_plan_id': daily_plan_id,
            'meal_type': meal_type,
            'meal_order': snack_order if meal_type == 'snack' else 1,
            'recipe_id': int(recipe_id),
            'servings': round(servings, 2),
            'actual_calories': round(total_nutrition.get('calories', 0)),
            'actual_protein': round(total_nutrition.get('protein', 0), 1),
            'actual_carbs': round(total_nutrition.get('carbohydrates', 0), 1),
            'actual_fat': round(total_nutrition.get('fat', 0), 1),
        }
        
        meals_to_insert.append(meal_record)
        
        if meal_type == 'snack':
            snack_order += 1
    
    # Bulk insert all meals
    if meals_to_insert:
        supabase.table('meals').insert(meals_to_insert).execute()
        print(f"✅ Inserted {len(meals_to_insert)} meals")
    else:
        # If the LLM failed to generate any valid meals, we should raise an error
        # to prevent the daily plan from being marked as complete but empty.
        raise ValueError("No valid meals to insert after parsing agent response.")


def get_next_monday():
    """Get the date of next Monday"""
    from datetime import date, timedelta
    today = date.today()
    days_ahead = 0 - today.weekday()  # Monday is 0
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)