# fit-or-skip

A tiny service that reads a job posting and tells you whether it is worth applying to — or whether you should skip it. You send it a job title, description, location, and company, and it compares the posting against a fixed candidate profile (an AI Engineering student: Python, C++, JavaScript, SQL, RAG/LangChain/LLM experience, based in Mexico, eligible for Mexico-based or 100% remote roles only). It replies with a verdict (`strong_match`, `potential_match`, `missing_skill`, `missing_tech`, or `skip`), the single biggest blocker if there is one, any specific skills or technologies that are missing, a confidence score, and a one-sentence reason. It is deliberately strict: senior roles, non-engineering roles, and international on-site jobs without visa sponsorship are always `skip`, and when a posting is too vague to judge, it says `skip` instead of guessing.

## Try it: curl and the exact response

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "field": "AI Engineering",
    "job_title": "Junior AI Engineer",
    "job_description": "We are seeking a Junior AI Engineer to build LLM pipelines and backend APIs with Python and LangChain. Strong SQL and Node.js skills are a plus. Remote role for Mexico candidates.",
    "place": "Remote (Mexico)",
    "company_name": "Tech Corp"
  }'
```

Exact response produced by this endpoint (captured from a live run):

```json
{"fit_verdict":"strong_match","primary_dealbreaker":"none","missing_requirements":[],"confidence":1.0,"reason":"The role perfectly aligns with the candidate's focus on LLM pipelines, Python, and LangChain within a remote context."}
```

## The job card

**What it does:** Evaluates a raw job posting description against an AI Engineering student profile to determine role suitability, detect hard blockers, and isolate missing technical requirements.

**Input:**

```json
{
  "job_description": "string, 100-5000 characters"
}
```

**Output:**

```json
{
  "fit_verdict": "one of [strong_match | potential_match | missing_skill | missing_tech | skip]",
  "primary_dealbreaker": "one of [seniority_mismatch | non_engineering_role | location_or_visa_ineligible | missing_core_skill | unsupported_tech_stack | none]",
  "missing_requirements": "array of strings, each 1-50 characters naming specific missing skills/technologies, empty array [] if none",
  "confidence": "number between 0.0 and 1.0",
  "reason": "one concise sentence explaining the verdict"
}
```

**It must never:**

- Return free-form text outside the exact JSON schema.
- Invent categories outside the specified enums.
- Assume a non-remote US/international job is eligible without explicit visa sponsorship or remote authorization for Mexico.
- Classify Senior, Lead, or Staff roles as anything other than "skip".

**When unsure it should:**

- Return `fit_verdict` "skip" with `primary_dealbreaker` "unsupported_tech_stack", empty `missing_requirements` `[]`, and confidence below 0.5, rather than guessing a match.

## Provider, model, and swapping providers

The service runs against **Ollama (self-hosted)** serving **`gemma4:e2b`** (Gemma 4 5.1B, Q4_K_M), an OpenAI-compatible local endpoint. No code changes are needed to switch providers — the integration depends strictly on three environment variables:

| Variable | Purpose | Local (this repo) example | OpenRouter example |
|---|---|---|---|
| `LLM_BASE_URL` | Base URL of the OpenAI-compatible API | `http://localhost:11434/v1/` | `https://openrouter.ai/api/v1` |
| `LLM_API_KEY` | API key (ignored by Ollama, required by hosted providers) | `ollama` | `sk-or-...` |
| `LLM_MODEL` | Model name to call | `gemma4:e2b` | e.g. `google/gemma-3-...` |

**Retry policy:** retries are handled by the application's own logic, and the OpenAI SDK's built-in retries are explicitly disabled (`max_retries=0`) so we never make six calls when we think we made one. The custom logic retries only transient failures — timeouts, HTTP 429, and HTTP 5xx — with exponential backoff plus jitter (≈1s, 2s, 4s, each plus a small random amount), and honors a `Retry-After` header on 429s instead of guessing. It never retries 400, 401, or 403: a bad key or bad payload will still be bad four seconds later, and on a metered free tier every pointless retry burns real quota.

## How to run locally

```bash
python -m venv .venv && source .venv/bin/activate   # once
pip install -r requirements.txt                     # once
cp .env.example .env && fill in the three LLM_* vars
uvicorn src.main:app --reload                       # serves http://127.0.0.1:8000
```

Project layout:

