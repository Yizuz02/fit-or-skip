from datetime import datetime, timezone
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

from ..llm.schema import FitVerdict, JobEvaluationOutput, PrimaryDealbreaker
from ..llm.model import evaluate_job, repair_job_evaluation

load_dotenv()

app = FastAPI()

class JobInput(BaseModel):
    field: str = Field(..., min_length=1, max_length=100)
    job_title: str = Field(..., min_length=1, max_length=100)
    job_description: str = Field(..., min_length=100, max_length=5000)
    place: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(..., min_length=1, max_length=100)

def quarantine_log(job, raw_output: str, error_message: str, prompt_version: str = "evaluate-job-v1"):
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    quarantine_file = logs_dir / "quarantine.jsonl"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": prompt_version,
        "input": job.model_dump() if hasattr(job, "model_dump") else dict(job),
        "raw_output": raw_output,
        "error": error_message
    }

    # Open with mode="a" (append) to add a new line without overwriting previous entries
    with open(quarantine_file, mode="a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


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

    raw_result = evaluate_job(job)

    try:
        return JobEvaluationOutput.model_validate(raw_result)
    except (ValidationError, json.JSONDecodeError) as e:
        repaired_result = repair_job_evaluation(job, raw_result, str(e))
        try:
            return JobEvaluationOutput.model_validate(repaired_result)
        except (ValidationError, json.JSONDecodeError) as final_error:
            quarantine_log(job, raw_result, str(final_error))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Model output failed schema validation after repair attempt."
            )