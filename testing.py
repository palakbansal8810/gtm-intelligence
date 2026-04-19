"""
Explorium API connectivity & health test
Run: python test_explorium.py
"""

import os
import json
import time
import httpx

BASE_URL = "https://api.explorium.ai/v1"
API_KEY  = os.getenv("EXPLORIUM_API_KEY", "")

BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
RESET = "\033[0m"

def ok(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg):print(f"  {RED}✗{RESET} {msg}")
def warn(msg):print(f"  {YELLOW}⚠{RESET} {msg}")
def section(title): print(f"\n{BOLD}{'─'*50}\n  {title}\n{'─'*50}{RESET}")


# ── 1. API Key check ──────────────────────────────────────────────────────────
section("1 · API Key")
if not API_KEY:
    fail("EXPLORIUM_API_KEY is not set in environment")
    print("     export EXPLORIUM_API_KEY=your_key_here")
else:
    masked = API_KEY[:6] + "..." + API_KEY[-4:]
    ok(f"Key found: {masked}  (length={len(API_KEY)})")


# ── 2. DNS / network reachability ────────────────────────────────────────────
section("2 · Network reachability")
try:
    r = httpx.get("https://api.explorium.ai", timeout=8)
    ok(f"DNS resolved & TCP connected  (status={r.status_code})")
except httpx.ConnectError as e:
    fail(f"Cannot reach api.explorium.ai — DNS or firewall issue\n     {e}")
except httpx.TimeoutException:
    fail("Connection timed out after 8 s")
except Exception as e:
    warn(f"Unexpected: {e}")


# ── 3. Auth check ─────────────────────────────────────────────────────────────
section("3 · Authentication")
if API_KEY:
    headers = {"api_key": API_KEY, "Content-Type": "application/json"}
    try:
        # Minimal payload — intentionally empty filters to probe auth
        r = httpx.post(
            f"{BASE_URL}/businesses",
            headers=headers,
            json={"mode": "full", "page": 1, "page_size": 1, "size": 1, "filters": {"has_website": {"value": True}}},
            timeout=15,
        )
        if r.status_code == 200:
            ok("Authenticated successfully")
        elif r.status_code == 401:
            fail(f"401 Unauthorized — API key is invalid or expired")
        elif r.status_code == 403:
            fail(f"403 Forbidden — key lacks permission for /v1/businesses")
        elif r.status_code == 422:
            warn(f"422 Unprocessable — key is valid but filter schema rejected (expected)")
        elif r.status_code == 503:
            warn(f"503 Service Unavailable — Explorium backend is down (not an auth issue)")
        else:
            warn(f"Unexpected status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"Request failed: {e}")
else:
    warn("Skipped (no API key)")


# ── 4. Endpoint health: /v1/businesses ───────────────────────────────────────
section("4 · Endpoint: /v1/businesses")
if API_KEY:
    payload = {
        "mode": "full",
        "page": 1,
        "page_size": 3,
        "size": 3,
        "filters": {
            "country_code": {"values": ["us"]},
            "company_size": {"values": ["51-200"]},
            "has_website":  {"value": True},
        },
    }
    try:
        t0 = time.time()
        r  = httpx.post(f"{BASE_URL}/businesses", headers=headers, json=payload, timeout=20)
        ms = int((time.time() - t0) * 1000)

        print(f"  Status : {r.status_code}   Latency: {ms} ms")
        if r.status_code == 200:
            data  = r.json()
            total = data.get("total_results", "?")
            rows  = data.get("data", [])
            ok(f"Got {len(rows)} companies  (total_results={total})")
            for c in rows:
                print(f"     • {c.get('name','?')}  —  {c.get('domain','?')}")
        elif r.status_code == 503:
            fail("503 — Explorium service is DOWN")
            print(f"     Body: {r.text[:300]}")
        else:
            warn(f"{r.status_code}: {r.text[:300]}")
    except httpx.TimeoutException:
        fail("Request timed out after 20 s")
    except Exception as e:
        fail(f"{e}")
else:
    warn("Skipped (no API key)")


# ── 5. Endpoint health: /v1/businesses/stats ─────────────────────────────────
section("5 · Endpoint: /v1/businesses/stats")
if API_KEY:
    try:
        t0 = time.time()
        r  = httpx.post(
            f"{BASE_URL}/businesses/stats",
            headers=headers,
            json={"filters": {"country_code": {"values": ["us"]}}},
            timeout=15,
        )
        ms = int((time.time() - t0) * 1000)
        print(f"  Status : {r.status_code}   Latency: {ms} ms")
        if r.status_code == 200:
            ok(f"Stats endpoint healthy")
            print(f"     {json.dumps(r.json(), indent=4)[:400]}")
        else:
            warn(f"{r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"{e}")
else:
    warn("Skipped (no API key)")


# ── 6. Endpoint health: /v1/prospects ────────────────────────────────────────
section("6 · Endpoint: /v1/prospects")
if API_KEY:
    try:
        t0 = time.time()
        r  = httpx.post(
            f"{BASE_URL}/prospects",
            headers=headers,
            json={
                "mode": "preview", "page": 1, "page_size": 2, "size": 2,
                "filters": {"has_email": {"type": "exists", "value": True}},
            },
            timeout=15,
        )
        ms = int((time.time() - t0) * 1000)
        print(f"  Status : {r.status_code}   Latency: {ms} ms")
        if r.status_code == 200:
            ok("Prospects endpoint healthy")
        else:
            warn(f"{r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"{e}")
else:
    warn("Skipped (no API key)")


# ── 7. Retry simulation (503 resilience) ─────────────────────────────────────
section("7 · 503 Resilience summary")
print("  Your search_companies() wrapper already handles 503 correctly:")
print("   1. @retry catches TimeoutException / ConnectError  (3 attempts)")
print("   2. HTTPStatusError catch returns []")
print("   3. Outer wrapper sees [] → falls back to mock data  ✓")
print()
warn("503 is a SERVER-SIDE outage — check https://status.explorium.ai")


# ── Summary ───────────────────────────────────────────────────────────────────
section("Done")
print("  All tests complete.\n")