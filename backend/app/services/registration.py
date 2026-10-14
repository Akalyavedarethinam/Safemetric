"""
Rule 27 registration verification - integration point for an authoritative registry.

Default: no authoritative source is configured -> {"available": False}.
When REGISTRATION_API_URL is set, a GET request is made to
    {REGISTRATION_API_URL}?number=<registration number>
with header `Authorization: Bearer <REGISTRATION_API_KEY>` and is expected to return JSON
    {"valid": true|false, "detail": "...", "holder": "..."}
Adapt `HttpRegistrationVerifier.verify` to the official API contract when it becomes available.
"""
from __future__ import annotations

import logging

from .. import config

log = logging.getLogger("safemetric.registration")


class NullRegistrationVerifier:
    source = "none"

    def verify(self, number: str) -> dict:
        return {"available": False, "source": self.source,
                "detail": "No authoritative registration source is configured (set REGISTRATION_API_URL)."}


class HttpRegistrationVerifier:
    source = "configured registration API"

    def __init__(self, url: str, key: str = ""):
        self.url, self.key = url, key

    def verify(self, number: str) -> dict:
        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
            r = httpx.get(self.url, params={"number": number}, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            return {"available": True, "valid": bool(data.get("valid")), "detail": data.get("detail", ""),
                    "holder": data.get("holder", ""), "source": self.source}
        except Exception as exc:
            log.warning("registration lookup failed: %s", exc)
            return {"available": False, "source": self.source, "detail": "Registration service unreachable."}


def get_verifier():
    if config.REGISTRATION_API_URL:
        return HttpRegistrationVerifier(config.REGISTRATION_API_URL, config.REGISTRATION_API_KEY)
    return NullRegistrationVerifier()
