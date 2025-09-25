import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv

from user import user
from prompts import system_prompt
from call_function import available_functions, call_function

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your specific domain
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods including OPTIONS, POST, GET, etc.
    allow_headers=["*"],  # Allows all headers
)

class MealPlanRequest(BaseModel):
    gender: str  # "male" or "female"
    height: float  # in cm
    age: int
    weight: float  # in kg
    workouts_per_week: int  # 0-7
    goal: str  # "Fat Loss", "Lean Gains", "General Health / Maintenance", "Build Muscle"
    diet: str  # e.g., "vegetarian", "keto", "mediterranean", etc.
    additional_considerations: Optional[str] = ""

def map_workouts_to_activity_level(workouts_per_week: int) -> str:
    """Map workouts per week to activity level"""
    if workouts_per_week <= 2:
        return "lightly active"
    elif workouts_per_week <= 5:
        return "moderately active"
    else:  # 6+
        return "extra active"

def generate_meal_plan_with_agent(prompt: str) -> str:
    """Generate meal plan using the AI agent"""
    load_dotenv()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not found in environment")
    
    client = genai.Client(api_key=api_key)
    
    messages = [
        types.Content(role="user", parts=[types.Part(text=prompt)]),
    ]
    
    max_iters = 60
    iters = 0
    
    while iters < max_iters:
        iters += 1
        
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=messages,
                config=types.GenerateContentConfig(
                    tools=[available_functions], 
                    system_instruction=system_prompt
                ),
            )
            
            if response.candidates:
                for candidate in response.candidates:
                    function_call_content = candidate.content
                    messages.append(function_call_content)
            
            if not response.function_calls:
                return response.text
            
            function_responses = []
            for function_call_part in response.function_calls:
                function_call_result = call_function(function_call_part, verbose=False)
                if (
                    not function_call_result.parts
                    or not function_call_result.parts[0].function_response
                ):
                    raise Exception("empty function call result")
                function_responses.append(function_call_result.parts[0])
            
            if not function_responses:
                raise Exception("no function responses generated")
            
            messages.append(types.Content(role="tool", parts=function_responses))
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error generating meal plan: {str(e)}")
    
    raise HTTPException(status_code=500, detail="Maximum iterations reached while generating meal plan")

@app.post("/generate_meal_plan", response_class=JSONResponse)
def generate_meal_plan(request: MealPlanRequest):
    """Generate a personalized meal plan based on user information"""
    try:
        # Map workouts per week to activity level
        activity_level = map_workouts_to_activity_level(request.workouts_per_week)
        
        # Create user instance
        user_instance = user(
            sex=request.gender,
            height=request.height,
            age=request.age,
            weight=request.weight,
            activity_level=activity_level
        )
        
        # Calculate nutritional targets
        goal_calories = round(user_instance.goal_based_bmr(request.goal))
        protein_grams = round(user_instance.protein_intake(request.goal), 1)
        fat_grams = round(user_instance.fat_intake(request.goal), 1)
        carbs_grams = round(user_instance.carbs_intake(request.goal), 1)
        
        # Create prompt for the AI agent
        prompt = f"""
Hi NutriWise AI, I'd like you to create a personalized daily meal plan for me based on the following:

**Daily Targets:**
- Calories: {goal_calories}
- Protein: {protein_grams}g
- Fat: {fat_grams}g
- Carbs: {carbs_grams}g

**Dietary Preference:** {request.diet}

**Additional Preferences & Considerations:**
{request.additional_considerations}

Please follow your standard meal distribution (Breakfast 20%, Lunch 32.5%, Dinner 32.5%, Snacks 15%) unless I've specified otherwise above. If I mentioned skipping meals, adjusting sizes, or timing (like intermittent fasting), please override defaults accordingly and note it in the plan.

Also, prioritize matching my macros in this order: Calories → Protein → Carbs → Fats. If exact matches aren't possible, optimize for my primary goal (e.g., high protein, low carb, etc.).

I'd like you to:
1. Calculate exact calorie & macro targets per meal.
2. Search for suitable recipes using your tools (respecting my diet & preferences).
3. Adjust serving sizes as needed to hit targets.
4. Validate totals and show variance analysis.

Thank you! I trust your methodical approach!
"""
        
        # Generate meal plan using the agent
        agent_response = generate_meal_plan_with_agent(prompt)
        
        # Try to read the generated meal_plan.json file
        meal_plan_path = os.path.join(os.path.dirname(__file__), "meal_plan.json")
        meal_plan_data = None
        
        if os.path.exists(meal_plan_path):
            try:
                with open(meal_plan_path, "r") as f:
                    meal_plan_data = json.load(f)
            except Exception:
                pass
        
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating meal plan: {str(e)}")

@app.get("/meal_plan", response_class=JSONResponse)
def get_meal_plan():
    """Get the current meal plan from meal_plan.json"""
    file_path = os.path.join(os.path.dirname(__file__), "meal_plan.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="meal_plan.json not found")
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# for local use only
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001)