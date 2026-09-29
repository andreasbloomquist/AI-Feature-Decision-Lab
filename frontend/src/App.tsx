import { useCallback, useState } from "react";
import { api } from "./api";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ErrorNotice } from "./components/Notice";
import { SourcePanel } from "./components/SourcePanel";
import { ConfigContext } from "./configContext";
import { href, useRoute } from "./router";
import { SourceContext, type SourceTarget } from "./sourceContext";
import { useAsync } from "./useAsync";
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
  const config = useAsync("config", api.config);
  const routeKey = `${route.view}?${route.params.toString()}`;
  // The source drawer belongs to the view it was opened from; navigating away (a tab, Back) closes it.
  const [source, setSource] = useState<{ target: SourceTarget; routeKey: string } | null>(null);
  const openSource = useCallback((target: SourceTarget) => setSource({ target, routeKey }), [routeKey]);
  const closeSource = useCallback(() => setSource(null), []);
  // Clear (not just hide) a drawer from another route, so Back or returning to the view doesn't reopen it.
  if (source && source.routeKey !== routeKey) setSource(null);
  const runParam = route.params.get("run");
  const settings = config.data?.settings;

  return (
    <ConfigContext.Provider value={config.data}>
      <SourceContext.Provider value={openSource}>
        <div className="app">
          <header className="topbar">
            <div className="brand">
              <span className="brand-mark" aria-hidden="true">
                N
              </span>
              <div>
                <div className="brand-name">Policy Assistant Decision Lab</div>
                <div className="brand-sub">Northstar · Should we launch an AI policy assistant?</div>
              </div>
            </div>
            <nav className="tabs-nav" aria-label="Views">
              {TABS.map((t) => (
                <a
                  key={t.id}
                  href={href(t.id, runParam && t.id !== "ask" ? { run: runParam } : {})}
                  className={route.view === t.id ? "active" : ""}
                  aria-current={route.view === t.id ? "page" : undefined}
                >
                  {t.label}
                </a>
              ))}
            </nav>
            <div className="mode">
              {settings &&
                (settings.mode === "fixture" ? (
                  <span className="mode-pill mode-fixture" title="No API key configured. AI answers come from saved examples.">
                    Fixture mode · demo data
                  </span>
                ) : (
                  <span className="mode-pill mode-live" title={`Provider: ${settings.provider}`}>
                    Live · {settings.model}
                  </span>
                ))}
            </div>
          </header>
          {config.error && (
            <div className="banner">
              <ErrorNotice error={config.error} onRetry={config.reload} />
            </div>
          )}
          <main>
            <ErrorBoundary resetKey={routeKey}>
              {route.view === "ask" && (
                // Keyed so a deep link to a different question resets the form.
                <AskView
                  key={`${route.params.get("q")}:${route.params.get("role")}`}
                  initialQuestion={route.params.get("q")}
                  initialRole={route.params.get("role")}
                />
              )}
              {route.view === "compare" && <CompareView runParam={runParam} splitParam={route.params.get("split")} />}
              {route.view === "inspect" && <InspectView route={route} />}
              {route.view === "decision" && <DecisionView runParam={runParam} />}
            </ErrorBoundary>
          </main>
          {source?.routeKey === routeKey && (
            <ErrorBoundary resetKey={routeKey}>
              <SourcePanel target={source.target} onClose={closeSource} />
            </ErrorBoundary>
          )}
        </div>
      </SourceContext.Provider>
    </ConfigContext.Provider>
  );
}
