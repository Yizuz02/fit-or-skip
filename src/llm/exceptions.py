class LLMServiceError(Exception):
    """Base exception for all LLM service failures."""
    pass

class LLMTimeoutError(LLMServiceError):
    """Raised when the LLM provider times out."""
    pass

class LLMConnectionError(LLMServiceError):
    """Raised when connecting to the LLM provider fails."""
    pass

class LLMRateLimitError(LLMServiceError):
    """Raised when rate limits or quotas are hit """
    pass

class LLMAuthenticationError(LLMServiceError):
    """Raised when the API key or token is missing/invalid. """
    pass

class LLMPermissionError(LLMServiceError):
    """Raised when the account lacks access to the requested model/resource."""
    pass

class LLMBadRequestError(LLMServiceError):
    """Raised when the payload or parameters sent to the provider are invalid."""
    pass

class LLMNotFoundError(LLMServiceError):
    """Raised when the specified model or deployment is not found (permanent / 404)."""
    pass