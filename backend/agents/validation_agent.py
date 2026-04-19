import json
from .base_agent import BaseAgent, AgentError

SYSTEM = """You are a Critic Agent for a GTM intelligence system.
Validate whether retrieved company results answer the user's original GTM query.

Output ONLY valid JSON:
{
  "verdict": "accept|reject|partial",
  "overall_confidence": 0.0-1.0,
  "issues": [
    {
      "type": "relevance|hallucination|over_constraint|missing_data|invalid_assumption",
      "description": "...",
      "severity": "critical|warning|info"
    }
  ],
  "corrections": {
    "revised_filters": {},
    "drop_company_ids": [],
    "instruction": "specific actionable fix for the retrieval agent"
  },
  "valid_company_ids": ["ids of companies that ARE relevant — include all if majority are fine"],
  "reasoning_summary": "2-3 sentence explanation"
}

Validation rules:
- ACCEPT if majority of companies match the query intent
- PARTIAL if some match, some don't — keep good ones in valid_company_ids
- REJECT only if companies are entirely irrelevant (wrong industry, wrong country)
- When rejecting due to wrong industry: set instruction to use website_keywords with specific terms
- When rejecting due to wrong country: set instruction to fix country filter
- Do NOT reject just because companies are large/established — focus on industry fit
- corrections.revised_filters: provide SPECIFIC filter changes that would fix the problem
  Example: {"website_keywords": {"values": ["voice AI", "speech recognition"], "operator": "OR"}}
- If companies are from a completely unrelated industry (publishing, manufacturing etc.) → REJECT
- If companies are broadly tech but not the specific niche → PARTIAL (not REJECT)
- Prefer PARTIAL over REJECT when in doubt — retrying is expensive
"""
class ValidationAgent(BaseAgent):
    name = "validation_agent"

    def run(self, query: str, plan: dict, enriched_companies: list[dict]) -> dict:
        self.log("start", {"num_companies": len(enriched_companies), "query": query})

        companies_summary = []
        for c in enriched_companies:
            companies_summary.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "industry": c.get("industry"),
                "country": c.get("country"),
                "description": (c.get("business_description") or "")[:100],
                "icp_score": c.get("enrichment", {}).get("icp_score"),
                "buying_signals": c.get("enrichment", {}).get("buying_signals", []),
            })

        user_prompt = f"""Original Query: {query}
Plan Strategy: {plan.get('strategy', '')}
Filters Used: {json.dumps(plan.get('filters', {}))}

Companies Retrieved ({len(companies_summary)}):
{json.dumps(companies_summary, indent=2)}

Validate relevance. If rejecting, provide specific filter corrections."""

        try:
            raw = self.call_llm(SYSTEM, user_prompt, max_tokens=500)
            validation = self.parse_json(raw)
        except AgentError as e:
            self.log("validation_fallback", str(e), level="warning")
            validation = {
                "verdict": "partial",
                "overall_confidence": 0.6,
                "issues": [{"type": "missing_data", "description": "Critic parse error", "severity": "warning"}],
                "corrections": {"revised_filters": {}, "drop_company_ids": [], "instruction": ""},
                "valid_company_ids": [c.get("id") for c in enriched_companies],
                "reasoning_summary": "Critic parse error — accepting with reduced confidence.",
            }

        verdict = validation.get("verdict", "partial")
        self.last_confidence = validation.get("overall_confidence", 0.6)
        self.log("verdict", {"verdict": verdict, "confidence": self.last_confidence})

        # Filter to valid companies — if filtering empties the list, keep all
        valid_ids = set(validation.get("valid_company_ids", [c.get("id") for c in enriched_companies]))
        drop_ids  = set(validation.get("corrections", {}).get("drop_company_ids", []))
        filtered  = [c for c in enriched_companies
                     if c.get("id") in valid_ids and c.get("id") not in drop_ids]
        if not filtered:
            filtered = enriched_companies

        return {
            "verdict": verdict,
            "confidence": self.last_confidence,
            "issues": validation.get("issues", []),
            "corrections": validation.get("corrections", {}),
            "reasoning_summary": validation.get("reasoning_summary", ""),
            "filtered_companies": filtered,
            "should_retry": verdict == "reject",
        }