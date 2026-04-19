from .base_agent import BaseAgent, AgentError

SYSTEM = """You are a GTM Planner Agent. Your job is to decompose a user's natural language go-to-market query into a structured execution plan.
Output ONLY valid JSON (no markdown, no explanation) with this exact schema:
{
  "entity_type": "company|person|market",
  "tasks": ["search", "enrich", "analyze", "generate_outreach"],
  "filters": {
    "industry": "...",
    "country": "US",
    "funding_stage": "...",
    "min_growth_rate": 0.0,
    "hiring_role": "...",
    "min_employees": 0,
    "max_employees": 10000
  },
  "target_personas": ["CEO", "VP Sales", "CTO"],
  "strategy": "short description of overall GTM approach",
  "confidence": 0.85,
  "reasoning": "why these filters and tasks were chosen"
}

Rules:
- confidence reflects how well the query maps to a clear GTM action (0-1)
- If query is vague, lower confidence and add "clarify" to tasks
- funding_stage options: Seed, Series A, Series B, Series C, Growth
- min_growth_rate is a decimal (0.5 = 50% growth)
- Only include filters that are clearly implied by the query
"""


class PlannerAgent(BaseAgent):
    name = "planner_agent"

    def run(self, query: str, memory_context: list[dict] | None = None) -> dict:
        self.log("start", {"query": query})

        memory_hint = ""
        if memory_context:
            memory_hint = f"\n\nSimilar past queries for context:\n"
            for m in memory_context[:2]:
                memory_hint += f"- Query: {m['entry']['query']} → Strategy: {m['entry']['plan'].get('strategy', '')}\n"

        user_prompt = f"GTM Query: {query}{memory_hint}"

        try:
            raw = self.call_llm(SYSTEM, user_prompt)
            plan = self.parse_json(raw)
            self.last_confidence = plan.get("confidence", 0.7)
            self.log("plan_created", plan)
            return plan
        except AgentError as e:
            self.log("fallback_plan", str(e), level="warning")
            # Fallback plan
            return {
                "entity_type": "company",
                "tasks": ["search", "enrich", "analyze", "generate_outreach"],
                "filters": {"industry": "", "country": "US", "min_growth_rate": 0.3},
                "target_personas": ["VP Sales", "CEO"],
                "strategy": "Broad GTM search with enrichment",
                "confidence": 0.4,
                "reasoning": "Fallback due to parse error",
            }