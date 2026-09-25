import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { SourcePanel } from "./components/SourcePanel";
import { href, navigate, useRoute } from "./router";
import { SourceContext, type SourceTarget } from "./sourceContext";
import type { Health, Role } from "./types";
import { AskView } from "./views/AskView";
import { CompareView } from "./views/CompareView";
import { DecisionView } from "./views/DecisionView";
import { InspectView } from "./views/InspectView";

const TABS = [
  { id: "ask", label: "Ask" },
  { id: "compare", label: "Compare" },
  { id: "inspect", label: "Inspect" },
  { id: "decision", label: "Decision" },
];

export default function App() {
  const route = useRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOffline(true));
    api.config().then((c) => setRoles(c.roles)).catch(() => setOffline(true));
  }, []);

  const openSource = useCallback((t: SourceTarget) => setSource(t), []);
  const runParam = route.params.get("run");

  return (
    <SourceContext.Provider value={openSource}>
      <div className="app">
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">N</span>
            <div>
              <div className="brand-name">Policy Assistant Decision Lab</div>
              <div className="brand-sub">Northstar · Should we launch an AI policy assistant?</div>
            </div>
          </div>
          <nav className="tabs-nav" aria-label="Views">
            {TABS.map((t) => (
              <a key={t.id} href={href(t.id, runParam && t.id !== "ask" ? { run: runParam } : {})} className={route.view === t.id ? "active" : ""}>
                {t.label}
              </a>
            ))}
          </nav>
          <div className="mode">
            {health &&
              (health.mode === "fixture" ? (
                <span className="mode-pill mode-fixture" title="No API key configured. AI answers come from saved examples.">
                  Fixture mode · demo data
                </span>
              ) : (
                <span className="mode-pill mode-live" title={`Provider: ${health.provider}`}>
                  Live · {health.model}
                </span>
              ))}
          </div>
        </header>
        {offline && <div className="notice notice-bad banner">Cannot reach the API. Start the backend: <span className="mono">make api</span></div>}
        <main>
          {route.view === "ask" && <AskView health={health} roles={roles} />}
          {route.view === "compare" && <CompareView runId={runParam} onRun={(id) => navigate("compare", { run: id })} />}
          {route.view === "inspect" && <InspectView route={route} />}
          {route.view === "decision" && <DecisionView runId={runParam} onRun={(id) => navigate("decision", { run: id ?? undefined })} />}
        </main>
        {source && <SourcePanel target={source} onClose={() => setSource(null)} />}
      </div>
    </SourceContext.Provider>
  );
}
