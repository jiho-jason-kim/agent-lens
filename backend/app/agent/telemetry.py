"""Safe diagnostics exclude exception bodies and provider credentials."""
import httpx


def error_category(error):
    status = getattr(error, 'status_code', None)
    if status is None and isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
    if status in (401, 403):
        return 'authentication'
    if status == 429:
        return 'rate_limit'
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or 'Timeout' in type(error).__name__:
        return 'timeout'
    if status and status >= 500:
        return 'provider_unavailable'
    if status == 400:
        return 'invalid_request'
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return 'invalid_output'
    return 'provider_error'
