import json
from google.genai import types

# 1. Import the actual, callable Python functions
from app.tools.database_tools import search_recipes, save_meal_plan, get_current_meal_plan,fuzzy_search_rows
from app.tools.calculator import calculate

# 2. Create the simple Python dictionary for execution mapping.
AVAILABLE_FUNCTIONS = {
    "save_meal_plan": save_meal_plan,
    "get_current_meal_plan": get_current_meal_plan,
    "calculate": calculate,
    "fuzzy_search_rows": fuzzy_search_rows,
}

# 3. Define the dispatcher function that uses the dictionary.
def call_function(function_call: types.FunctionCall, verbose: bool = False) -> types.Content:
    function_name = function_call.name
    function_to_call = AVAILABLE_FUNCTIONS.get(function_name)

    if not function_to_call:
        raise ValueError(f"Function '{function_name}' is not registered in AVAILABLE_FUNCTIONS.")

    function_args = dict(function_call.args)

    if verbose:
        print(f"--- Calling Tool: {function_name} with args: {function_args} ---")
        
    function_response_content = function_to_call(**function_args)
    
    if verbose:
        print(f"--- Tool Response: {function_response_content} ---")

    # Wrap the response for the genai library
    return types.Content(
        role="tool",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name=function_name,
                    response={"result": function_response_content},
                )
            )
        ],
    )
