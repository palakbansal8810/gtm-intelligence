import json
from .base_agent import BaseAgent, AgentError
from tools.mock_apis import get_hiring_signals, get_tech_signals

SYSTEM = """You are a B2B GTM Enrichment Agent. Score and enrich a company record.
Output ONLY this JSON (no extra text, no markdown):
{"icp_score":0.0,"icp_breakdown":{"fit_score":0.0,"intent_score":0.0,"growth_score":0.0},"buying_signals":["signal1","signal2"],"derived_insights":["insight1","insight2"],"data_quality":"high|medium|low","missing_fields":[],"enrichment_confidence":0.0}
Rules:
- icp_score = fit*0.4 + intent*0.3 + growth*0.3
- buying_signals: specific actionable signals (e.g. "Hiring VP Sales", "Adopted Salesforce")
- derived_insights: max 2 short sentences on why this company is a good prospect
- data_quality: low if revenue/growth missing, else medium/high
- enrichment_confidence: drops if many fields null
- Keep buying_signals and derived_insights to 2-3 items each — be concise
"""

def _compact_company(company: dict, hiring: dict, tech: dict, plan: dict) -> str:
    return json.dumps({
        "name": company.get("name"),
        "industry": company.get("industry"),
        "employees_range": company.get("employees_range"),
        "funding_stage": company.get("funding_stage"),
        "growth_rate": company.get("growth_rate"),
        "revenue_estimate_m": company.get("revenue_estimate_m"),
        "hiring_roles": company.get("hiring_roles", [])[:4],
        "tech_stack": company.get("tech_stack", [])[:4],
        "competitors": company.get("competitors", [])[:3],
        "description": (company.get("business_description") or "")[:200],
        "hiring_signals": hiring,
        "tech_signals": tech,
        "target_personas": plan.get("target_personas", []),
        "strategy": plan.get("strategy", ""),
    }, separators=(",", ":"))   # compact JSON = fewer tokens
 
 
class EnrichmentAgent(BaseAgent):
    name = "enrichment_agent"
    max_tokens = 400   
 
    def run(self, companies: list[dict], plan: dict) -> list[dict]:
        self.log("start", {"num_companies": len(companies)})
        enriched = []
        total_confidence = 0.0
 
        for company in companies:
            cid = company.get("id", "unknown")
 
            hiring = get_hiring_signals(cid, business_data=company)
            tech   = get_tech_signals(cid, business_data=company)
 
            user_prompt = f"Enrich this company:\n{_compact_company(company, hiring, tech, plan)}"
 
            try:
                raw = self.call_llm(SYSTEM, user_prompt, max_tokens=300)
                enrichment = self.parse_json(raw)
            except AgentError as e:
                self.log("enrichment_fallback", str(e), level="warning")
                enrichment = {
                    "icp_score": 0.5,
                    "icp_breakdown": {"fit_score": 0.5, "intent_score": 0.5, "growth_score": 0.5},
                    "buying_signals": ["Insufficient data"],
                    "derived_insights": ["Could not enrich — using defaults"],
                    "data_quality": "low",
                    "missing_fields": ["multiple"],
                    "enrichment_confidence": 0.3,
                }
            total_confidence += enrichment.get("enrichment_confidence", 0.5)
            enriched.append({
                **company,
                "hiring_signals": hiring,
                "tech_signals": tech,
                "enrichment": enrichment,
            })
            self.log("enriched_company", {
                "id": cid,
                "icp_score": enrichment.get("icp_score"),
            })
 
        self.last_confidence = total_confidence / max(len(companies), 1)
        self.log("done", {"avg_confidence": self.last_confidence})
        return enriched
