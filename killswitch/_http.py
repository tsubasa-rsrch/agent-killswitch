"""HTTP client using only urllib (zero dependencies)."""

import json
import urllib.request
import urllib.error
from typing import Optional


def post_json(url: str, data: dict, api_key: str = "",
              timeout: int = 10) -> Optional[dict]:
    """POST JSON to url, return parsed response or None on failure."""
    body = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return None


def get_json(url: str, api_key: str = "",
             timeout: int = 10) -> Optional[dict]:
    """GET JSON from url, return parsed response or None on failure."""
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return None
