from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

from ..llm.prompt import get_latest_prompt_info
from ..llm.schema import FitVerdict, JobEvaluationOutput, PrimaryDealbreaker
from ..llm.model import evaluate_job, repair_job_evaluation
from ..llm.exceptions import (
    LLMNotFoundError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMAuthenticationError,
    LLMPermissionError,
    LLMBadRequestError,
)

load_dotenv()

app = FastAPI()

class JobInput(BaseModel):
    field: str = Field(..., min_length=1, max_length=100)
    job_title: str = Field(..., min_length=1, max_length=100)
    job_description: str = Field(..., min_length=100, max_length=5000)
    place: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(..., min_length=1, max_length=100)

def quarantine_log(job, raw_output: str, error_message: str, prompt_version: str):
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

    with open(quarantine_file, mode="a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def api_log(prompt_version: str, model: str, input_tokens:int, output_tokens:int, duration_ms: float, repair: bool):
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    api_log_file = logs_dir / "api_call.jsonl"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": prompt_version,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "needed_repair": repair,
    }

    with open(api_log_file, mode="a", encoding="utf-8") as f:
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

@app.post("/evaluate")
async def evaluate(job: JobInput):

    if os.getenv("LLM_ENABLED") == "false":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model output is disabled."
        )

    if os.getenv("LLM_STUB") == "1":
        return JobEvaluationOutput(
            fit_verdict=FitVerdict.STRONG_MATCH,
            primary_dealbreaker=PrimaryDealbreaker.NONE,
            missing_requirements=[],
            confidence=0.95,
            reason="[STUB] Job matches your AI engineering stack and remote eligibility."
        )

    try:
        _, prompt_version, _ = get_latest_prompt_info()

        start_time = time.perf_counter()
        raw_result, input_tokens, output_tokens = evaluate_job(job)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        try:
            result = JobEvaluationOutput.model_validate(raw_result)
            api_log(
                prompt_version=prompt_version,
                model=os.getenv("LLM_MODEL", ""),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                repair=False,
            )
            return result
        except (ValidationError, json.JSONDecodeError) as e:
            api_log(
                prompt_version=prompt_version,
                model=os.getenv("LLM_MODEL", ""),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                repair=True,
            )
            start_time = time.perf_counter()
            repaired_result, input_tokens, output_tokens = repair_job_evaluation(job, raw_result, str(e))
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            try:
                result = JobEvaluationOutput.model_validate(repaired_result)
                api_log(
                    prompt_version=prompt_version,
                    model=os.getenv("LLM_MODEL", ""),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    repair=False,
                )
                return result
            except (ValidationError, json.JSONDecodeError) as final_error:
                api_log(
                    prompt_version=prompt_version,
                    model=os.getenv("LLM_MODEL", ""),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    repair=True,
                )
                quarantine_log(job, raw_result, str(final_error), prompt_version)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Model output failed schema validation after repair attempt."
                )

    except (LLMAuthenticationError, LLMPermissionError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM provider authentication or permission configuration error.",
        )
    except LLMBadRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream LLM provider rejected the prompt payload: {exc}",
        )
    except LLMRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Upstream LLM rate limit reached: {exc}",
        )
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Upstream LLM inference timed out: {exc}",
        )
    except LLMConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach upstream LLM provider: {exc}",
        )

    except (LLMAuthenticationError, LLMPermissionError, LLMNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM provider configuration error: {exc}",
        )
    