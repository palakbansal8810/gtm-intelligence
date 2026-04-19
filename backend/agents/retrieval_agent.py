import json
from .base_agent import BaseAgent, AgentError
from tools.mock_apis import search_companies
 
SYSTEM = """You are a Retrieval Agent for a GTM intelligence platform.
Given a search plan, return a refined filter set as compact JSON.
 
Output ONLY valid JSON (no extra text):
{"refined_filters":{"industry":"...","country":"...","funding_stage":"","min_growth_rate":0.0,"hiring_role":"","min_employees":0,"max_employees":10000},"filter_confidence":0.85,"warnings":[],"fallback_applied":false}
 
Rules:
- PRESERVE the exact industry string from the plan — do not rephrase or generalise it
  e.g. "voice AI" stays "voice AI", not "Artificial Intelligence"
- If filters are too strict, relax min_growth_rate or employee range, not the industry
- filter_confidence: 0.9 if industry is specific, 0.6 if vague
"""
 
 
class RetrievalAgent(BaseAgent):
    name = "retrieval_agent"
 
    def run(self, plan: dict, state: dict = None) -> dict:
        state = state or {}
        plan_filters = plan.get("filters", {})
        self.log("start", {"filters": plan_filters})
 
        user_prompt = f"Plan filters: {json.dumps(plan_filters)}\nStrategy: {plan.get('strategy','')}\nRefine these filters — preserve the industry string exactly."
 
        try:
            raw = self.call_llm(SYSTEM, user_prompt, max_tokens=300)
            refinement = self.parse_json(raw)
        except AgentError:
            refinement = {
                "refined_filters": plan_filters,
                "filter_confidence": 0.5,
                "warnings": ["Could not refine filters — using plan filters directly"],
                "fallback_applied": False,
            }
 
        refined = refinement.get("refined_filters", plan_filters)
 
        original_industry = plan_filters.get("industry", "")
        if original_industry and refined.get("industry", "") != original_industry:
            self.log(
                "industry_restored",
                {"original": original_industry, "llm_said": refined.get("industry")},
                level="warning",
            )
            refined["industry"] = original_industry
 
        self.log("refined_filters", refined)
 
        companies = search_companies(refined, max_results=6)
        if companies:
            state["last_successful_companies"] = companies
            self.log("cache_saved", {"count": len(companies)})

        self.log("retrieved", {"count": len(companies)})
 
        # Empty results — relax to country + industry only (drop employee/growth constraints)
        if not companies:
            self.log("empty_results_fallback", "relaxing constraints", level="warning")
            relaxed = {
                "industry": refined.get("industry", ""),
                "country": refined.get("country", "US"),
            }
            companies = search_companies(relaxed, max_results=6)
            if companies:
                state["last_successful_companies"] = companies
                self.log("cache_saved_after_relaxation", {"count": len(companies)})

            if not companies:
                cached = state.get("last_successful_companies", [])
                if cached:
                    self.log("using_cached_companies", {"count": len(cached)}, level="warning")
                    companies = cached
                else:
                    self.log("no_cache_available", {}, level="error")
            refinement["fallback_applied"] = True
            refinement["warnings"].append("Empty results — relaxed to industry + country only")
 
        self.last_confidence = refinement.get("filter_confidence", 0.7)
 
        return {
            "companies": companies,
            "refined_filters": refined,
            "filter_confidence": self.last_confidence,
            "warnings": refinement.get("warnings", []),
            "fallback_applied": refinement.get("fallback_applied", False),
        }