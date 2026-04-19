import time
import asyncio
import logging
from typing import AsyncGenerator

from agents import (PlannerAgent,RetrievalAgent,EnrichmentAgent,ValidationAgent,GTMStrategyAgent,)
from memory import memory_store

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

class Orchestrator:
    def __init__(self):
        self.planner = PlannerAgent()
        self.retriever = RetrievalAgent()
        self.enricher = EnrichmentAgent()
        self.validator = ValidationAgent()
        self.gtm = GTMStrategyAgent()
        self.reasoning_trace: list[dict] = []
        self.agent_logs: list[dict] = []

    def _trace(self, step: str, agent: str, summary: str, data: dict = None, status: str = "done"):
        entry = {
            "step": step,
            "agent": agent,
            "summary": summary,
            "status": status,
            "ts": time.time(),
            "data": data or {},
        }
        self.reasoning_trace.append(entry)
        return entry

    async def run(self, query: str) -> AsyncGenerator[dict, None]:
   
        self.reasoning_trace = []
        self.agent_logs = []
        start_time = time.time()
        yield {"event": "agent_start", "agent": "memory", "message": "Checking vector memory for similar queries…"}
        await asyncio.sleep(0.1)

        memory_hits = memory_store.retrieve(query, top_k=3, threshold=0.75)
        if memory_hits:
            best = memory_hits[0]
            yield {
                "event": "memory_hit",
                "agent": "memory",
                "message": f"Found {len(memory_hits)} similar past queries (similarity: {best['similarity']:.2f})",
                "data": {"hits": len(memory_hits), "best_similarity": best["similarity"]},
            }
            self._trace("memory_lookup", "memory", f"Cache hit: {len(memory_hits)} similar queries found")
        else:
            yield {"event": "memory_miss", "agent": "memory", "message": "No cached results — running full pipeline"}
            self._trace("memory_lookup", "memory", "No cache hit; proceeding with full execution")

        yield {"event": "agent_start", "agent": "planner_agent", "message": "Planner decomposing query…"}
        await asyncio.sleep(0.1)

        plan = self.planner.run(query, memory_context=memory_hits or None)
        self.agent_logs.extend(self.planner.logs)
        self._trace(
            "planning", "planner_agent",
            f"Plan created: {len(plan.get('tasks', []))} tasks, confidence {plan.get('confidence', 0):.2f}",
            {"tasks": plan.get("tasks"), "strategy": plan.get("strategy")},
        )
        yield {
            "event": "agent_done",
            "agent": "planner_agent",
            "message": f"Plan ready — {plan.get('strategy', '')}",
            "data": {"tasks": plan.get("tasks"), "confidence": plan.get("confidence"), "filters": plan.get("filters")},
        }

        retry_count = 0
        validation_result = None
        enriched_companies = []
        retrieval_result = {}

        while retry_count < MAX_RETRIES:
            iteration = retry_count + 1

            yield {
                "event": "agent_start", "agent": "retrieval_agent",
                "message": f"Retrieval Agent fetching companies (attempt {iteration})…",
                "data": {"attempt": iteration},
            }
            await asyncio.sleep(0.1)

            # Apply corrections from previous critic if any
            if validation_result and validation_result.get("corrections", {}).get("revised_filters"):
                plan["filters"].update(validation_result["corrections"]["revised_filters"])
                yield {
                    "event": "retry_correction",
                    "agent": "retrieval_agent",
                    "message": f"Re-planning with critic corrections (attempt {iteration})",
                    "data": {"revised_filters": plan["filters"]},
                }

            retrieval_result = self.retriever.run(plan)
            self.agent_logs.extend(self.retriever.logs)
            companies = retrieval_result.get("companies", [])

            self._trace(
                f"retrieval_attempt_{iteration}", "retrieval_agent",
                f"Retrieved {len(companies)} companies (filter confidence: {retrieval_result.get('filter_confidence', 0):.2f})",
                {"count": len(companies), "fallback": retrieval_result.get("fallback_applied")},
            )
            yield {
                "event": "agent_done",
                "agent": "retrieval_agent",
                "message": f"Retrieved {len(companies)} companies",
                "data": {
                    "count": len(companies),
                    "warnings": retrieval_result.get("warnings", []),
                    "fallback_applied": retrieval_result.get("fallback_applied"),
                },
            }

            yield {"event": "agent_start", "agent": "enrichment_agent", "message": "Enriching company records…"}
            await asyncio.sleep(0.1)

            enriched_companies = self.enricher.run(companies, plan)
            self.agent_logs.extend(self.enricher.logs)

            avg_icp = sum(
                c.get("enrichment", {}).get("icp_score", 0) for c in enriched_companies
            ) / max(len(enriched_companies), 1)

            self._trace(
                f"enrichment_attempt_{iteration}", "enrichment_agent",
                f"Enriched {len(enriched_companies)} companies, avg ICP score {avg_icp:.2f}",
                {"avg_icp": avg_icp},
            )
            yield {
                "event": "agent_done",
                "agent": "enrichment_agent",
                "message": f"Enriched {len(enriched_companies)} companies (avg ICP: {avg_icp:.2f})",
                "data": {"avg_icp_score": avg_icp, "count": len(enriched_companies)},
            }

            yield {"event": "agent_start", "agent": "validation_agent", "message": "Critic validating results…"}
            await asyncio.sleep(0.1)

            validation_result = self.validator.run(query, plan, enriched_companies)
            self.agent_logs.extend(self.validator.logs)

            verdict = validation_result.get("verdict", "partial")
            critical_issues = [i for i in validation_result.get("issues", []) if i.get("severity") == "critical"]

            self._trace(
                f"validation_attempt_{iteration}", "validation_agent",
                f"Verdict: {verdict} — {validation_result.get('reasoning_summary', '')}",
                {"verdict": verdict, "issues": len(validation_result.get("issues", []))},
            )
            yield {
                "event": "agent_done",
                "agent": "validation_agent",
                "message": f"Critic verdict: {verdict.upper()} — {validation_result.get('reasoning_summary', '')}",
                "data": {
                    "verdict": verdict,
                    "confidence": validation_result.get("confidence"),
                    "issues": validation_result.get("issues", []),
                    "critical_count": len(critical_issues),
                },
            }

            if not validation_result.get("should_retry", False):
                break

            retry_count += 1
            if retry_count < MAX_RETRIES:
                instruction = validation_result.get("corrections", {}).get("instruction", "Retrying with relaxed filters")
                yield {
                    "event": "retry",
                    "agent": "orchestrator",
                    "message": f"Critic rejected output — retrying ({retry_count}/{MAX_RETRIES}): {instruction}",
                    "data": {"retry": retry_count, "instruction": instruction},
                }
                await asyncio.sleep(0.2)

        final_companies = validation_result.get("filtered_companies", enriched_companies) if validation_result else enriched_companies

        yield {"event": "agent_start", "agent": "gtm_strategy_agent", "message": "Generating multi-persona GTM strategy…"}
        await asyncio.sleep(0.1)

        gtm_result = self.gtm.run(final_companies, plan, query)
        self.agent_logs.extend(self.gtm.logs)

        self._trace(
            "gtm_strategy", "gtm_strategy_agent",
            f"Strategy generated for {len(gtm_result.get('companies', []))} companies",
            {"confidence": gtm_result.get("confidence")},
        )
        yield {
            "event": "agent_done",
            "agent": "gtm_strategy_agent",
            "message": "GTM strategy complete — hooks, emails, and competitive intel ready",
            "data": {"companies": len(gtm_result.get("companies", []))},
        }

        signals_summary = []
        for c in final_companies:
            signals_summary.extend(c.get("enrichment", {}).get("buying_signals", []))

        entry_id = memory_store.store(
            query=query,
            plan=plan,
            results=[{"id": c.get("id"), "name": c.get("name")} for c in final_companies],
            signals=signals_summary[:20],
            gtm_strategy={"summary": gtm_result.get("overall_gtm_summary", ""), "hooks": gtm_result.get("top_hooks", [])},
            confidence=gtm_result.get("confidence", 0.7),
        )
        self.reasoning_trace.append({"step": "memory_store", "agent": "memory", "summary": f"Stored run {entry_id} to vector memory"})

        elapsed = time.time() - start_time
        final_confidence = (
            plan.get("confidence", 0.7) * 0.2
            + retrieval_result.get("filter_confidence", 0.7) * 0.2
            + (validation_result.get("confidence", 0.7) if validation_result else 0.7) * 0.3
            + gtm_result.get("confidence", 0.7) * 0.3
        )
        results = []
        for c in final_companies:
            enrichment = c.get("enrichment", {})
            results.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "domain": c.get("domain"),
                "industry": c.get("industry"),
                "funding_stage": c.get("funding_stage"),
                "employees": c.get("employees"),
                "growth_rate": c.get("growth_rate"),
                "tech_stack": c.get("tech_stack", []),
                "hiring_roles": c.get("hiring_roles", []),
                "competitors": c.get("competitors", []),
                "icp_score": enrichment.get("icp_score", 0.5),
                "icp_breakdown": enrichment.get("icp_breakdown", {}),
                "buying_signals": enrichment.get("buying_signals", []),
                "derived_insights": enrichment.get("derived_insights", []),
                "data_quality": enrichment.get("data_quality", "medium"),
                "hiring_signals": c.get("hiring_signals", {}),
                "tech_signals": c.get("tech_signals", {}),
            })

        results.sort(key=lambda x: x.get("icp_score", 0), reverse=True)

        final_output = {
            "plan": plan,
            "results": results,
            "signals": signals_summary[:15],
            "gtm_strategy": {
                "companies": gtm_result.get("companies", []),
                "hooks": gtm_result.get("top_hooks", []),
                "overall_summary": gtm_result.get("overall_gtm_summary", ""),
                "confidence": gtm_result.get("confidence", 0.7),
            },
            "validation": {
                "verdict": validation_result.get("verdict") if validation_result else "partial",
                "issues": validation_result.get("issues", []) if validation_result else [],
                "reasoning": validation_result.get("reasoning_summary", "") if validation_result else "",
            },
            "confidence": round(final_confidence, 3),
            "reasoning_trace": [
                {
                    "step": t["step"],
                    "agent": t["agent"],
                    "summary": t["summary"],
                    "status": t.get("status", "done"),
                }
                for t in self.reasoning_trace
            ],
            "meta": {
                "elapsed_seconds": round(elapsed, 2),
                "retry_count": retry_count,
                "memory_entry_id": entry_id,
                "memory_hits": len(memory_hits),
                "total_companies_retrieved": len(enriched_companies),
                "total_companies_after_validation": len(final_companies),
            },
        }
        yield {"event": "complete", "agent": "orchestrator", "message": "Pipeline complete", "data": final_output}