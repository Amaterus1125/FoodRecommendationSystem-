from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Import your existing engine logic
from run import sheet_to_engine
from engine import recommend, check
from meals import recommend_meals

app = FastAPI(
    title="Nutrition Planner API",
    description="Backend API for generating daily and meal-specific nutrition plans."
)

# Enable CORS to allow any frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL (e.g., "http://localhost:3000")
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class PlanRequest(BaseModel):
    sheet: Dict[str, Any] = Field(..., description="The full JSON object structured like sheet.json")
    protein_level: str = Field(default="optimum", description="Must be 'minimum', 'optimum', or 'maximum'")
    meals: bool = Field(default=True, description="True for meal-wise split (Breakfast/Lunch/Snack/Dinner), False for daily list")
    supplements: bool = Field(default=False, description="Allow whey protein/supplements in the plan")

@app.post("/api/plan")
def generate_plan(request: PlanRequest):
    """
    Generate a nutrition plan based on the user's sheet.json data.
    """
    try:
        # 1. Parse the incoming JSON sheet into the internal engine format
        sheet = sheet_to_engine(request.sheet, request.protein_level)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid sheet data: {str(e)}")

    # 2. Run the optimizer based on the requested mode (meals vs daily)
    if request.meals:
        shares = request.sheet.get("preferences", {}).get("meals")
        result = recommend_meals(sheet, shares=shares, include_supplements=request.supplements)
    else:
        result = recommend(sheet, include_supplements=request.supplements)

    # 3. Handle optimizer failure
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=422, 
            detail=f"Optimizer could not find a viable plan. Status: {result.get('status')}. Try relaxing constraints."
        )

    # 4. Run automatic checks to ensure data validity (matching the 'AUTOMATIC CHECK' in the CLI)
    if request.meals:
        # Flatten the meals list for the checker
        flat_foods = [{"name": f["name"], "grams": f["grams"]} 
                      for meal_data in result["meals"].values() 
                      for f in meal_data["foods"]]
        to_check = {"foods": flat_foods, "coverage": result["coverage"]}
    else:
        to_check = result

    problems = check(sheet, to_check)
    
    # 5. Append validation results and return the payload to the frontend
    return {
        "success": True,
        "mode": "meals" if request.meals else "daily",
        "data": result,
        "validation": {
            "passed": len(problems) == 0,
            "problems": problems
        }
    }

@app.get("/")
def read_root():
    return {"message": "Welcome to the Nutrition Planner API. Go to /docs to test the endpoints."}


@app.get("/health")
def health_check():
    return {"status": "active", "message": "API is running."}
