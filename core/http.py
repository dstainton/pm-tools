"""HTTP calls that honor a rate limit once.

Jira answers 429 with Retry-After. Wait that long, try the same call one
more time, and then fail with a message that says it was a rate limit.
"""

import time

import requests


def retry_after_seconds(response):
    """Seconds to wait. Missing or unreadable headers wait one second."""
    raw = (response.headers.get("Retry-After") or "").strip()
    try:
        seconds = int(float(raw))
    except (TypeError, ValueError):
        seconds = 1
    return max(0, min(seconds, 60))


def send(method, url, **kwargs):
    """Perform one HTTP call. On 429, wait and try exactly once more."""
    kwargs.setdefault("timeout", 60)
    response = requests.request(method, url, **kwargs)
    if response.status_code != 429:
        return response
    wait = retry_after_seconds(response)
    time.sleep(wait)
    response = requests.request(method, url, **kwargs)
    if response.status_code == 429:
        raise requests.HTTPError(
            f"Rate limit (429) after waiting {wait}s. Try again shortly.",
            response=response)
    return response
