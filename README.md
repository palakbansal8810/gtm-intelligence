# GTM Intelligence System 🧠
### Multi-Agent Go-To-Market Intelligence + Outbound Engine

---

## Overview

A distributed multi-agent AI system that accepts a natural language GTM query, decomposes it into structured sub-tasks, and uses autonomous agents to plan, retrieve, enrich, validate, rank, and generate outbound intelligence.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Query                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │    Vector Memory (RAG)   │  ← FAISS similarity search
              │  Check for past runs    │    Pseudo-embeddings (hash)
              └────────────┬────────────┘
                           │ (cache hit → inject context)
              ┌────────────▼────────────┐
              │      Planner Agent      │  ← Claude API
              │  Decompose → structured │    Uses memory context hints
              │  plan + filters         │
              └────────────┬────────────┘
                           │
         ┌─────────────────▼──────────────────────┐
         │           RETRY LOOP (max 3)            │
         │                                         │
         │  ┌──────────────────────────────────┐   │
         │  │      Retrieval Agent             │   │
         │  │  Validate & refine filters       │   │
         │  │  Call mock/explorium company API          │   │   
         │  │  Handle empty/over-constrained   │   │
         │  └──────────────┬───────────────────┘   │
         │                 │                        │
         │  ┌──────────────▼───────────────────┐   │
         │  │      Enrichment Agent            │   │
         │  │  Hiring signals (mock/explorium API)       │   │  
         │  │  Tech signals (mock/explorium API)         │   │
         │  │  ICP scoring (fit/intent/growth) │   │
         │  │  Buying signal detection         │   │
         │  └──────────────┬───────────────────┘   │
         │                 │                        │
         │  ┌──────────────▼───────────────────┐   │
         │  │   Critic / Validation Agent      │   │
         │  │  Relevance check                 │   │
         │  │  Hallucination detection         │   │
         │  │  Verdict: accept/partial/reject  │   │
         │  │  Correction instructions         │   │
         │  └──────────────┬───────────────────┘   │
         │                 │                        │
         │     verdict=reject → retry ─────────────┘
         └─────────────────┬──────────────────────────┘
                           │ (accept or partial)
              ┌────────────▼────────────┐
              │    GTM Strategy Agent   │  ← Groq api
              │  Multi-persona targeting│
              │  • CEO hooks            │
              │  • VP Sales hooks       │
              │  • CTO hooks            │
              │  Competitive intel      │
              │  • Competitor mapping   │
              │  • Positioning strategy │
              │  • Displacement tactics │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │   Store to Vector Memory │
              │   (for future queries)   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │    Final JSON Output    │
              │  + SSE stream to UI     │
              └─────────────────────────┘
```

---

## Agent Details

### 1. Planner Agent (`agents/planner_agent.py`)
- Parses natural language GTM query
- Outputs structured execution plan: entity_type, tasks, filters, target_personas, strategy, confidence
- Uses vector memory context from similar past queries to improve plans
- Fallback plan on parse errors

### 2. Retrieval Agent (`agents/retrieval_agent.py`)
- Validates and refines planner filters via Claude
- Calls mock/explorium company search APIs
- Handles over-constrained queries with automatic filter relaxation
- Tracks filter confidence and fallback status

### 3. Enrichment Agent (`agents/enrichment_agent.py`)
- Fetches hiring signals per company
- Fetches tech stack / intent signals per company
- Generates ICP score breakdown: fit, intent, growth
- Detects buying signals (funding, hiring VP Sales, tech migrations)
- Handles partial/noisy/missing data with graceful fallbacks

### 4. Validation / Critic Agent (`agents/validation_agent.py`) 
- Evaluates result relevance to original query
- Detects hallucinated filters and invalid assumptions
- Issues verdict: `accept`, `partial`, or `reject`
- Provides correction instructions for re-planning
- Filters out irrelevant companies from results

### 5. GTM Strategy Agent (`agents/gtm_strategy_agent.py`)
**Multi-Persona Targeting:**
- **CEO**: Strategic/revenue/risk angles
- **VP Sales**: Pipeline/quota/tools/efficiency angles
- **CTO**: Tech/scale/security/engineering velocity angles

**Competitive Intelligence:**
- Maps key competitors per company
- Identifies competitor weaknesses
- Generates positioning strategy
- Suggests displacement tactics

---

## Memory System

### Vector Memory (RAG-style) (`memory/vector_memory.py`)
- **Storage**: Each completed run stored with query, plan, results, signals, GTM strategy
- **Retrieval**: FAISS inner-product search on query embeddings (cosine similarity on normalized vectors)
- **Embeddings**: Deterministic pseudo-embeddings via MD5 hashing
- **Cache hit**: When similarity ≥ 0.75, past context injected into Planner prompt
- **Use cases**: Avoid repeated API calls, improve future responses, store intermediate reasoning
- **Capacity**: 500 entries with automatic LRU eviction

## Orchestration Loop

```
Planner → Retrieval → Enrichment → Critic
              ↑                       ↓
              └──── (if reject) ──────┘
              
