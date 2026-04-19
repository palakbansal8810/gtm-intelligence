import json
from .base_agent import BaseAgent, AgentError
 
SYSTEM_SINGLE = """You are a GTM Strategy Agent. Generate an outreach strategy for ONE company.
Output ONLY valid JSON (no extra text):
{
  "company_id": "...",
  "company_name": "...",
  "persona_strategies": {
    "CEO": {
      "hook": "1-sentence hook referencing a specific signal",
      "angle": "strategic/revenue/risk",
      "email_snippet": "2-3 sentence cold email opening",
      "talking_points": ["point 1", "point 2", "point 3"]
    },
    "VP Sales": {
      "hook": "...",
      "angle": "pipeline/quota/efficiency",
      "email_snippet": "...",
      "talking_points": ["...", "...", "..."]
    },
    "CTO": {
      "hook": "...",
      "angle": "tech/scale/security",
      "email_snippet": "...",
      "talking_points": ["...", "...", "..."]
    }
  },
  "competitive_intel": {
    "key_competitors": ["..."],
    "competitor_weaknesses": "one sentence",
    "our_positioning": "one sentence",
    "displacement_strategy": "one sentence"
  },
  "icp_rank": 1,
  "recommended_sequence": "email|linkedin|call",
  "urgency_signal": "specific signal from company data"
}
Rules:
- Hooks MUST reference a specific fact from company data (hiring role, tech, growth signal)
- CEO = strategic/revenue/risk angle
- VP Sales = pipeline/quota/tools/efficiency angle
- CTO = tech/scale/security/engineering velocity angle
- Keep each field concise — hooks 1 sentence, email_snippet 2-3 sentences max
"""
 
SYSTEM_SUMMARY = """You are a GTM Strategy Agent. Given a list of company strategies,
write a 2-3 sentence overall GTM narrative and pick the top 3 hooks.
 
Output ONLY valid JSON:
{
  "overall_gtm_summary": "2-3 sentence narrative",
  "top_hooks": ["hook 1", "hook 2", "hook 3"],
  "confidence": 0.0-1.0
}
"""
 
