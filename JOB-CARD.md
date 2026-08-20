# Job Card: fit-or-skip

What it does: Evaluates a raw job posting description against an AI Engineering student profile to determine role suitability, detect hard blockers, and isolate missing technical requirements.

Input:
{
  "job_description": "string, 100-5000 characters"
}

Output:
{
  "fit_verdict": "one of [strong_match | potential_match | missing_skill | missing_tech | skip]",
  "primary_dealbreaker": "one of [seniority_mismatch | non_engineering_role | location_or_visa_ineligible | missing_core_skill | unsupported_tech_stack | none]",
  "missing_requirements": "array of strings, each 1-50 characters naming specific missing skills/technologies, empty array [] if none",
  "confidence": "number between 0.0 and 1.0",
  "reason": "one concise sentence explaining the verdict"
}

It must never:
- Return free-form text outside the exact JSON schema.
- Invent categories outside the specified enums.
- Assume a non-remote US/international job is eligible without explicit visa sponsorship or remote authorization for Mexico.
- Classify Senior, Lead, or Staff roles as anything other than "skip".

When unsure it should:
- Return fit_verdict "skip" with primary_dealbreaker "unsupported_tech_stack", empty missing_requirements [], and confidence below 0.5, rather than guessing a match.