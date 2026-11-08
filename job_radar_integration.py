"""Optional Job Radar callback for the Resume-Builder scorer sidecar.

When a tailoring run finishes (its result is published and the DOCX package is
written), Resume-Builder can tell Job Radar so the application lands in Job
Radar's tracking without anyone touching the Excel tracker. The callback is:

  POST {JOB_RADAR_URL}/api/v1/jobs/mark-applied
       {"company": ..., "url": ..., "title": ..., "folder": ...}

Contract with the caller (scorer_server.py):
    - fire-and-forget: every failure is caught, logged and returned as
      ``{"ok": False, "message": ...}`` - a callback problem must never fail
      or retry a run that actually succeeded;
    - inert by default: with JOB_RADAR_URL unset, the helper answers
      ``{"ok": False, "message": "JOB_RADAR_URL not configured"}`` without
      touching the network, so standalone use is unchanged;
    - no resume content or JD text is ever sent: only the company, the posting
      URL, the role title and the output folder name.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

log = logging.getLogger("scorer.jobradar")

# Read once at import; docker-compose.yml sets this to http://app:8090.
JOB_RADAR_URL = os.getenv("JOB_RADAR_URL", "").rstrip("/")

_CALLBACK_TIMEOUT = 10  # seconds


def is_configured() -> bool:
    """Whether the callback is switched on at all."""
    return bool(JOB_RADAR_URL)


def mark_applied(
    company: Optional[str],
    url: Optional[str],
    title: Optional[str],
    folder: Optional[str],
) -> Dict[str, Any]:
    """Record one finished application in Job Radar. Never raises.

    Uses only the stdlib so the callback works in the scorer image without
    any extra dependency.
    """
    if not JOB_RADAR_URL:
        return {"ok": False, "message": "JOB_RADAR_URL not configured"}

    payload = json.dumps({
        "company": company or "",
        "url": url or "",
        "title": title or "",
        "folder": folder or "",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{JOB_RADAR_URL}/api/v1/jobs/mark-applied",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_CALLBACK_TIMEOUT) as resp:
            try:
                body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
            except ValueError:
                body = {}
            if isinstance(body, dict):
                body.setdefault("ok", True)
                return body
            return {"ok": True}
    except urllib.error.HTTPError as exc:
        log.warning("Job Radar callback failed: HTTP %s", exc.code)
        return {"ok": False, "message": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 -- fire-and-forget by contract
        log.warning("Job Radar callback failed: %s", exc)
        return {"ok": False, "message": str(exc)}