class GTMStrategyAgent(BaseAgent):
    name = "gtm_strategy_agent"
    max_tokens = 1100 
 
    def run(self, enriched_companies: list[dict], plan: dict, query: str) -> dict:
        self.log("start", {"num_companies": len(enriched_companies), "personas": plan.get("target_personas")})
 
        if not enriched_companies:
            return {
                "companies": [],
                "overall_gtm_summary": "No valid companies to generate strategy for.",
                "top_hooks": [],
                "confidence": 0.0,
            }
 
        target_personas = plan.get("target_personas", ["CEO", "VP Sales", "CTO"])
     
        for p in ["CEO", "VP Sales", "CTO"]:
            if p not in target_personas:
                target_personas.append(p)
 
        company_strategies = []
 
        for company in enriched_companies[:5]:
            strategy = self._strategy_for_company(company, target_personas, query)
            if strategy:
                company_strategies.append(strategy)
 
        summary = self._generate_summary(company_strategies, query)
 
        self.last_confidence = summary.get("confidence", 0.75)
        self.log("done", {"confidence": self.last_confidence, "companies": len(company_strategies)})
 
        return {
            "companies": company_strategies,
            "overall_gtm_summary": summary.get("overall_gtm_summary", ""),
            "top_hooks": summary.get("top_hooks", []),
            "confidence": self.last_confidence,
        }
 
    def _strategy_for_company(self, company: dict, personas: list[str], query: str) -> dict | None:
        """Generate strategy for a single company. Returns None on total failure."""
        enrichment = company.get("enrichment", {})
        company_data = {
            "id": company.get("id"),
            "name": company.get("name"),
            "industry": company.get("industry"),
            "funding_stage": company.get("funding_stage"),
            "growth_rate": company.get("growth_rate"),
            "employees_range": company.get("employees_range"),
            "hiring_roles": company.get("hiring_roles", []),
            "tech_stack": company.get("tech_stack", [])[:5],
            "competitors": company.get("competitors", []),
            "buying_signals": enrichment.get("buying_signals", []),
            "icp_score": enrichment.get("icp_score", 0.5),
            "derived_insights": enrichment.get("derived_insights", [])[:3],
            "hiring_signals": company.get("hiring_signals", {}),
        }
 
        user_prompt = f"""Query: {query}
Target personas: {personas}
 
Company data:
{json.dumps(company_data, indent=2)}
 
Generate the GTM strategy JSON for this company only."""
 
        try:
            raw = self.call_llm(SYSTEM_SINGLE, user_prompt, max_tokens=800)
            result = self.parse_json(raw)
            # Ensure required fields present
            if "company_id" not in result:
                result["company_id"] = company.get("id", "")
            if "company_name" not in result:
                result["company_name"] = company.get("name", "")
            return result
        except AgentError as e:
            self.log("company_strategy_fallback", {"company": company.get("name"), "error": str(e)}, level="warning")
            return self._fallback_single(company)
 
    def _generate_summary(self, company_strategies: list[dict], query: str) -> dict:
        """Generate overall GTM summary from all company strategies."""
        if not company_strategies:
            return {"overall_gtm_summary": "No strategies generated.", "top_hooks": [], "confidence": 0.0}
 
        # Collect all hooks for the summary prompt
        all_hooks = []
        for cs in company_strategies:
            for persona, data in cs.get("persona_strategies", {}).items():
                hook = data.get("hook", "")
                if hook:
                    all_hooks.append(f"[{cs.get('company_name', '')} / {persona}] {hook}")
 
        user_prompt = f"""Query: {query}
Companies with strategies: {[cs.get('company_name') for cs in company_strategies]}
 
Sample hooks generated:
{json.dumps(all_hooks[:9], indent=2)}
 
Write the GTM summary JSON."""
 
        try:
            raw = self.call_llm(SYSTEM_SUMMARY, user_prompt, max_tokens=300)
            return self.parse_json(raw)
        except AgentError:
            # Build summary from hooks directly — no extra API call needed
            top_hooks = [h.split("] ", 1)[-1] for h in all_hooks[:3]]
            return {
                "overall_gtm_summary": f"Targeting {len(company_strategies)} companies with personalized outreach across CEO, VP Sales, and CTO personas.",
                "top_hooks": top_hooks,
                "confidence": 0.7,
            }
 
    def _fallback_single(self, company: dict) -> dict:
        """Minimal deterministic fallback for a single company."""
        name = company.get("name", "Company")
        signals = company.get("enrichment", {}).get("buying_signals", [])
        signal_hint = signals[0] if signals else "recent growth signals"
        return {
            "company_id": company.get("id", ""),
            "company_name": name,
            "persona_strategies": {
                "CEO": {
                    "hook": f"{name}'s {signal_hint} signals a strong moment to discuss strategic growth.",
                    "angle": "growth",
                    "email_snippet": f"Hi, I noticed {name} has been scaling quickly. I'd love to share how we've helped similar companies accelerate revenue.",
                    "talking_points": ["Revenue growth", "Competitive positioning", "ROI timeline"],
                },
                "VP Sales": {
                    "hook": f"Your reps at {name} could close 30% faster with AI-powered prospect intelligence.",
                    "angle": "pipeline",
                    "email_snippet": f"Hi, are your reps at {name} spending too much time on manual research? We eliminate that.",
                    "talking_points": ["Pipeline velocity", "Rep productivity", "ICP targeting precision"],
                },
                "CTO": {
                    "hook": f"{name}'s tech investment signals readiness to scale — we integrate in under a day.",
                    "angle": "scale",
                    "email_snippet": f"Hi, given {name}'s recent infrastructure investments, I think you'd find our API-first platform valuable.",
                    "talking_points": ["Zero-friction integration", "Data quality", "Engineering velocity"],
                },
            },
            "competitive_intel": {
                "key_competitors": company.get("competitors", []),
                "competitor_weaknesses": "Lack of AI-native workflows",
                "our_positioning": "Modern AI-first alternative with faster time-to-value",
                "displacement_strategy": "Offer a free 2-week POC against their current stack",
            },
            "icp_rank": 1,
            "recommended_sequence": "email|linkedin|call",
            "urgency_signal": signal_hint,
        }