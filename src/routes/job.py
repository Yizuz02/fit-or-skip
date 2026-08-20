import os
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from ..llm.schema import FitVerdict, JobEvaluationOutput, PrimaryDealbreaker

load_dotenv()

class JobInput(BaseModel):
    field: str = Field(..., min_length=1, max_length=100)
    job_title: str = Field(..., min_length=1, max_length=100)
    job_description: str = Field(..., min_length=100, max_length=5000)
    place: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(..., min_length=1, max_length=100)

app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Extract the first failing field and reason
    first_error = errors[0] if errors else {}
    loc_list = first_error.get("loc", [])
    filtered_parts = []

    for loc in loc_list:
        if loc != "body":
            filtered_parts.append(str(loc))

    field_name = " -> ".join(filtered_parts)
    msg = first_error.get("msg", "Invalid input")
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Bad Request",
            "field": field_name or "unknown",
            "message": f"Validation failed: {msg}",
            "details": errors
        }
    )

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/evaluate")
async def evaluate(job: JobInput):
    if os.getenv("LLM_STUB") == "1":
        return JobEvaluationOutput(
            fit_verdict=FitVerdict.STRONG_MATCH,
            primary_dealbreaker=PrimaryDealbreaker.NONE,
            missing_requirements=[],
            confidence=0.95,
            reason="[STUB] Job matches your AI engineering stack and remote eligibility."
        )

    # In later stages, the real LLM call logic will live here
    pass