```
src/main.py            FastAPI app entry point
src/routes/job.py      POST /evaluate, input validation, repair-once + quarantine
src/llm/model.py       provider client, retry policy, repair call
src/llm/prompt.py      picks the highest evaluate-job-vN.md
src/llm/schema.py      pydantic output schema + enums
src/llm/exceptions.py  domain exceptions mapped from provider errors
prompts/               versioned system prompts (evaluate-job-v2.md is active)
evals/                 eval set + runner (see below)
logs/                  api_call.jsonl (tokens/cost) and quarantine.jsonl
```

## Eval: does it actually work?

`evals/cases.json` holds eight hand-written cases, each with the answer we believe is correct: two hard-blocker seniority/location cases, a non-engineering role, a strong match, a borderline match, a missing-technology case, a missing-credential case, and one deliberately ambiguous posting that must hit the "when unsure" rule (skip, `unsupported_tech_stack`, confidence below 0.5). `evals/run_eval.py` runs all eight through the live endpoint and reports the percentage on the key field (`fit_verdict`) plus the list of failures.

**Result (2026-08-21, prompt version `evaluate-job-v2`, model `gemma4:e2b`):**

```
Score on key field 'fit_verdict': 6/8 (75%)
Strict (verdict + dealbreaker + confidence + missing_requirements): 5/8 (62%)
```

Run twice (both runs identical: 6/8). Failures:

- `02_potential_match`: expected `potential_match`, got `strong_match` — the model judged the Python/Node/SQL stack as a core-stack match despite the optional Redis/Kafka extras.
- `04_missing_skill`: expected `missing_skill`, got `potential_match` — the "must have published research" requirement was treated as soft, not as a hard credential gap.

A secondary warning: the ambiguous case (08) correctly returns `skip` with low confidence but occasionally lists non-empty `missing_requirements` (`["no technical requirements specified"]`) instead of `[]`, which violates the "empty array when none" guardrail.

That number is the point: it is the baseline to compare against. The next prompt change gets judged by whether 6/8 moves, not by how good the change *feels*.

## Cost

One call logged in `logs/api_call.jsonl` (2026-08-21, `gemma4:e2b`, no repair needed): **1,547 input tokens + 615 output tokens, 5.7s, $0.00** — inference runs on our own hardware, so there is no per-token billing. Estimate for 10,000 requests/day: **$0.00 in API fees on local Ollama (electricity aside)**.

For reference, if the same workload were hosted with DeepSeek instead, the list prices are:

| MODEL | deepseek-v4-flash | deepseek-v4-pro |
|---|---|---|
| 1M INPUT TOKENS (CACHE HIT) OFF-PEAK | $0.007 | $0.022 |
| 1M INPUT TOKENS (CACHE HIT) PEAK | $0.014 | $0.044 |
| 1M INPUT TOKENS (CACHE MISS) OFF-PEAK | $0.22 | $0.66 |
| 1M INPUT TOKENS (CACHE MISS) PEAK | $0.44 | $1.32 |
| 1M OUTPUT TOKENS OFF-PEAK | $0.66 | $1.98 |
| 1M OUTPUT TOKENS PEAK | $1.32 | $3.96 |

Estimated cost for one call (1,547 input + 615 output tokens) and for 10,000 calls/day at those prices:

| Model | Scenario | 1 call | 10,000 calls/day |
|---|---|---|---|
| deepseek-v4-flash | off-peak, cache miss | $0.000746 | $7.46 |
| deepseek-v4-flash | peak, cache miss | $0.001492 | $14.92 |
| deepseek-v4-flash | off-peak, cache hit | $0.000417 | $4.17 |
| deepseek-v4-flash | peak, cache hit | $0.000833 | $8.33 |
| deepseek-v4-pro | off-peak, cache miss | $0.002239 | $22.39 |
| deepseek-v4-pro | peak, cache miss | $0.004477 | $44.77 |
| deepseek-v4-pro | off-peak, cache hit | $0.001252 | $12.52 |
| deepseek-v4-pro | peak, cache hit | $0.002503 | $25.03 |

The system prompt is byte-identical on every request, so in practice most of the input is cacheable and the cache-hit rows are the realistic ones.

## What I'd fix with another day

Add few-shot examples for `potential_match` and `missing_skill` — the two verdicts that failed — and reinforce in the prompt that a stated credential requirement (e.g., "must have published research") is a hard blocker, then re-run the same eight cases to see whether 6/8 moves.

## Internship

This project was developed as part of the FlyRank AI Internship.
