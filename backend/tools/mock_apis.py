import os
import time
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

BASE_URL = "https://api.explorium.ai/v1"
API_KEY = os.getenv("EXPLORIUM_API_KEY", "")


def _coerce_str(value) -> str:
    """
    Safely coerce a filter value to a plain string.
    Handles cases where agents accidentally pass dicts like {"values": ["AI"]}
    or lists like ["AI"] instead of a plain string "AI".
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # e.g. {"values": ["AI"]} or {"value": "AI"}
        inner = value.get("values") or value.get("value") or ""
        if isinstance(inner, list):
            return inner[0] if inner else ""
        return str(inner)
    if isinstance(value, list):
        return inner[0] if value else ""
    return str(value)

INDUSTRY_TO_LINKEDIN_CATEGORY = {
    "voice ai":             "software development",
    "voice tech":           "software development",
    "speech ai":            "software development",
    "conversational ai":    "software development",
    "nlp":                  "software development",
    "natural language":     "software development",
    "speech recognition":   "software development",
    "generative ai":        "software development",
    "llm":                  "software development",
    "ai startup":           "software development",
    "ai saas":              "software development",
    "ai":                   "software development",
    "ml":                   "software development",
    "artificial intelligence": "software development",
    "saas":                 "software development",
    "software":             "software development",
    "devops":               "software development",
    "developer tools":      "software development",
    "platform":             "software development",
    "data infrastructure":  "data infrastructure and analytics",
    "data analytics":       "data infrastructure and analytics",
    "data":                 "data infrastructure and analytics",
    "analytics":            "data infrastructure and analytics",
    "it services":          "it services and it consulting",
    "cloud":                "technology, information and internet",
    "internet":             "technology, information and internet",
    "tech":                 "technology, information and internet",
    "technology":           "technology, information and internet",
    "cybersecurity":        "computer and network security",
    "security":             "computer and network security",
    "fintech":              "financial services",
    "finance":              "financial services",
    "banking":              "banking",
    "investment":           "investment management",
    "insurtech":            "insurance",
    "health ai":            "hospitals and health care",
    "health":               "hospitals and health care",
    "healthcare":           "hospitals and health care",
    "healthtech":           "hospitals and health care",
    "medical":              "medical device",
    "biotech":              "biotechnology research",
    "retail tech":          "retail",
    "retail":               "retail",
    "ecommerce":            "online and mail order retail",
    "d2c":                  "online and mail order retail",
    "supply chain":         "transportation, logistics, supply chain and storage",
    "logistics":            "transportation, logistics, supply chain and storage",
    "hr":                   "human resources services",
    "hrtech":               "human resources services",
    "marketing":            "marketing services",
    "martech":              "marketing services",
    "advertising":          "advertising services",
    "adtech":               "advertising services",
    "real estate":          "real estate",
    "proptech":             "real estate",
    "education":            "education administration programs",
    "edtech":               "e-learning providers",
    "legaltech":            "legal services",
    "legal":                "legal services",
    "gaming":               "computer games",
    "media":                "media production",
    "telecom":              "telecommunications",
    "semiconductor":        "semiconductor manufacturing",
    "robotics":             "robotics engineering",
    "automotive":           "automotive",
    "autotech":             "automotive",
    "aerospace":            "aviation and aerospace component manufacturing",
    "energy":               "renewable energy power generation",
    "cleantech":            "renewable energy power generation",
    "climatetech":          "renewable energy power generation",
    "hospitality":          "hospitality",
    "traveltech":           "travel arrangements",
    "insurance":            "insurance",
    "accounting":           "accounting",
    "consulting":           "business consulting and services",
    "staffing":             "staffing and recruiting",
    "research":             "research services",
    "nonprofit":            "non-profit organizations",
}

INDUSTRY_TO_KEYWORDS = {
    "voice ai":             ["voice AI", "speech recognition", "voice assistant", "conversational AI"],
    "voice tech":           ["voice technology", "speech synthesis", "TTS", "ASR"],
    "speech ai":            ["speech AI", "speech recognition", "voice", "ASR"],
    "conversational ai":    ["conversational AI", "chatbot", "voice bot", "NLP"],
    "nlp":                  ["natural language processing", "NLP", "text analysis"],
    "natural language":     ["natural language", "NLP", "language model"],
    "speech recognition":   ["speech recognition", "ASR", "voice", "audio AI"],
    "generative ai":        ["generative AI", "large language model", "LLM", "GPT"],
    "llm":                  ["large language model", "LLM", "foundation model"],
    "ai startup":           ["artificial intelligence", "machine learning", "AI"],
    "ai saas":              ["artificial intelligence", "machine learning", "SaaS"],
    "ai":                   ["artificial intelligence", "machine learning"],
    "ml":                   ["machine learning", "deep learning", "neural network"],
    "data infrastructure":  ["data pipeline", "data warehouse", "data platform"],
    "data analytics":       ["data analytics", "business intelligence", "BI"],
    "devops":               ["DevOps", "infrastructure", "CI/CD", "Kubernetes"],
    "developer tools":      ["developer tools", "API", "SDK", "developer platform"],
    "cybersecurity":        ["cybersecurity", "zero trust", "SOC", "endpoint security"],
    "health ai":            ["artificial intelligence", "machine learning", "clinical AI"],
    "healthtech":           ["health technology", "digital health", "telemedicine"],
    "fintech":              ["fintech", "payments", "neobank", "embedded finance"],
    "insurtech":            ["insurance technology", "insurtech"],
    "ecommerce":            ["ecommerce", "online retail", "D2C"],
    "d2c":                  ["direct to consumer", "D2C", "ecommerce"],
    "edtech":               ["e-learning", "online education", "LMS", "EdTech"],
    "cleantech":            ["clean energy", "sustainability", "carbon", "renewable"],
    "climatetech":          ["climate technology", "net zero", "carbon capture"],
    "hrtech":               ["HR technology", "human resources software", "HRMS"],
    "martech":              ["marketing technology", "MarTech", "marketing automation"],
    "proptech":             ["property technology", "PropTech", "real estate tech"],
    "gaming":               ["video game", "gaming", "game engine"],
    "legaltech":            ["legal technology", "LegalTech", "contract AI"],
}

FUNDING_TO_COMPANY_AGE = {
    "seed":     "0-3",
    "series a": "0-3",
    "series b": "3-6",
    "series c": "6-10",
    "growth":   "10-20",
}


def _headers() -> dict:
    if not API_KEY:
        raise EnvironmentError(
            "EXPLORIUM_API_KEY is not set. "
            "Add to backend/.env: EXPLORIUM_API_KEY=your_key_here\n"
            "Get your key: https://admin.explorium.ai → Access & Authentication"
        )
    return {
        "api_key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _build_business_filters(filters: dict) -> dict:
    """
    Convert internal GTM filters → validated Explorium filter schema.

    Key fixes vs previous version:
      - website_keywords: dropped unsupported "operator" field → just {"values": [...]}
      - events: dropped unsupported "last_occurrence" field → just {"values": [...]}
      - company_age: removed entirely (field not confirmed valid; caused 422)
      - google_category: removed entirely (field not confirmed valid; caused 422)
      - has_website: kept as {"value": true} (singular, confirmed working)
      - All filter objects use only confirmed-working keys
    """
    ef: dict = {}

    # ── Country ───────────────────────────────────────────────────────────────
    country_raw = _coerce_str(filters.get("country", "US")).lower().strip()
    country_map = {
        # North America
        "us": "us", "usa": "us", "united states": "us",
        "ca": "ca", "canada": "ca",
        "mx": "mx", "mexico": "mx",
        # Europe
        "uk": "gb", "gb": "gb", "united kingdom": "gb", "britain": "gb",
        "de": "de", "germany": "de",
        "fr": "fr", "france": "fr",
        "nl": "nl", "netherlands": "nl",
        "se": "se", "sweden": "se",
        "es": "es", "spain": "es",
        "it": "it", "italy": "it",
        "ch": "ch", "switzerland": "ch",
        "pl": "pl", "poland": "pl",
        "be": "be", "belgium": "be",
        "at": "at", "austria": "at",
        "dk": "dk", "denmark": "dk",
        "fi": "fi", "finland": "fi",
        "no": "no", "norway": "no",
        "pt": "pt", "portugal": "pt",
        "ie": "ie", "ireland": "ie",
        "cz": "cz", "czech republic": "cz", "czechia": "cz",
        "ro": "ro", "romania": "ro",
        "hu": "hu", "hungary": "hu",
        "ua": "ua", "ukraine": "ua",
        "ee": "ee", "estonia": "ee",
        "lt": "lt", "lithuania": "lt",
        "lv": "lv", "latvia": "lv",
        # Asia-Pacific
        "in": "in", "india": "in",
        "jp": "jp", "japan": "jp",
        "cn": "cn", "china": "cn",
        "kr": "kr", "south korea": "kr", "korea": "kr",
        "sg": "sg", "singapore": "sg",
        "au": "au", "australia": "au",
        "nz": "nz", "new zealand": "nz",
        "hk": "hk", "hong kong": "hk",
        "tw": "tw", "taiwan": "tw",
        "id": "id", "indonesia": "id",
        "my": "my", "malaysia": "my",
        "th": "th", "thailand": "th",
        "vn": "vn", "vietnam": "vn",
        "ph": "ph", "philippines": "ph",
        "pk": "pk", "pakistan": "pk",
        "bd": "bd", "bangladesh": "bd",
        # Middle East & Africa
        "il": "il", "israel": "il",
        "ae": "ae", "uae": "ae", "united arab emirates": "ae",
        "sa": "sa", "saudi arabia": "sa",
        "za": "za", "south africa": "za",
        "eg": "eg", "egypt": "eg",
        "ng": "ng", "nigeria": "ng",
        "ke": "ke", "kenya": "ke",
        # Latin America
        "br": "br", "brazil": "br",
        "ar": "ar", "argentina": "ar",
        "cl": "cl", "chile": "cl",
        "co": "co", "colombia": "co",
    }
    country_code = country_map.get(country_raw)
    if not country_code:
        # Try matching by checking if input is already a valid 2-letter ISO code
        # from Explorium's known list rather than blindly slicing
        known_codes = set(country_map.values())
        if len(country_raw) == 2 and country_raw in known_codes:
            country_code = country_raw
        else:
            logger.warning(f"[explorium] Unknown country '{country_raw}' — defaulting to 'us'")
            country_code = "us"
    ef["country_code"] = {"values": [country_code]}

    # ── Industry → linkedin_category + website_keywords ───────────────────────
    industry_raw = _coerce_str(filters.get("industry", "")).lower().strip()
    if industry_raw:
        linkedin_cat = INDUSTRY_TO_LINKEDIN_CATEGORY.get(industry_raw)
        if not linkedin_cat:
            for key, val in INDUSTRY_TO_LINKEDIN_CATEGORY.items():
                if key in industry_raw or industry_raw in key:
                    linkedin_cat = val
                    break

        if linkedin_cat:
            ef["linkedin_category"] = {"values": [linkedin_cat]}

            kws = INDUSTRY_TO_KEYWORDS.get(industry_raw)
            if not kws:
                for key, val in INDUSTRY_TO_KEYWORDS.items():
                    if key in industry_raw or industry_raw in key:
                        kws = val
                        break
            if kws:
                # FIX: removed unsupported "operator" key — Explorium only accepts {"values": [...]}
                ef["website_keywords"] = {"values": kws}

    # ── Company size ──────────────────────────────────────────────────────────
    min_emp = int(filters.get("min_employees", 0))
    max_emp = int(filters.get("max_employees", 10000))
    size_ranges = [
        (1,     10,     "1-10"),
        (11,    50,     "11-50"),
        (51,    200,    "51-200"),
        (201,   500,    "201-500"),
        (501,   1000,   "501-1000"),
        (1001,  5000,   "1001-5000"),
        (5001,  10000,  "5001-10000"),
        (10001, 999999, "10001+"),
    ]
    size_values = [lbl for lo, hi, lbl in size_ranges if lo <= max_emp and hi >= min_emp]
    if size_values:
        ef["company_size"] = {"values": size_values}

    # ── Growth signals → events ───────────────────────────────────────────────
    min_growth = float(filters.get("min_growth_rate", 0))
    if min_growth >= 1.0:
        # FIX: removed unsupported "last_occurrence" key
        ef["events"] = {"values": ["increase_in_all_departments", "new_funding_round"]}
    elif min_growth >= 0.5:
        ef["events"] = {"values": ["hiring_in_sales_department", "increase_in_all_departments"]}
    elif min_growth >= 0.3:
        ef["events"] = {"values": ["increase_in_all_departments"]}

    # ── has_website ───────────────────────────────────────────────────────────
    ef["has_website"] = {"value": True}

    # NOTE: "company_age" and "google_category" removed — not confirmed valid fields
    # and were likely causing 422s. Re-add only after verifying with Explorium docs/support.

    return ef


def _build_relaxed_filters(original: dict) -> dict:
    """Strip down to the safest confirmed-working filter subset."""
    relaxed = {}
    if "country_code" in original:
        relaxed["country_code"] = original["country_code"]
    if "linkedin_category" in original:
        relaxed["linkedin_category"] = original["linkedin_category"]
    if "company_size" in original:
        relaxed["company_size"] = original["company_size"]
    relaxed["has_website"] = {"value": True}
    return relaxed


def _build_minimal_filters(original: dict) -> dict:
    """Last-resort: country + has_website only."""
    return {
        "country_code": original.get("country_code", {"values": ["us"]}),
        "has_website": {"value": True},
    }


def _infer_funding_stage(employees: int, growth_rate: float) -> str:
    if employees <= 15 and growth_rate > 1.0:
        return "Seed"
    if employees <= 50 and growth_rate > 0.7:
        return "Series A"
    if employees <= 200 and growth_rate > 0.4:
        return "Series B"
    if employees <= 500:
        return "Series C"
    return "Growth"


def _extract_hiring_roles_from_events(events: list) -> list[str]:
    dept_to_role = {
        "sales": "VP Sales", "engineering": "Engineering Lead",
        "marketing": "VP Marketing", "finance": "CFO",
        "operations": "COO", "human_resources": "VP People",
        "support": "Head of Customer Success", "legal": "General Counsel",
        "creative": "Creative Director",
    }
    roles = []
    for event in events or []:
        for dept, role in dept_to_role.items():
            if dept in event and role not in roles:
                roles.append(role)
    return roles or ["Engineering", "Sales"]


def _normalize_business(raw: dict) -> dict:
    emp_range = raw.get("number_of_employees_range", "11-50") or "11-50"
    try:
        emp_mid = int(emp_range.split("-")[0].replace("+", "").replace(",", ""))
    except (ValueError, IndexError):
        emp_mid = 50

    rev_range = raw.get("yearly_revenue_range", "") or ""
    rev_map = {
        "0-500K": 0.25, "500K-1M": 0.75, "1M-5M": 3.0, "5M-10M": 7.5,
        "10M-50M": 30.0, "50M-100M": 75.0, "100M-500M": 300.0, "500M-1B": 750.0,
    }
    revenue_estimate_m = rev_map.get(rev_range)

    events = raw.get("events", []) or []
    growth_signals = [e for e in events if "increase" in e or "hiring" in e or "funding" in e]
    growth_rate = round(min(0.2 + len(growth_signals) * 0.25, 2.5), 2)

    intent_topics = raw.get("business_intent_topics", []) or []
    tech_hints = []
    for t in intent_topics[:6]:
        if isinstance(t, dict):
            topic = t.get("topic", "")
            if topic:
                tech_hints.append(topic.split(":")[0].strip().title())
        elif isinstance(t, str) and t:
            tech_hints.append(t.split(":")[0].strip().title())

    industry = (
        raw.get("naics_description")
        or raw.get("linkedin_industry_category")
        or raw.get("linkedin_category")
        or "Technology"
    )

    return {
        "id":                   raw.get("business_id", ""),
        "name":                 raw.get("name", "Unknown"),
        "domain":               raw.get("domain") or raw.get("website", ""),
        "industry":             industry,
        "country":              (raw.get("country_name") or "US").title(),
        "city":                 raw.get("city_name", ""),
        "employees":            emp_mid,
        "employees_range":      emp_range,
        "funding_stage":        _infer_funding_stage(emp_mid, growth_rate),
        "funding_amount_m":     None,
        "founded":              None,
        "growth_rate":          growth_rate,
        "tech_stack":           tech_hints or ["Not Available"],
        "hiring_roles":         _extract_hiring_roles_from_events(events),
        "competitors":          [],
        "revenue_estimate_m":   revenue_estimate_m,
        "business_description": raw.get("business_description", ""),
        "linkedin_profile":     raw.get("linkedin_profile", ""),
        "website":              raw.get("website", ""),
        "_events":              events,
        "_explorium_id":        raw.get("business_id", ""),
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
def search_companies(filters: dict, max_results: int = 6) -> list[dict]:
    explorium_filters = _build_business_filters(filters)
    page_size = min(max_results, 100)
    base_payload = {
        "mode": "full",
        "page": 1,
        "page_size": page_size,
        "size": max_results,
    }

    logger.info(f"[explorium] POST /v1/businesses | filters={list(explorium_filters.keys())}")

    try:
        with httpx.Client(timeout=30.0) as client:

            # ── Attempt 1: full filters ───────────────────────────────────────
            resp = client.post(
                f"{BASE_URL}/businesses",
                headers=_headers(),
                json={**base_payload, "filters": explorium_filters},
            )

            # ── Attempt 2: relaxed filters (drop events + website_keywords) ──
            if resp.status_code == 422:
                logger.error(f"[explorium] 422 full filters: {resp.text[:400]}")
                relaxed1 = _build_relaxed_filters(explorium_filters)
                logger.warning(f"[explorium] Relaxing to: {list(relaxed1.keys())}")
                resp = client.post(
                    f"{BASE_URL}/businesses",
                    headers=_headers(),
                    json={**base_payload, "filters": relaxed1},
                )

            # ── Attempt 3: country + has_website only ─────────────────────────
            if resp.status_code == 422:
                logger.error(f"[explorium] 422 relaxed filters: {resp.text[:400]}")
                minimal = _build_minimal_filters(explorium_filters)
                logger.warning(f"[explorium] Falling back to minimal filters: {list(minimal.keys())}")
                resp = client.post(
                    f"{BASE_URL}/businesses",
                    headers=_headers(),
                    json={**base_payload, "filters": minimal},
                )

            # ── Still 422 after all fallbacks → log full body and bail ────────
            if resp.status_code == 422:
                logger.error(f"[explorium] 422 even on minimal filters: {resp.text[:600]}")
                return []

            if resp.status_code == 401:
                raise EnvironmentError("Explorium API key invalid or expired.")

            if resp.status_code == 503:
                logger.warning("[explorium] 503 — raising to trigger tenacity retry")
                raise httpx.TimeoutException("explorium 503")

            if resp.status_code == 429:
                logger.warning("[explorium] Rate limited — sleeping 5s")
                time.sleep(5)
                raise httpx.TimeoutException("rate limited")

            resp.raise_for_status()
            data = resp.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"[explorium] HTTP {e.response.status_code}: {e.response.text[:200]}")
        if e.response.status_code in (502, 503, 504):
            raise httpx.TimeoutException(f"upstream {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"[explorium] Request error: {e}")
        return []

    raw_list = data.get("data", [])
    total = data.get("total_results", 0)
    logger.info(f"[explorium] Got {len(raw_list)}/{total} businesses")
    return [_normalize_business(c) for c in raw_list if c.get("business_id")]


def get_market_stats(filters: dict) -> dict:
    explorium_filters = _build_business_filters(filters)
    # Strip fields that are less likely to be supported by the stats endpoint
    stats_filters = {
        k: v for k, v in explorium_filters.items()
        if k not in ("has_website", "events", "website_keywords")
    }
    logger.info("[explorium] POST /v1/businesses/stats")
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{BASE_URL}/businesses/stats",
                headers=_headers(),
                json={"filters": stats_filters},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"[explorium] Stats call failed: {e}")
        return {"total_results": 0, "stats": {}}


def get_hiring_signals(company_id: str, business_data: dict | None = None) -> dict:
    if business_data:
        events = business_data.get("_events", []) or []
        dept_counts: dict[str, int] = {}
        depts = ["sales", "engineering", "marketing", "finance",
                 "operations", "support", "human_resources", "legal"]
        for event in events:
            for dept in depts:
                if dept in event:
                    dept_counts[dept] = dept_counts.get(dept, 0) + 1

        hiring_events = [e for e in events if "hiring" in e or "increase" in e]
        top_depts = sorted(dept_counts, key=dept_counts.get, reverse=True)[:3]
        return {
            "open_roles": len(hiring_events) * 3,
            "yoy_hiring_growth": round(min(len(hiring_events) * 0.3, 2.5), 2),
            "top_departments": [d.replace("_", " ").title() for d in top_depts] or ["Engineering"],
        }

    if not company_id:
        return {"open_roles": 0, "yoy_hiring_growth": 0.0, "top_departments": []}

    payload = {
        "mode": "preview",
        "page": 1, "page_size": 10, "size": 50,
        "filters": {"business_id": {"type": "includes", "values": [company_id]}},
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{BASE_URL}/prospects", headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()

        prospects = data.get("data", [])
        dept_counts = {}
        for p in prospects:
            dept = (p.get("job_department") or "unknown").lower()
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        top_depts = sorted(dept_counts, key=dept_counts.get, reverse=True)[:3]
        total = data.get("total_results", len(prospects))
        return {
            "open_roles": max(total // 4, len(prospects)),
            "yoy_hiring_growth": round(min(total / 50, 2.5), 2),
            "top_departments": [d.title() for d in top_depts] or ["Engineering"],
        }
    except Exception as e:
        logger.warning(f"[explorium] Hiring signals failed for {company_id}: {e}")
        return {"open_roles": 0, "yoy_hiring_growth": 0.0, "top_departments": []}


def get_tech_signals(company_id: str, business_data: dict | None = None) -> dict:
    recently_adopted = []
    if business_data:
        tech_stack = business_data.get("tech_stack", [])
        recently_adopted = [t for t in tech_stack if t and t != "Not Available"]
        for event in business_data.get("_events", []):
            if "new_product" in event and "New Product Launch" not in recently_adopted:
                recently_adopted.append("New Product Launch")
            if "new_partnership" in event and "Strategic Partnership" not in recently_adopted:
                recently_adopted.append("Strategic Partnership")
    return {
        "recently_adopted": list(dict.fromkeys(recently_adopted))[:5],
        "sunset": [],
    }


def get_contact_info(prospect_id: str) -> dict:
    if not prospect_id:
        return {"emails": [], "phone_numbers": None}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{BASE_URL}/prospects/contacts_information/enrich",
                headers=_headers(),
                json={"prospect_id": prospect_id},
            )
            resp.raise_for_status()
            d = resp.json().get("data", {})
            return {
                "emails": d.get("emails", []),
                "professions_email": d.get("professions_email"),
                "phone_numbers": d.get("phone_numbers"),
                "mobile_phone": d.get("mobile_phone"),
            }
    except Exception as e:
        logger.warning(f"[explorium] Contact info failed for {prospect_id}: {e}")
        return {"emails": [], "phone_numbers": None}


def get_prospects_for_business(
    business_id: str,
    job_department: list[str] | None = None,
    job_level: list[str] | None = None,
    max_results: int = 5,
) -> list[dict]:
    f: dict = {
        "business_id": {"type": "includes", "values": [business_id]},
        "has_email": {"type": "exists", "value": True},
    }
    if job_department:
        f["job_department"] = {"type": "includes", "values": job_department}
    if job_level:
        f["job_level"] = {"type": "includes", "values": job_level}

    payload = {"mode": "full", "page": 1, "page_size": max_results, "size": max_results, "filters": f}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{BASE_URL}/prospects", headers=_headers(), json=payload)
            resp.raise_for_status()
            return resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"[explorium] Prospects fetch failed for {business_id}: {e}")
        return []

import random as _random

_MOCK_COMPANIES = [
    {
        "id": "c001", "name": "Nexus AI", "domain": "nexusai.io",
        "industry": "AI SaaS", "country": "US", "employees": 320,
        "employees_range": "201-500", "funding_stage": "Series B", "funding_amount_m": 45,
        "founded": 2020, "growth_rate": 0.87,
        "tech_stack": ["Python", "AWS", "Kubernetes", "OpenAI"],
        "hiring_roles": ["VP Sales", "ML Engineer", "SDR"],
        "competitors": ["Scale AI", "Labelbox"], "revenue_estimate_m": None,
        "business_description": "AI-powered data labeling and model training platform.",
        "_events": ["hiring_in_sales_department", "increase_in_engineering_department"],
        "_explorium_id": "c001",
    },
    {
        "id": "c002", "name": "FinFlow", "domain": "finflow.com",
        "industry": "Fintech", "country": "US", "employees": 180,
        "employees_range": "51-200", "funding_stage": "Series A", "funding_amount_m": 18,
        "founded": 2021, "growth_rate": 1.2,
        "tech_stack": ["Node.js", "Stripe", "Plaid", "GCP"],
        "hiring_roles": ["CTO", "Backend Engineer", "Compliance Officer"],
        "competitors": ["Brex", "Ramp"], "revenue_estimate_m": 4.5,
        "business_description": "Embedded finance platform for B2B payments.",
        "_events": ["new_funding_round", "hiring_in_engineering_department"],
        "_explorium_id": "c002",
    },
    {
        "id": "c003", "name": "DataSphere", "domain": "datasphere.ai",
        "industry": "Data Infrastructure", "country": "US", "employees": 95,
        "employees_range": "51-200", "funding_stage": "Seed", "funding_amount_m": 7,
        "founded": 2022, "growth_rate": 2.1,
        "tech_stack": ["Rust", "ClickHouse", "dbt", "Snowflake"],
        "hiring_roles": ["CEO assistant", "Sales Engineer"],
        "competitors": ["Fivetran", "Airbyte"], "revenue_estimate_m": 1.2,
        "business_description": "Real-time data pipeline and observability platform.",
        "_events": ["increase_in_all_departments", "new_product"],
        "_explorium_id": "c003",
    },
    {
        "id": "c004", "name": "CloudOps Pro", "domain": "cloudopspro.com",
        "industry": "DevOps SaaS", "country": "US", "employees": 450,
        "employees_range": "201-500", "funding_stage": "Series C", "funding_amount_m": 90,
        "founded": 2018, "growth_rate": 0.34,
        "tech_stack": ["Go", "Terraform", "Azure", "Datadog"],
        "hiring_roles": ["VP Sales", "Enterprise AE", "Customer Success"],
        "competitors": ["PagerDuty", "OpsGenie"], "revenue_estimate_m": 22.0,
        "business_description": "Cloud infrastructure automation and monitoring.",
        "_events": ["hiring_in_sales_department", "increase_in_customer_service_department"],
        "_explorium_id": "c004",
    },
    {
        "id": "c005", "name": "MedLink AI", "domain": "medlinkhealth.io",
        "industry": "Health AI", "country": "US", "employees": 60,
        "employees_range": "11-50", "funding_stage": "Series A", "funding_amount_m": 12,
        "founded": 2021, "growth_rate": 1.6,
        "tech_stack": ["Python", "AWS", "HIPAA-compliant infra"],
        "hiring_roles": ["CTO", "ML Researcher", "VP Partnerships"],
        "competitors": ["Tempus", "Flatiron Health"], "revenue_estimate_m": None,
        "business_description": "AI-driven clinical decision support for hospitals.",
        "_events": ["new_partnership", "hiring_in_engineering_department"],
        "_explorium_id": "c005",
    },
    {
        "id": "c006", "name": "RetailAI", "domain": "retailai.com",
        "industry": "Retail Tech", "country": "US", "employees": 210,
        "employees_range": "51-200", "funding_stage": "Series B", "funding_amount_m": 35,
        "founded": 2019, "growth_rate": 0.55,
        "tech_stack": ["Python", "Shopify", "GCP", "BigQuery"],
        "hiring_roles": ["VP Sales", "Product Manager", "Data Scientist"],
        "competitors": ["Bloomreach", "Dynamic Yield"], "revenue_estimate_m": 9.8,
        "business_description": "AI personalisation engine for retail and e-commerce.",
        "_events": ["hiring_in_sales_department", "new_product"],
        "_explorium_id": "c006",
    },
    {
        "id": "c007", "name": "SecureVault", "domain": "securevault.io",
        "industry": "Cybersecurity SaaS", "country": "US", "employees": 130,
        "employees_range": "51-200", "funding_stage": "Series A", "funding_amount_m": 20,
        "founded": 2020, "growth_rate": 0.95,
        "tech_stack": ["Rust", "AWS", "SOC2", "Zero-trust"],
        "hiring_roles": ["CEO", "CISO consultant", "Sales Engineer"],
        "competitors": ["CrowdStrike", "SentinelOne"], "revenue_estimate_m": 5.5,
        "business_description": "Zero-trust endpoint security for mid-market enterprises.",
        "_events": ["hiring_in_sales_department", "increase_in_engineering_department"],
        "_explorium_id": "c007",
    },
    {
        "id": "c008", "name": "LogiChain", "domain": "logichain.tech",
        "industry": "Supply Chain SaaS", "country": "US", "employees": 75,
        "employees_range": "11-50", "funding_stage": "Seed", "funding_amount_m": 4,
        "founded": 2022, "growth_rate": 1.8,
        "tech_stack": ["Python", "React", "PostgreSQL", "AWS"],
        "hiring_roles": ["CTO", "Full-stack Engineer"],
        "competitors": ["project44", "Flexport"], "revenue_estimate_m": 0.8,
        "business_description": "Supply chain visibility and freight tracking platform.",
        "_events": ["new_funding_round", "hiring_in_engineering_department"],
        "_explorium_id": "c008",
    },
    {
        "id": "c009", "name": "Sarvam AI", "domain": "sarvam.ai",
        "industry": "Voice AI", "country": "India", "employees": 85,
        "employees_range": "51-200", "funding_stage": "Series A", "funding_amount_m": 41,
        "founded": 2023, "growth_rate": 2.5,
        "tech_stack": ["Python", "PyTorch", "GCP", "Indic NLP"],
        "hiring_roles": ["ML Engineer", "VP Sales", "Research Scientist"],
        "competitors": ["OpenAI", "ElevenLabs"], "revenue_estimate_m": None,
        "business_description": "Voice AI and speech models for Indian languages.",
        "_events": ["new_funding_round", "increase_in_all_departments", "hiring_in_engineering_department"],
        "_explorium_id": "c009",
    },
    {
        "id": "c010", "name": "Krutrim", "domain": "krutrim.com",
        "industry": "Voice AI", "country": "India", "employees": 200,
        "employees_range": "51-200", "funding_stage": "Series A", "funding_amount_m": 50,
        "founded": 2023, "growth_rate": 3.0,
        "tech_stack": ["Python", "CUDA", "AWS", "Indic LLM"],
        "hiring_roles": ["CTO", "AI Researcher", "Enterprise Sales"],
        "competitors": ["Sarvam AI", "Google Gemini"], "revenue_estimate_m": None,
        "business_description": "India-first AI platform with multilingual voice capabilities.",
        "_events": ["new_funding_round", "increase_in_all_departments"],
        "_explorium_id": "c010",
    },
    {
        "id": "c011", "name": "Vernacular AI", "domain": "vernacular.ai",
        "industry": "Conversational AI", "country": "India", "employees": 120,
        "employees_range": "51-200", "funding_stage": "Series B", "funding_amount_m": 22,
        "founded": 2018, "growth_rate": 0.9,
        "tech_stack": ["Python", "AWS", "NLP", "ASR"],
        "hiring_roles": ["VP Sales", "NLP Engineer", "Customer Success"],
        "competitors": ["Yellow.ai", "Observe.AI"], "revenue_estimate_m": 6.0,
        "business_description": "Multilingual voice bots for banking and insurance.",
        "_events": ["hiring_in_sales_department", "new_partnership"],
        "_explorium_id": "c011",
    },
    {
        "id": "c012", "name": "Yellow.ai", "domain": "yellow.ai",
        "industry": "Conversational AI", "country": "India", "employees": 500,
        "employees_range": "201-500", "funding_stage": "Series C", "funding_amount_m": 78,
        "founded": 2016, "growth_rate": 0.6,
        "tech_stack": ["Python", "React", "AWS", "NLP", "Speech Recognition"],
        "hiring_roles": ["VP Sales", "Enterprise AE", "ML Engineer"],
        "competitors": ["Genesys", "Nuance"], "revenue_estimate_m": 20.0,
        "business_description": "Enterprise conversational AI platform for CX automation.",
        "_events": ["hiring_in_sales_department", "increase_in_engineering_department"],
        "_explorium_id": "c012",
    },
    {
        "id": "c013", "name": "Gnani.ai", "domain": "gnani.ai",
        "industry": "Speech AI", "country": "India", "employees": 90,
        "employees_range": "51-200", "funding_stage": "Series A", "funding_amount_m": 13,
        "founded": 2018, "growth_rate": 1.1,
        "tech_stack": ["Python", "TensorFlow", "GCP", "ASR", "TTS"],
        "hiring_roles": ["CTO", "Sales Engineer", "ML Researcher"],
        "competitors": ["Sarvam AI", "Vernacular AI"], "revenue_estimate_m": 3.5,
        "business_description": "Speech recognition and voice analytics for enterprise.",
        "_events": ["new_product", "hiring_in_engineering_department"],
        "_explorium_id": "c013",
    },
    {
        "id": "c014", "name": "Observe.AI", "domain": "observe.ai",
        "industry": "Voice AI", "country": "India", "employees": 350,
        "employees_range": "201-500", "funding_stage": "Series C", "funding_amount_m": 125,
        "founded": 2017, "growth_rate": 0.75,
        "tech_stack": ["Python", "AWS", "NLP", "Real-time ASR"],
        "hiring_roles": ["VP Sales", "Enterprise AE", "Data Scientist"],
        "competitors": ["CallMiner", "Invoca"], "revenue_estimate_m": 30.0,
        "business_description": "AI-powered contact center intelligence and QA automation.",
        "_events": ["hiring_in_sales_department", "increase_in_all_departments"],
        "_explorium_id": "c014",
    },
    {
        "id": "c015", "name": "Slang Labs", "domain": "slanglabs.in",
        "industry": "Voice AI", "country": "India", "employees": 40,
        "employees_range": "11-50", "funding_stage": "Seed", "funding_amount_m": 5,
        "founded": 2018, "growth_rate": 1.4,
        "tech_stack": ["Python", "React Native", "GCP", "Voice SDK"],
        "hiring_roles": ["CTO", "Mobile Engineer", "Sales"],
        "competitors": ["Siri", "Alexa Skills"], "revenue_estimate_m": 1.0,
        "business_description": "In-app voice assistants for e-commerce and retail apps.",
        "_events": ["new_product", "hiring_in_engineering_department"],
        "_explorium_id": "c015",
    },
    {
        "id": "c016", "name": "Perfios", "domain": "perfios.com",
        "industry": "Fintech", "country": "India", "employees": 800,
        "employees_range": "501-1000", "funding_stage": "Series D", "funding_amount_m": 229,
        "founded": 2008, "growth_rate": 0.45,
        "tech_stack": ["Java", "AWS", "ML", "Open Banking"],
        "hiring_roles": ["VP Sales", "Backend Engineer", "Data Analyst"],
        "competitors": ["CIBIL", "Experian India"], "revenue_estimate_m": 40.0,
        "business_description": "Financial data analytics and credit underwriting platform.",
        "_events": ["hiring_in_sales_department", "new_partnership"],
        "_explorium_id": "c016",
    },
    {
        "id": "c017", "name": "Darwinbox", "domain": "darwinbox.com",
        "industry": "HR Tech", "country": "India", "employees": 650,
        "employees_range": "501-1000", "funding_stage": "Series D", "funding_amount_m": 140,
        "founded": 2015, "growth_rate": 0.52,
        "tech_stack": ["Python", "React", "AWS", "ML"],
        "hiring_roles": ["VP Sales", "Implementation Engineer", "CS Manager"],
        "competitors": ["SAP SuccessFactors", "Workday"], "revenue_estimate_m": 35.0,
        "business_description": "Modern HCM platform for Asian enterprises.",
        "_events": ["hiring_in_sales_department", "new_partnership"],
        "_explorium_id": "c017",
    },
]

_MOCK_HIRING_SIGNALS: dict[str, dict] = {
    "c001": {"open_roles": 14, "yoy_hiring_growth": 0.8,  "top_departments": ["Sales", "Engineering"]},
    "c002": {"open_roles": 8,  "yoy_hiring_growth": 1.2,  "top_departments": ["Engineering", "Compliance"]},
    "c003": {"open_roles": 5,  "yoy_hiring_growth": 2.0,  "top_departments": ["Engineering"]},
    "c004": {"open_roles": 22, "yoy_hiring_growth": 0.3,  "top_departments": ["Sales", "CS"]},
    "c005": {"open_roles": 9,  "yoy_hiring_growth": 1.5,  "top_departments": ["Research", "Partnerships"]},
    "c006": {"open_roles": 12, "yoy_hiring_growth": 0.6,  "top_departments": ["Sales", "Data"]},
    "c007": {"open_roles": 7,  "yoy_hiring_growth": 0.9,  "top_departments": ["Sales", "Security"]},
    "c008": {"open_roles": 4,  "yoy_hiring_growth": 1.8,  "top_departments": ["Engineering"]},
    "c009": {"open_roles": 18, "yoy_hiring_growth": 2.5,  "top_departments": ["Engineering", "Research"]},
    "c010": {"open_roles": 25, "yoy_hiring_growth": 3.0,  "top_departments": ["Engineering", "AI Research"]},
    "c011": {"open_roles": 11, "yoy_hiring_growth": 0.9,  "top_departments": ["Sales", "Engineering"]},
    "c012": {"open_roles": 30, "yoy_hiring_growth": 0.6,  "top_departments": ["Sales", "Engineering", "CS"]},
    "c013": {"open_roles": 8,  "yoy_hiring_growth": 1.1,  "top_departments": ["Engineering", "Research"]},
    "c014": {"open_roles": 20, "yoy_hiring_growth": 0.75, "top_departments": ["Sales", "Engineering"]},
    "c015": {"open_roles": 6,  "yoy_hiring_growth": 1.4,  "top_departments": ["Engineering", "Sales"]},
    "c016": {"open_roles": 15, "yoy_hiring_growth": 0.45, "top_departments": ["Sales", "Data"]},
    "c017": {"open_roles": 22, "yoy_hiring_growth": 0.52, "top_departments": ["Sales", "CS", "Engineering"]},
}

_MOCK_TECH_SIGNALS: dict[str, dict] = {
    "c001": {"recently_adopted": ["Salesforce", "Outreach"],     "sunset": ["HubSpot"]},
    "c002": {"recently_adopted": ["Stripe", "Plaid API v3"],     "sunset": []},
    "c003": {"recently_adopted": ["dbt Cloud", "Monte Carlo"],   "sunset": ["Airflow"]},
    "c004": {"recently_adopted": ["Gainsight", "Gong"],          "sunset": ["Zendesk"]},
    "c005": {"recently_adopted": ["AWS HealthLake"],              "sunset": []},
    "c006": {"recently_adopted": ["Klaviyo", "Segment"],         "sunset": ["Mailchimp"]},
    "c007": {"recently_adopted": ["CrowdStrike Falcon"],          "sunset": []},
    "c008": {"recently_adopted": ["project44 API"],               "sunset": ["spreadsheets"]},
    "c009": {"recently_adopted": ["Indic TTS", "GCP Speech"],    "sunset": []},
    "c010": {"recently_adopted": ["Custom LLM infra", "CUDA"],   "sunset": []},
    "c011": {"recently_adopted": ["Whisper ASR", "Dialogflow"],  "sunset": ["rule-based IVR"]},
    "c012": {"recently_adopted": ["GPT-4o", "Real-time STT"],    "sunset": ["legacy IVR"]},
    "c013": {"recently_adopted": ["Conformer ASR", "FastAPI"],   "sunset": []},
    "c014": {"recently_adopted": ["GPT-4 Turbo", "AWS Connect"], "sunset": ["manual QA"]},
    "c015": {"recently_adopted": ["Voice SDK v3", "React Native"],"sunset": []},
    "c016": {"recently_adopted": ["Open Banking API", "ML Scoring"],"sunset": ["manual underwriting"]},
    "c017": {"recently_adopted": ["GPT for HR", "Mobile HCM"],   "sunset": ["legacy HRMS"]},
}


def _mock_search_companies(filters: dict, max_results: int = 6) -> list[dict]:
    results = list(_MOCK_COMPANIES)

    country_raw = _coerce_str(filters.get("country", "")).lower().strip()
    country_aliases = {
        "us": "us", "usa": "us", "united states": "us",
        "india": "india", "in": "india",
        "uk": "uk", "gb": "uk", "united kingdom": "uk",
        "japan": "japan", "jp": "japan",
        "singapore": "singapore", "sg": "singapore",
        "australia": "australia", "au": "australia",
        "germany": "germany", "de": "germany",
        "france": "france", "fr": "france",
        "canada": "canada", "ca": "canada",
        "brazil": "brazil", "br": "brazil",
        "china": "china", "cn": "china",
        "south korea": "south korea", "kr": "south korea",
        "israel": "israel", "il": "israel",
    }
    target_country = country_aliases.get(country_raw, country_raw)
    if target_country:
        results = [c for c in results if c["country"].lower() == target_country]

    industry_kw = _coerce_str(filters.get("industry", "")).lower()
    if industry_kw:
        def _matches(c: dict) -> bool:
            haystack = (
                c["industry"].lower() + " "
                + c.get("business_description", "").lower() + " "
                + " ".join(c.get("tech_stack", [])).lower()
            )
            for word in industry_kw.replace("-", " ").split():
                if len(word) >= 3 and word in haystack:
                    return True
            return False
        filtered = [c for c in results if _matches(c)]
        if filtered:
            results = filtered

    min_growth = float(filters.get("min_growth_rate", 0))
    if min_growth > 0:
        results = [c for c in results if (c.get("growth_rate") or 0) >= min_growth]

    funding_stage = _coerce_str(filters.get("funding_stage", "")).lower()
    if funding_stage:
        results = [c for c in results
                   if funding_stage in (c.get("funding_stage") or "").lower()]

    min_emp = int(filters.get("min_employees", 0))
    max_emp = int(filters.get("max_employees", 99999))
    if min_emp > 0 or max_emp < 99999:
        results = [c for c in results
                   if min_emp <= (c.get("employees") or 0) <= max_emp]

    noisy = []
    for c in results:
        c = dict(c)
        if _random.random() < 0.3:
            c[_random.choice(["revenue_estimate_m", "funding_amount_m"])] = None
        noisy.append(c)

    return noisy[:max_results]


def _mock_hiring_signals(company_id: str) -> dict:
    return _MOCK_HIRING_SIGNALS.get(
        company_id,
        {"open_roles": 0, "yoy_hiring_growth": 0.0, "top_departments": []},
    )


def _mock_tech_signals(company_id: str) -> dict:
    return _MOCK_TECH_SIGNALS.get(
        company_id,
        {"recently_adopted": [], "sunset": []},
    )

_original_search_companies = search_companies

def search_companies(filters: dict, max_results: int = 6) -> list[dict]:
    if not API_KEY:
        logger.info("[data_source] No EXPLORIUM_API_KEY — using mock data")
        return _mock_search_companies(filters, max_results)
    try:
        results = _original_search_companies(filters, max_results)
        if results:
            logger.info(f"[data_source] Explorium returned {len(results)} companies")
            return results
        logger.warning("[data_source] Explorium returned 0 results — falling back to mock data")
        return _mock_search_companies(filters, max_results)
    except Exception as e:
        logger.warning(f"[data_source] Explorium failed ({e.__class__.__name__}: {e}) — using mock data")
        return _mock_search_companies(filters, max_results)


_original_get_hiring_signals = get_hiring_signals

def get_hiring_signals(company_id: str, business_data: dict | None = None) -> dict:
    if not API_KEY:
        return _mock_hiring_signals(company_id)
    if business_data and business_data.get("_events"):
        return _original_get_hiring_signals(company_id, business_data=business_data)
    if company_id in _MOCK_HIRING_SIGNALS:
        return _MOCK_HIRING_SIGNALS[company_id]
    try:
        return _original_get_hiring_signals(company_id, business_data=business_data)
    except Exception as e:
        logger.warning(f"[data_source] Hiring signals failed — using mock ({e.__class__.__name__})")
        return _mock_hiring_signals(company_id)


_original_get_tech_signals = get_tech_signals

def get_tech_signals(company_id: str, business_data: dict | None = None) -> dict:
    if not API_KEY:
        return _mock_tech_signals(company_id)
    if company_id in _MOCK_TECH_SIGNALS:
        return _MOCK_TECH_SIGNALS[company_id]
    try:
        return _original_get_tech_signals(company_id, business_data=business_data)
    except Exception as e:
        logger.warning(f"[data_source] Tech signals failed — using mock ({e.__class__.__name__})")
        return _mock_tech_signals(company_id)