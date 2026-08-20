## Provider Abstraction & Portability

The integration relies strictly on three environment variables (LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL), decoupling the codebase from any single provider and allowing seamless switching between local models (e.g., Ollama) and cloud providers (e.g., OpenRouter) without changing a single line of application code.  