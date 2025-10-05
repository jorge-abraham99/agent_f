from pydantic import BaseModel, EmailStr
from typing import Optional

# Your existing model, moved here
class MealPlanRequest(BaseModel):
    gender: str  # "male" or "female"
    height: float  # in cm
    age: int
    weight: float  # in kg
    workouts_per_week: int  # 0-7
    goal: str  # "Fat Loss", "Lean Gains", "General Health / Maintenance", "Build Muscle"
    diet: str  # e.g., "vegetarian", "keto", "mediterranean", etc.
    additional_considerations: Optional[str] = ""
    weight_goal: float  # desired weight in kg
    planned_weekly_weight_loss: float  # number of weeks to achieve the goal

# New models for Authentication (from the next task, but good to add now)
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str