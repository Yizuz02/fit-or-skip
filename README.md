## Provider Abstraction & Portability

The integration relies strictly on three environment variables (LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL), decoupling the codebase from any single provider and allowing seamless switching between local models (e.g., Ollama) and cloud providers (e.g., OpenRouter) without changing a single line of application code.  


## Testing the Endpoint

Use these `curl` commands to test input validation and stub mode:

* **1. Valid Request (Expected: HTTP 200)**


Passes all required fields and length constraints.



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

*Expected Response (Stub Mode)*:

```json
{
  "fit_verdict": "strong_match",
  "primary_dealbreaker": "none",
  "missing_requirements": [],
  "confidence": 0.95,
  "reason": "[STUB] Job matches your AI engineering stack and remote eligibility."
}
```

* **2. Missing Field (Expected: HTTP 400)**


**Why it fails:** The mandatory `job_description` field is omitted from the request body.



```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "field": "AI Engineering",
    "job_title": "Junior AI Engineer",
    "place": "Remote (Mexico)",
    "company_name": "Tech Corp"
  }'
```

*Expected Response*:

```json
{
  "error": "Bad Request",
  "field": "job_description",
  "message": "Validation failed: Field required",
  "details": ...
}
```

* **3. Text Too Short (Expected: HTTP 400)**


**Why it fails:** The `job_description` string is under the minimum requirement of 100 characters.



```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "field": "AI Engineering",
    "job_title": "Junior AI Engineer",
    "job_description": "Too short description.",
    "place": "Remote (Mexico)",
    "company_name": "Tech Corp"
  }'
```

*Expected Response*:

```json
{
  "error": "Bad Request",
  "field": "job_description",
  "message": "Validation failed: String should have at least 100 characters",
  "details": ...
}
```