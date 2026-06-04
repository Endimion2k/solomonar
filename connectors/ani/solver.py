"""Solver CAPTCHA (Cloudflare Turnstile) pentru portalul central ANI.

declaratii.integritate.eu protejează căutarea de declarații cu Turnstile (sitekey ANI_SITEKEY).
Solver real = serviciu PLĂTIT (CapSolver / 2captcha) → necesită CAPSOLVER_API_KEY.

Flux complet (cu cheie):
  1. solve_turnstile() → token (CapSolver AntiTurnstileTaskProxyLess)
  2. Camoufox: încarcă pagina → injectează token-ul în widget-ul Turnstile → trimite căutarea
  3. capturează endpoint-ul de rezultate (/api/...) + PDF-urile → parse avere + guard PII

Fără cheie, restul pipeline-ului (parser avere, guard PII, delta) e gata — vezi connectors/ani/.
Alternativă gratuită: declarațiile per-instituție (deja harvestate, 529, fără CAPTCHA).
"""

from __future__ import annotations

import os
import time

from romega_core.http import Client

CAPSOLVER_BASE = "https://api.capsolver.com"
ANI_URL = "https://declaratii.integritate.eu"
ANI_SITEKEY = "0x4AAAAAAA9DS4Z2J7giQ9cL"  # Turnstile sitekey ANI (capturat din challenge live)


def build_turnstile_task(website_url: str, website_key: str) -> dict:
    """Payload-ul CapSolver pentru un task Turnstile (proxyless)."""
    return {"type": "AntiTurnstileTaskProxyLess", "websiteURL": website_url, "websiteKey": website_key}


def solve_turnstile(
    website_url: str = ANI_URL,
    website_key: str = ANI_SITEKEY,
    api_key: str | None = None,
    client: Client | None = None,
    poll_timeout: int = 120,
) -> str:
    """Rezolvă Turnstile prin CapSolver → întoarce token-ul. Necesită CAPSOLVER_API_KEY."""
    api_key = api_key or os.environ.get("CAPSOLVER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "CAPSOLVER_API_KEY lipsește — solver-ul Turnstile e serviciu plătit (capsolver.com / 2captcha). "
            "Setează cheia ca să rulezi căutarea ANI; altfel folosește declarațiile per-instituție (gratis)."
        )
    client = client or Client(legacy_ssl=False, timeout=30)
    created = client.post(
        f"{CAPSOLVER_BASE}/createTask",
        json={"clientKey": api_key, "task": build_turnstile_task(website_url, website_key)},
    ).json()
    if created.get("errorId"):
        raise RuntimeError(f"CapSolver createTask: {created.get('errorDescription')}")
    task_id = created["taskId"]
    waited = 0
    while waited < poll_timeout:
        time.sleep(3)
        waited += 3
        res = client.post(
            f"{CAPSOLVER_BASE}/getTaskResult", json={"clientKey": api_key, "taskId": task_id}
        ).json()
        if res.get("status") == "ready":
            return res["solution"]["token"]
        if res.get("errorId"):
            raise RuntimeError(f"CapSolver getTaskResult: {res.get('errorDescription')}")
    raise TimeoutError("CapSolver timeout (Turnstile nerezolvat în timp)")