Max retries: 3
On reject: apply critic's revised_filters, re-run Retrieval → Enrichment → Critic
```

---

## Output Schema

```json
{
  "plan": {
    "entity_type": "company",
    "tasks": ["search", "enrich", "analyze", "generate_outreach"],
    "filters": {"industry": "AI SaaS", "country": "US", "min_growth_rate": 0.5},
    "target_personas": ["CEO", "VP Sales", "CTO"],
    "strategy": "...",
    "confidence": 0.85
  },
  "results": [
    {
      "id": "c001",
      "name": "Nexus AI",
      "icp_score": 0.82,
      "icp_breakdown": {"fit_score": 0.85, "intent_score": 0.78, "growth_score": 0.83},
      "buying_signals": ["Hiring VP Sales", "Recently adopted Salesforce"],
      "derived_insights": ["..."],
      "data_quality": "high"
    }
  ],
  "signals": ["Hiring VP Sales", "Series B funding", "..."],
  "gtm_strategy": {
    "companies": [
      {
        "company_id": "c001",
        "persona_strategies": {
          "CEO": {"hook": "...", "angle": "growth", "email_snippet": "...", "talking_points": []},
          "VP Sales": {"hook": "...", "angle": "pipeline", "email_snippet": "...", "talking_points": []},
          "CTO": {"hook": "...", "angle": "scale", "email_snippet": "...", "talking_points": []}
        },
        "competitive_intel": {
          "key_competitors": ["Scale AI", "Labelbox"],
          "competitor_weaknesses": "...",
          "our_positioning": "...",
          "displacement_strategy": "..."
        },
        "urgency_signal": "Currently hiring VP Sales — active buying moment"
      }
    ],
    "hooks": ["Top hook 1", "Top hook 2", "Top hook 3"],
    "overall_summary": "..."
  },
  "validation": {
    "verdict": "accept",
    "issues": [],
    "reasoning": "..."
  },
  "confidence": 0.81,
  "reasoning_trace": [
    {"step": "memory_lookup", "agent": "memory", "summary": "Cache hit: 2 similar queries"},
    {"step": "planning", "agent": "planner_agent", "summary": "Plan created: 4 tasks, confidence 0.85"},
    ...
  ],
  "meta": {
    "elapsed_seconds": 12.4,
    "retry_count": 0,
    "memory_entry_id": "abc123",
    "memory_hits": 2,
    "total_companies_retrieved": 6,
    "total_companies_after_validation": 5
  }
}
```

---

## Setup & Running

### Prerequisites
- Python 3.11+
- Node.js 18+
- Groq and Explorium API key

### Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Set API key
export GROQ_API_KEY=..
export EXPLORIUM_API_KEY=..

# Run development server
python main.py
# → API available at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
REACT_APP_API_URL=http://localhost:8000 npm start
# → UI available at http://localhost:3000

LIVE_URL= 'https://gtm-intelligence-zeta.vercel.app/'
## Failure Handling

| Failure Type | Handling |
|---|---|
| Empty API results | Filter relaxation fallback |
| Claude JSON parse error | Structured fallback objects |
| Claude API rate limit | Exponential backoff (tenacity, 3 retries) |
| Critic rejects output | Re-plan with revised filters (max 3 loops) |
| Missing company fields | `data_quality: low`, flagged in output |
| Hallucinated filters | Critic detects and removes |

---

## Advanced Features Implemented

| Feature | Implementation |
|---|---|
|5 Agents | Planner, Retrieval, Enrichment, Critic, GTM Strategy |
|Iterative retry loop | Critic → reject → re-plan, max 3 cycles |
|Vector Memory (RAG) | FAISS inner-product search, cosine similarity |
|Multi-Persona Targeting | CEO / VP Sales / CTO — distinct hooks + angles |
|Competitive Intelligence | Competitors, weaknesses, positioning, displacement |
|Hallucination detection | Critic agent flags invalid filters/assumptions |
|ICP Scoring Engine | fit × 40% + intent × 30% + growth × 30% |
|Buying Signal Detection | Hiring trends, tech migrations, funding stage |
|SSE Streaming | Real-time agent execution updates |
|Rate limiting | 10 req/min per IP |
|Confidence scores | Per agent + weighted final score |
|Fallback strategies | Every agent has graceful degradation |
|Structured logging | Agent-level logs with timing |
