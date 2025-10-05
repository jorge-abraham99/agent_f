from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import meal_plans, auth,public # We will add 'auth' router here later

app = FastAPI(title="NutriWise AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the routers from other files
app.include_router(meal_plans.router)
# We will add: app.include_router(auth.router) in the next task

app.include_router(auth.router) 

app.include_router(public.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to NutriWise AI"}