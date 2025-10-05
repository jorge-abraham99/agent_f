import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from fastapi import Depends
from app.services.agent_service import map_workouts_to_activity_level
from app.models.schemas import MealPlanRequest
from app.models.user_logic import user

router = APIRouter(
    prefix="/public",
    tags=["public"]
)


@router.post("/calculate-targets", response_class=JSONResponse)
def calculate_nutritional_targets(request: MealPlanRequest):
    try:
        # Map workouts per week to activity level
        activity_level = map_workouts_to_activity_level(request.workouts_per_week)
        
        # Create user instance
        user_instance = user(
            sex=request.gender,
            height=request.height,
            age=request.age,
            weight=request.weight,
            activity_level=activity_level,
            desired_weight=request.weight_goal,
            planned_weekly_weight_loss=request.planned_weekly_weight_loss
        )
        
        # Build response - all calculations done by user_instance methods
        response_data = {
            "success": True,
            "data": {
                "nutritional_targets": {
                    "calories": round(user_instance.goal_based_bmr(request.goal)),
                    "protein_grams": round(user_instance.protein_intake(request.goal), 1),
                    "fat_grams": round(user_instance.fat_intake(request.goal), 1),
                    "carbs_grams": round(user_instance.carbs_intake(request.goal), 1)
                },
                "user_metrics": {
                    "tdee": round(user_instance.get_tdee()),
                    "activity_level": activity_level,
                    "goal": request.goal,
                    "diet": request.diet
                },
                "weight_goal_info": {
                    "current_weight": request.weight,
                    "goal_weight": request.weight_goal,
                    "total_weight_change_kg": round(request.weight - request.weight_goal, 2),
                    "planned_weekly_change_kg": round(user_instance.get_planned_weekly_weight_loss(), 2),

                }
            }
        }
        
      
        return JSONResponse(content=response_data, status_code=200)
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except NameError as ne:
        raise HTTPException(status_code=400, detail=str(ne))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")