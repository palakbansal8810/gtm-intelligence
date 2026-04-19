import { useState, useRef, useCallback } from "react";
import "./App.css";

const API_BASE = process.env.REACT_APP_API_URL || "https://gtm-intelligence-1.onrender.com";

const AGENT_META = {
  memory:             { label: "Memory",       icon: "◈", color: "#7a7aff" },
  planner_agent:      { label: "Planner",      icon: "◎", color: "#5a9cf5" },
  retrieval_agent:    { label: "Retrieval",    icon: "⊕", color: "#4aaa7a" },
  enrichment_agent:   { label: "Enrichment",   icon: "⊗", color: "#c8962a" },
  validation_agent:   { label: "Critic",       icon: "⊘", color: "#c04040" },
  gtm_strategy_agent: { label: "GTM Strategy", icon: "⊙", color: "#c070a0" },
  orchestrator:       { label: "Orchestrator", icon: "◉", color: "#4f6ef7" },
};

const EXAMPLE_QUERIES = [
  "Find high-growth AI SaaS companies in the US and generate personalized outbound hooks for their VP Sales.",
  "Identify fintech startups hiring aggressively and suggest outreach strategies.",
  "Give me DevOps companies likely to churn competitors and how to target their CTO.",
];

function TimelineEvent({ event, index }) {
  const meta = AGENT_META[event.agent] || { label: event.agent, icon: "◌", color: "#555" };
  const isRetry = event.event === "retry" || event.event === "retry_correction";
  const isError = event.event === "error";
  const isMemory = event.event === "memory_hit";

  return (
    <div
      className={`timeline-event ${isRetry ? "retry" : ""} ${isError ? "error" : ""}`}
      style={{ "--agent-color": meta.color, animationDelay: `${index * 0.04}s` }}
    >
      <div className="event-connector">
        <div className="event-dot" />
        {index > 0 && <div className="event-line" />}
      </div>
      <div className="event-body">
        <div className="event-header">
          <span className="event-agent-label" style={{ color: meta.color }}>
            {meta.icon} {meta.label}
          </span>
          {isRetry && <span className="badge retry-badge">↺ RETRY</span>}
          {isMemory && <span className="badge memory-badge">⚡ CACHED</span>}
          {isError && <span className="badge error-badge">✗ ERROR</span>}
        </div>
        <p className="event-message">{event.message}</p>
        {event.data && Object.keys(event.data).length > 0 && (
          <div className="event-data">
            {Object.entries(event.data).map(([k, v]) => {
              if (k === "issues" && Array.isArray(v)) return null;
              if (k === "filters" && typeof v === "object") return null;
              const val = typeof v === "object" ? JSON.stringify(v) : String(v);
              if (val === "null" || val === "undefined") return null;
              return (
                <span key={k} className="data-chip">
                  {k}: <strong>{val.length > 28 ? val.slice(0, 28) + "…" : val}</strong>
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ConfidenceMeter({ value, label }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 70 ? "#3d9e6e" : pct >= 40 ? "#c8962a" : "#c04040";
  return (
    <div className="confidence-meter">
      <div className="cm-header">
        <span className="cm-label">{label}</span>
        <span className="cm-value" style={{ color }}>{pct}%</span>
      </div>
      <div className="cm-track">
        <div className="cm-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function CompanyCard({ company, strategy }) {
  const [expanded, setExpanded] = useState(false);
  const [activePersona, setActivePersona] = useState("VP Sales");

  const icp = Math.round((company.icp_score || 0) * 100);
  const icpColor = icp >= 70 ? "#3d9e6e" : icp >= 40 ? "#c8962a" : "#c04040";
  const strat = strategy?.persona_strategies || {};
  const personas = Object.keys(strat);
  const compIntel = strategy?.competitive_intel || {};

  return (
    <div className={`company-card ${expanded ? "expanded" : ""}`}>
      <div className="card-header" onClick={() => setExpanded(!expanded)}>
        <div className="card-title-row">
          <div className="card-title-info">
            <h3 className="card-company-name">{company.name}</h3>
            <div className="card-meta">
              <span className="meta-chip industry">{company.industry}</span>
              <span className="meta-chip funding">{company.funding_stage}</span>
              {company.employees && <span className="meta-chip">{company.employees} emp</span>}
              {company.growth_rate && (
                <span className="meta-chip growth">{Math.round(company.growth_rate * 100)}% growth</span>
              )}
            </div>
          </div>
          <div className="card-icp">
            <svg viewBox="0 0 36 36" className="icp-ring">
              <circle cx="18" cy="18" r="15" fill="none" stroke="#222" strokeWidth="3" />
              <circle
                cx="18" cy="18" r="15" fill="none"
                stroke={icpColor} strokeWidth="3"
                strokeDasharray={`${(icp / 100) * 94.2} 94.2`}
                strokeLinecap="round"
                transform="rotate(-90 18 18)"
              />
            </svg>
            <div className="icp-score-text">
              <span className="icp-num" style={{ color: icpColor }}>{icp}</span>
              <span className="icp-sub">ICP</span>
            </div>
          </div>
        </div>
        <div className="card-signals">
          {(company.buying_signals || []).slice(0, 3).map((sig, i) => (
            <span key={i} className="signal-tag">⚡ {sig}</span>
          ))}
        </div>
        <div className="card-expand-hint">{expanded ? "▲ collapse" : "▼ view strategy"}</div>
      </div>

      {expanded && (
        <div className="card-body">
          {personas.length > 0 && (
            <div className="persona-section">
              <h4 className="section-title">Multi-Persona Strategy</h4>
              <div className="persona-tabs">
                {personas.map((p) => (
                  <button
                    key={p}
                    className={`persona-tab ${activePersona === p ? "active" : ""}`}
                    onClick={() => setActivePersona(p)}
                  >
                    {p === "CEO" ? "👔" : p === "VP Sales" ? "📈" : "⚙️"} {p}
                  </button>
                ))}
              </div>
              {strat[activePersona] && (
                <div className="persona-content">
                  <div className="persona-hook">
                    <span className="hook-label">Hook</span>
                    <p>{strat[activePersona].hook}</p>
                  </div>
                  <div className="persona-angle">
                    <span className="hook-label">Angle</span>
                    <span className="angle-badge">{strat[activePersona].angle}</span>
                  </div>
                  <div className="persona-email">
                    <span className="hook-label">Email Opening</span>
                    <blockquote>{strat[activePersona].email_snippet}</blockquote>
                  </div>
                  {strat[activePersona].talking_points?.length > 0 && (
                    <div className="talking-points">
                      <span className="hook-label">Talking Points</span>
                      <ul>
                        {strat[activePersona].talking_points.map((tp, i) => (
                          <li key={i}>{tp}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {compIntel.key_competitors?.length > 0 && (
            <div className="comp-intel-section">
              <h4 className="section-title">Competitive Intelligence</h4>
              <div className="comp-intel-grid">
                <div className="ci-item">
                  <span className="ci-label">Competitors</span>
                  <div>{compIntel.key_competitors.map((c, i) => <span key={i} className="comp-chip">{c}</span>)}</div>
                </div>
                {compIntel.competitor_weaknesses && (
                  <div className="ci-item">
                    <span className="ci-label">Their Weaknesses</span>
                    <p>{compIntel.competitor_weaknesses}</p>
                  </div>
                )}
                {compIntel.our_positioning && (
                  <div className="ci-item">
                    <span className="ci-label">Our Positioning</span>
                    <p>{compIntel.our_positioning}</p>
                  </div>
                )}
                {compIntel.displacement_strategy && (
                  <div className="ci-item">
                    <span className="ci-label">Displacement Strategy</span>
                    <p>{compIntel.displacement_strategy}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {strategy?.urgency_signal && (
            <div className="urgency-row">
              <span>🔥</span>
              <span className="urgency-text">{strategy.urgency_signal}</span>
            </div>
          )}

          {company.icp_breakdown && (
            <div className="icp-breakdown">
              <h4 className="section-title">ICP Score Breakdown</h4>
              <ConfidenceMeter value={company.icp_breakdown.fit_score} label="Fit" />
              <ConfidenceMeter value={company.icp_breakdown.intent_score} label="Intent" />
              <ConfidenceMeter value={company.icp_breakdown.growth_score} label="Growth" />
            </div>
          )}

          {company.tech_stack?.length > 0 && (
            <div className="tech-stack-row">
              <span className="hook-label">Tech Stack</span>
              <div>{company.tech_stack.map((t, i) => <span key={i} className="tech-chip">{t}</span>)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReasoningTrace({ trace }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="reasoning-trace">
      <button className="trace-toggle" onClick={() => setOpen(!open)}>
        {open ? "▲" : "▼"} Reasoning Trace ({trace.length} steps)
      </button>
      {open && (
        <div className="trace-list">
          {trace.map((t, i) => (
            <div key={i} className="trace-step">
              <span className="trace-num">{String(i + 1).padStart(2, "0")}</span>
              <span className="trace-agent">{t.agent}</span>
              <span className="trace-summary">{t.summary}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const addEvent = useCallback((ev) => {
    setEvents((prev) => [...prev, ev]);
  }, []);

  const run = useCallback(async () => {
    if (!query.trim() || running) return;
    setRunning(true);
    setEvents([]);
    setResult(null);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: abortRef.current?.signal,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "API error");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const dataLine = part.split("\n").find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          try {
            const ev = JSON.parse(dataLine.slice(5));
            if (ev.event === "complete") setResult(ev.data);
            else if (ev.event === "error") setError(ev.message);
            else addEvent(ev);
          } catch {}
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setRunning(false);
    }
  }, [query, running, addEvent]);

  const activeAgents = new Set(events.filter(e => e.event === "agent_start").map(e => e.agent));
  const doneAgents   = new Set(events.filter(e => e.event === "agent_done").map(e => e.agent));

  const resultCompanies = result?.results || [];
  const gtmCompanies = result?.gtm_strategy?.companies || [];
  const getStrategy = (id) => gtmCompanies.find((c) => c.company_id === id) || null;

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo">GTM<span>Intel</span></div>
          <div className="header-sub">Multi-Agent GTM Intelligence System</div>
          <div className="agent-status-row">
            {Object.entries(AGENT_META).map(([key, meta]) => (
              <div
                key={key}
                className={`status-dot ${doneAgents.has(key) ? "done" : activeAgents.has(key) ? "active" : "idle"}`}
                style={{ "--c": meta.color }}
                title={meta.label}
              >
                {meta.icon}
              </div>
            ))}
          </div>
        </div>
      </header>

      <main className="main">
        <section>
          <div className="query-box">
            <textarea
              className="query-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter a GTM query… e.g. 'Find high-growth AI SaaS companies hiring VP Sales'"
              rows={3}
              disabled={running}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run(); }}
            />
            <div className="query-actions">
              <div className="examples">
                {EXAMPLE_QUERIES.map((q, i) => (
                  <button key={i} className="example-btn" onClick={() => setQuery(q)} disabled={running}>
                    {q.slice(0, 55)}…
                  </button>
                ))}
              </div>
              <button className="run-btn" onClick={run} disabled={running || !query.trim()}>
                {running ? <><span className="spinner" />Running…</> : <>Run Pipeline</>}
              </button>
            </div>
          </div>
        </section>

        <div className="two-col">
          {/* Left: Timeline */}
          <div className="col-left">
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">Execution Timeline</span>
                {running && <span className="live-badge">● LIVE</span>}
              </div>
              <div className="timeline">
                {events.length === 0 && !running && (
                  <div className="empty-state">Run a query to see agent execution…</div>
                )}
                {events.map((ev, i) => <TimelineEvent key={i} event={ev} index={i} />)}
                {running && (
                  <div className="timeline-pulse">
                    <div className="pulse-dot" />
                    <span>Processing…</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right: Results */}
          <div className="col-right">
            {result && (
              <>
                <div className="panel meta-panel">
                  <div className="panel-header">
                    <span className="panel-title">Pipeline Summary</span>
                  </div>
                  <ConfidenceMeter value={result.confidence} label="Overall Confidence" />
                  <div className="meta-grid">
                    <div className="meta-item">
                      <span className="mi-num">{result.meta?.total_companies_retrieved}</span>
                      <span className="mi-label">Retrieved</span>
                    </div>
                    <div className="meta-item">
                      <span className="mi-num">{result.meta?.total_companies_after_validation}</span>
                      <span className="mi-label">Validated</span>
                    </div>
                    <div className="meta-item">
                      <span className="mi-num">{result.meta?.retry_count}</span>
                      <span className="mi-label">Retries</span>
                    </div>
                    <div className="meta-item">
                      <span className="mi-num">{result.meta?.elapsed_seconds}s</span>
                      <span className="mi-label">Duration</span>
                    </div>
                    <div className="meta-item">
                      <span className="mi-num">{result.meta?.memory_hits}</span>
                      <span className="mi-label">Mem Hits</span>
                    </div>
                  </div>
                  <div className={`verdict-badge verdict-${result.validation?.verdict}`}>
                    {result.validation?.verdict === "accept" ? "✓ ACCEPTED"
                     : result.validation?.verdict === "reject" ? "✗ REJECTED" : "~ PARTIAL"}
                    <span className="verdict-reason">{result.validation?.reasoning}</span>
                  </div>
                </div>

                {result.gtm_strategy?.overall_summary && (
                  <div className="panel">
                    <div className="panel-header"><span className="panel-title">GTM Overview</span></div>
                    <p className="gtm-summary">{result.gtm_strategy.overall_summary}</p>
                    {result.gtm_strategy.hooks?.length > 0 && (
                      <div>
                        <span className="hook-label">Top Hooks</span>
                        {result.gtm_strategy.hooks.map((h, i) => (
                          <div key={i} className="top-hook">"{h}"</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="panel">
                  <div className="panel-header"><span className="panel-title">Execution Plan</span></div>
                  <div className="plan-grid">
                    <div>
                      <span className="plan-label">Strategy</span>
                      <span className="plan-val">{result.plan?.strategy}</span>
                    </div>
                    <div>
                      <span className="plan-label">Tasks</span>
                      <div>{result.plan?.tasks?.map((t, i) => <span key={i} className="task-chip">{t}</span>)}</div>
                    </div>
                    <div>
                      <span className="plan-label">Personas</span>
                      <div>{result.plan?.target_personas?.map((p, i) => <span key={i} className="persona-chip">{p}</span>)}</div>
                    </div>
                  </div>
                  <ConfidenceMeter value={result.plan?.confidence} label="Plan Confidence" />
                </div>

                {resultCompanies.length > 0 && (
                  <div className="panel">
                    <div className="panel-header">
                      <span className="panel-title">Companies ({resultCompanies.length})</span>
                      <span className="panel-sub">ranked by ICP score · click to expand</span>
                    </div>
                    <div className="company-list">
                      {resultCompanies.map((c) => (
                        <CompanyCard key={c.id} company={c} strategy={getStrategy(c.id)} />
                      ))}
                    </div>
                  </div>
                )}

                {result.reasoning_trace?.length > 0 && (
                  <div className="panel">
                    <ReasoningTrace trace={result.reasoning_trace} />
                  </div>
                )}
              </>
            )}

            {error && (
              <div className="error-panel">
                <span className="error-icon">⊘</span>
                <div>
                  <strong>Pipeline Error</strong>
                  <p>{error}</p>
                </div>
              </div>
            )}

            {!result && !error && !running && (
              <div className="panel empty-results">
                <span className="empty-icon">◉</span>
                <p>Results will appear here once you run a query.</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}