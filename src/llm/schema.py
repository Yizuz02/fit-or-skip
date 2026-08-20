from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class FitVerdict(str, Enum):
    STRONG_MATCH = "strong_match"
    POTENTIAL_MATCH = "potential_match"
    MISSING_SKILL = "missing_skill"
    MISSING_TECH = "missing_tech"
    SKIP = "skip"


class PrimaryDealbreaker(str, Enum):
    SENIORITY_MISMATCH = "seniority_mismatch"
    NON_ENGINEERING_ROLE = "non_engineering_role"
    LOCATION_OR_VISA_INELIGIBLE = "location_or_visa_ineligible"
    MISSING_CORE_SKILL = "missing_core_skill"
    UNSUPPORTED_TECH_STACK = "unsupported_tech_stack"
    NONE = "none"


class JobEvaluationOutput(BaseModel):
    fit_verdict: FitVerdict
    primary_dealbreaker: PrimaryDealbreaker
    missing_requirements: List[str] = Field(
        default_factory=list,
        description="List of specific missing skills/technologies (1-50 chars each)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="One concise sentence explaining the verdict",
    )