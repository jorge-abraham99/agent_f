import os
from fastapi import HTTPException
from google import genai
from google.genai import types
from dotenv import load_dotenv
import json

from app.core.prompts import system_prompt
from app.tools.call_function import call_function

# Import the actual functions we will be describing and calling
from app.tools.database_tools import search_recipes, save_meal_plan, get_current_meal_plan
from app.tools.calculator import calculate

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
                        "user_id": types.Schema(type=types.Type.STRING, description="The user's unique identifier (UUID)."),
                        "plan_data": types.Schema(type=types.Type.OBJECT, description="The complete JSON object of the meal plan."),
                        "user_targets": types.Schema(type=types.Type.OBJECT, description="A JSON object of the user's nutritional targets.")
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

def generate_meal_plan_with_agent(prompt: str) -> str:
    """Generate meal plan using the AI agent with detailed logging."""
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not found")

    client = genai.Client(api_key=api_key)
    messages = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    
    max_iters = 40 # A reasonable limit
    iters = 0

    print("\n--- STARTING NEW AGENT SESSION ---")
    print(f"Initial Prompt: {prompt[:200]}...") # Print the start of the prompt

    while iters < max_iters:
        iters += 1
        print(f"\n--- AGENT ITERATION {iters} ---")

        try:
            # --- MAKE THE API CALL ---
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=messages,
                config=types.GenerateContentConfig(
                    tools=tools,
                    system_instruction=system_prompt
                ),
            )

            candidate = response.candidates[0]

            # ADD DIAGNOSTIC LOGGING
            print(f"Finish reason: {candidate.finish_reason}")
            print(f"Safety ratings: {candidate.safety_ratings if hasattr(candidate, 'safety_ratings') else 'N/A'}")
            print(f"Content present: {candidate.content is not None}")
            print(f"Parts present: {candidate.content.parts if candidate.content else 'No content'}")
            print(f"Message history length: {len(messages)}")

            # Try to see the raw response if available
            if hasattr(candidate, 'grounding_metadata'):
                print(f"Grounding metadata: {candidate.grounding_metadata}")
            if hasattr(response, 'prompt_feedback'):
                print(f"Prompt feedback: {response.prompt_feedback}")

            if not candidate.content or not candidate.content.parts:
                print("!!! Model returned an empty response. Stopping. !!!")
                print(f"Finish reason was: {candidate.finish_reason}")

                # Handle MALFORMED_FUNCTION_CALL specifically
                if str(candidate.finish_reason) == "FinishReason.MALFORMED_FUNCTION_CALL":
                    print("⚠️ Model generated a malformed function call. Attempting recovery...")
                    print(f"   Iteration {iters}: This might be a save_meal_plan call with invalid JSON structure.")

                    # Limit retries to prevent infinite loops
                    if iters >= max_iters - 5:
                        print("❌ Too many malformed calls near max iterations. Stopping.")
                        raise HTTPException(status_code=500, detail="Agent repeatedly generated malformed function calls")

                    # Provide feedback to retry with valid function call
                    messages.append(types.Content(
                        role="user",
                        parts=[types.Part(text="Error: Your last function call was malformed. Please retry with valid JSON arguments. For save_meal_plan, ensure plan_data is a properly formatted dict with all required fields. Double-check all quotes, commas, and brackets.")]
                    ))
                    continue  # Retry the loop

                return "Agent returned an empty response."

            messages.append(candidate.content)

            # --- PROCESS ALL PARTS, NOT JUST THE FIRST ONE ---
            parts = candidate.content.parts
            print(f"📦 Response has {len(parts)} part(s)")

            has_function_calls = False
            final_text = None

            for idx, part in enumerate(parts):
                print(f"\n  Part {idx}: ", end="")

                if hasattr(part, 'function_call') and part.function_call and part.function_call.name:
                    # This part is a function call
                    has_function_calls = True
                    function_call = part.function_call

                    print(f"Function call: '{function_call.name}'")
                    args_dict = dict(function_call.args)
                    print(f"    Arguments: {json.dumps(args_dict, indent=2)[:100]}...")

                    tool_response = call_function(function_call, verbose=True)
                    messages.append(tool_response)

                elif hasattr(part, 'text') and part.text:
                    # This part is text
                    print(f"Text: {part.text[:100]}...")
                    final_text = part.text
                else:
                    print(f"Unknown part type: {type(part)}")

            # If there were function calls, continue the loop
            if has_function_calls:
                print("✅ Processed function call(s), continuing...")
                continue

            # If we only got text and no function calls, we're done
            if final_text:
                print(f"✅ Agent finished. Final response: {final_text[:200]}...")
                return final_text

            # If we got here with no text and no function calls, something is wrong
            print("⚠️ Response had no function calls and no text. Continuing...")
            continue

        except Exception as e:
            print(f"!!! ERROR in agent loop: {e} !!!")
            import traceback
            traceback.print_exc() # Print the full traceback for detailed debugging
            raise HTTPException(status_code=500, detail=f"Error in agent processing: {str(e)}")

    print("!!! Maximum iterations reached. Stopping. !!!")
    raise HTTPException(status_code=508, detail="Maximum iterations reached, agent could not complete the request.")

