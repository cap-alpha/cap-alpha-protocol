import { Metadata } from "next";
import { Shield, Key, Terminal, ArrowRight, CheckCircle2, AlertCircle, Code2, Zap } from "lucide-react";
import Link from "next/link";
import { DisplayHeading } from "@/components/ui/heading";

export const metadata: Metadata = {
    title: "API Reference | Pundit Ledger",
    description:
        "REST API documentation for the Pundit Prediction Ledger. Integrate pundit accuracy scores, prediction history, and draft results into your app.",
};

const BASE_URL = "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

// ---------------------------------------------------------------------------
// Reusable components
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent-editorial/30 bg-accent-editorial/10 text-accent-editorial text-xs font-mono font-medium uppercase tracking-widest">
            {children}
        </span>
    );
}

function CodeBlock({ children, language = "bash" }: { children: string; language?: string }) {
    return (
        <div className="relative rounded-xl border border-editorial-border bg-editorial-bg overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2 border-b border-editorial-border bg-editorial-card">
                <Code2 className="w-3.5 h-3.5 text-ink-3" />
                <span className="text-xs font-mono text-ink-3">{language}</span>
            </div>
            <pre className="overflow-x-auto p-4 text-sm text-ink-2 leading-relaxed">
                <code>{children}</code>
            </pre>
        </div>
    );
}

function ParamTable({
    params,
}: {
    params: { name: string; type: string; required: boolean; description: string; example?: string }[];
}) {
    return (
        <div className="overflow-x-auto rounded-xl border border-editorial-border">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-editorial-border bg-editorial-card">
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Name</th>
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Type</th>
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Required</th>
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Description</th>
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Example</th>
                    </tr>
                </thead>
                <tbody>
                    {params.map((p, i) => (
                        <tr key={p.name} className={i % 2 === 0 ? "bg-editorial-bg" : "bg-editorial-card"}>
                            <td className="px-4 py-3 font-mono text-accent-editorial">{p.name}</td>
                            <td className="px-4 py-3 font-mono text-ink-2">{p.type}</td>
                            <td className="px-4 py-3">
                                {p.required ? (
                                    <span className="text-correct font-mono text-xs">yes</span>
                                ) : (
                                    <span className="text-ink-3 font-mono text-xs">no</span>
                                )}
                            </td>
                            <td className="px-4 py-3 text-ink-2">{p.description}</td>
                            <td className="px-4 py-3 font-mono text-ink-3 text-xs">{p.example ?? "—"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function ErrorTable({ codes }: { codes: { code: number; meaning: string }[] }) {
    return (
        <div className="overflow-x-auto rounded-xl border border-editorial-border">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-editorial-border bg-editorial-card">
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">HTTP status</th>
                        <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Meaning</th>
                    </tr>
                </thead>
                <tbody>
                    {codes.map((c, i) => (
                        <tr key={c.code} className={i % 2 === 0 ? "bg-editorial-bg" : "bg-editorial-card"}>
                            {/* FLAG: orange-400 (HTTP error status codes) collapses to incorrect per spec exception */}
                            <td className="px-4 py-3 font-mono text-incorrect">{c.code}</td>
                            <td className="px-4 py-3 text-ink-2">{c.meaning}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function EndpointCard({
    method,
    path,
    description,
    children,
}: {
    method: "GET" | "POST";
    path: string;
    description: string;
    children: React.ReactNode;
}) {
    return (
        <div id={path.replace(/\//g, "-").replace(/[{}]/g, "").replace(/^-/, "")} className="rounded-2xl border border-editorial-border bg-editorial-card overflow-hidden">
            <div className="flex flex-wrap items-center gap-3 px-6 py-4 border-b border-editorial-border bg-editorial-card">
                <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${method === "GET" ? "bg-correct/20 text-correct" : "bg-accent-editorial/20 text-accent-editorial"}`}>
                    {method}
                </span>
                <code className="text-ink font-mono text-sm">{path}</code>
                <span className="text-ink-3 text-sm">{description}</span>
            </div>
            <div className="p-6 space-y-6">{children}</div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ApiDocsPage() {
    return (
        <div className="bg-editorial-bg text-ink min-h-[100dvh] flex flex-col font-sans">
            {/* Hero */}
            <section className="relative flex flex-col items-center justify-center text-center px-6 pt-24 pb-16 overflow-hidden">
                <div className="relative z-10 max-w-3xl mx-auto space-y-6">
                    <SectionLabel>
                        <Terminal className="w-3.5 h-3.5" />
                        REST API
                    </SectionLabel>
                    <DisplayHeading size="md" className="font-display sm:text-display-lg">
                        Pundit Ledger{" "}
                        <span className="text-accent-editorial">API Reference</span>
                    </DisplayHeading>
                    <p className="text-xl text-ink-2 max-w-xl mx-auto leading-relaxed">
                        Integrate pundit accuracy scores, prediction history, and draft
                        results into your app, betting tool, or agent.
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                        <code className="px-4 py-2 rounded-lg bg-editorial-card border border-editorial-border text-accent-editorial font-mono text-sm">
                            {BASE_URL}
                        </code>
                    </div>
                </div>
            </section>

            {/* Navigation */}
            <nav className="sticky top-0 z-20 w-full border-y border-editorial-border bg-editorial-bg/80 backdrop-blur-sm">
                <div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-6 overflow-x-auto text-sm">
                    <span className="text-ink-3 text-xs font-mono uppercase tracking-widest shrink-0">Jump to:</span>
                    {[
                        ["Quick start", "#quick-start"],
                        ["Auth", "#auth"],
                        ["Rate limits", "#rate-limits"],
                        ["Leaderboard", "#v1-leaderboard"],
                        ["Pundits", "#v1-pundits-"],
                        ["Predictions", "#v1-predictions-"],
                        ["Draft", "#v1-draft-year"],
                        ["Integrity", "#v1-integrity-verify"],
                    ].map(([label, href]) => (
                        <a
                            key={href}
                            href={href}
                            className="shrink-0 text-ink-2 hover:text-accent-editorial transition-colors"
                        >
                            {label}
                        </a>
                    ))}
                </div>
            </nav>

            <div className="max-w-5xl mx-auto w-full px-6 py-16 space-y-20">

                {/* Quick start */}
                <section id="quick-start" className="space-y-8">
                    <div className="space-y-3">
                        <SectionLabel><Zap className="w-3.5 h-3.5" /> Quick start</SectionLabel>
                        <h2 className="text-3xl font-black text-ink">Get up and running in 2 minutes</h2>
                    </div>

                    <div className="grid sm:grid-cols-3 gap-4">
                        {[
                            {
                                step: "1",
                                icon: Key,
                                title: "Get an API key",
                                desc: "Sign in at cap-alpha.co and create a key from your account dashboard. Keys look like capk_live_...",
                            },
                            {
                                step: "2",
                                icon: Terminal,
                                title: "Make your first call",
                                desc: "Pass your key in the x-api-key header on every request.",
                            },
                            {
                                step: "3",
                                icon: CheckCircle2,
                                title: "Explore & build",
                                desc: "Browse the endpoint reference below or use the interactive schema at /docs on the base URL.",
                            },
                        ].map(({ step, icon: Icon, title, desc }) => (
                            <div key={step} className="rounded-xl border border-editorial-border bg-editorial-card p-5 space-y-3">
                                <div className="flex items-center gap-3">
                                    <span className="w-6 h-6 rounded-full bg-accent-editorial/20 border border-accent-editorial/30 flex items-center justify-center text-xs font-bold text-accent-editorial">
                                        {step}
                                    </span>
                                    <Icon className="w-4 h-4 text-accent-editorial" />
                                </div>
                                <h3 className="font-semibold text-ink">{title}</h3>
                                <p className="text-sm text-ink-2 leading-relaxed">{desc}</p>
                            </div>
                        ))}
                    </div>

                    <CodeBlock language="bash">{`curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/leaderboard?limit=5" \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                </section>

                {/* Auth */}
                <section id="auth" className="space-y-6">
                    <div className="space-y-3">
                        <SectionLabel><Shield className="w-3.5 h-3.5" /> Authentication</SectionLabel>
                        <h2 className="text-3xl font-black text-ink">API key authentication</h2>
                        <p className="text-ink-2 leading-relaxed max-w-2xl">
                            API-key enforcement is <strong className="text-ink">active</strong> on all data endpoints.
                            Every request to <code className="font-mono text-sm text-ink-2">/v1/*</code> endpoints requires a valid <code className="font-mono text-sm text-ink-2">x-api-key</code> header.
                            Keys are provisioned via your Cap Alpha dashboard and are validated against your account in real-time.
                        </p>
                    </div>
                    <CodeBlock language="bash">{`# Pass your key in this header (required for all /v1/* endpoints)
x-api-key: capk_live_your_key`}</CodeBlock>
                    <div className="rounded-xl border border-pending/20 bg-pending/5 p-4 flex items-start gap-3">
                        <AlertCircle className="w-4 h-4 text-pending mt-0.5 shrink-0" />
                        <p className="text-sm text-ink-2">
                            Never expose your API key in client-side code or public repositories.
                            If a key is compromised, rotate it from your dashboard immediately.
                        </p>
                    </div>
                    <div>
                        <p className="text-sm text-ink-3 mb-3">Error response when key is missing or invalid:</p>
                        <CodeBlock language="json">{`HTTP 401
{ "detail": "Invalid or missing API key" }`}</CodeBlock>
                    </div>
                </section>

                {/* Rate limits */}
                <section id="rate-limits" className="space-y-6">
                    <div className="space-y-3">
                        <SectionLabel>Rate limits</SectionLabel>
                        <h2 className="text-3xl font-black text-ink">Tiers &amp; rate limits</h2>
                        <p className="text-ink-2 leading-relaxed max-w-2xl">
                            API access scales with your subscription tier. The number of active keys and
                            request throughput both increase as you upgrade.
                        </p>
                    </div>
                    <div className="overflow-x-auto rounded-xl border border-editorial-border">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-editorial-border bg-editorial-card">
                                    <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Tier</th>
                                    <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Max active keys</th>
                                    <th className="text-left px-4 py-3 text-ink-2 font-mono font-medium">Notes</th>
                                </tr>
                            </thead>
                            <tbody>
                                {[
                                    ["free", "1", "Public leaderboard, limited history"],
                                    ["pro", "3", "Full prediction history, multi-sport"],
                                    ["api_starter", "10", "Suitable for small integrations"],
                                    ["enterprise", "25", "High-volume, priority support"],
                                ].map(([tier, keys, notes], i) => (
                                    <tr key={tier} className={i % 2 === 0 ? "bg-editorial-bg" : "bg-editorial-card"}>
                                        <td className="px-4 py-3 font-mono text-accent-editorial">{tier}</td>
                                        <td className="px-4 py-3 font-mono text-ink-2">{keys}</td>
                                        <td className="px-4 py-3 text-ink-2">{notes}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="text-sm text-ink-3">
                        Rate-limited requests receive <code className="font-mono text-ink-2">HTTP 429</code>.
                        Contact <a href="mailto:support@cap-alpha.co" className="text-accent-editorial hover:text-accent-editorial-light">support@cap-alpha.co</a> to upgrade.
                    </p>
                </section>

                {/* Endpoint reference */}
                <section className="space-y-8">
                    <div className="space-y-3">
                        <SectionLabel><Code2 className="w-3.5 h-3.5" /> Endpoints</SectionLabel>
                        <h2 className="text-3xl font-black text-ink">Endpoint reference</h2>
                    </div>

                    <div className="space-y-8">

                        {/* Health */}
                        <EndpointCard method="GET" path="/" description="Service health check — no auth required">
                            <CodeBlock language="bash">{`curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "status": "ok",
  "service": "pundit-prediction-ledger",
  "version": "1.0.0"
}`}</CodeBlock>
                        </EndpointCard>

                        {/* /v1/leaderboard */}
                        <EndpointCard method="GET" path="/v1/leaderboard" description="Pundits ranked by weighted accuracy score">
                            <p className="text-sm text-ink-2">
                                Returns pundits ranked by weighted accuracy (accuracy × timeliness). Results are cached for 5 minutes.
                            </p>
                            <ParamTable params={[
                                { name: "limit", type: "integer", required: false, description: "Number of pundits to return (1–100, default 25)", example: "?limit=10" },
                            ]} />
                            <CodeBlock language="bash">{`curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/leaderboard?limit=10" \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "leaderboard": [
    {
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "sport": "NFL",
      "total_predictions": 142,
      "resolved_count": 118,
      "correct_count": 71,
      "accuracy_rate": 0.601,
      "avg_brier_score": 0.22,
      "avg_weighted_score": 0.72
    }
  ],
  "total": 48
}`}</CodeBlock>
                            <ErrorTable codes={[{ code: 401, meaning: "Missing or invalid API key" }, { code: 500, meaning: "Backend / BigQuery error" }]} />
                        </EndpointCard>

                        {/* /v1/pundits/ */}
                        <EndpointCard method="GET" path="/v1/pundits/" description="List all tracked pundits with aggregate stats">
                            <CodeBlock language="bash">{`curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/pundits/ \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "pundits": [
    {
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "sport": "NFL",
      "total_predictions": 142,
      "resolved_count": 118,
      "correct_count": 71,
      "accuracy_rate": 0.601,
      "avg_brier_score": 0.22,
      "avg_weighted_score": 0.72
    }
  ],
  "total": 48
}`}</CodeBlock>
                            <ErrorTable codes={[{ code: 401, meaning: "Missing or invalid API key" }, { code: 500, meaning: "Backend / BigQuery error" }]} />
                        </EndpointCard>

                        {/* /v1/pundits/{pundit_id} */}
                        <EndpointCard method="GET" path="/v1/pundits/{pundit_id}" description="Pundit detail with accuracy breakdown by claim category">
                            <ParamTable params={[
                                { name: "pundit_id", type: "string", required: true, description: "Pundit slug (path param)", example: "mcafee_pat" },
                            ]} />
                            <CodeBlock language="bash">{`curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/pundits/mcafee_pat \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "pundit": {
    "pundit_id": "mcafee_pat",
    "pundit_name": "Pat McAfee",
    "sport": "NFL",
    "total_predictions": 142,
    "resolved_count": 118,
    "correct_count": 71,
    "accuracy_rate": 0.601,
    "avg_brier_score": 0.22,
    "avg_weighted_score": 0.72
  },
  "accuracy_by_category": [
    {
      "claim_category": "draft_pick",
      "total": 38,
      "resolved": 32,
      "correct": 21,
      "accuracy_rate": 0.656,
      "avg_weighted_score": 0.78
    }
  ]
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 404, meaning: "Pundit not found" },
                                { code: 422, meaning: "Validation error" },
                                { code: 500, meaning: "Backend / BigQuery error" },
                            ]} />
                        </EndpointCard>

                        {/* /v1/pundits/{pundit_id}/predictions */}
                        <EndpointCard method="GET" path="/v1/pundits/{pundit_id}/predictions" description="Paginated prediction history for a pundit">
                            <ParamTable params={[
                                { name: "pundit_id", type: "string", required: true, description: "Pundit slug (path param)", example: "mcafee_pat" },
                                { name: "page", type: "integer", required: false, description: "Page number (default 1)", example: "?page=2" },
                                { name: "page_size", type: "integer", required: false, description: "Records per page (1–100, default 20)", example: "?page_size=50" },
                                { name: "status", type: "string", required: false, description: "Filter by resolution status: CORRECT, INCORRECT, PENDING", example: "?status=CORRECT" },
                            ]} />
                            <CodeBlock language="bash">{`curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/pundits/mcafee_pat/predictions?page=1&page_size=20&status=CORRECT" \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "pundit_id": "mcafee_pat",
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "ingestion_timestamp": "2025-04-10T08:30:00Z",
      "source_url": "https://x.com/PatMcAfeeShow/status/...",
      "raw_assertion_text": "Chase Young goes top 5",
      "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
      "claim_category": "draft_pick",
      "season_year": 2025,
      "target_player_id": "chase_young_2025",
      "target_team": null,
      "resolution_status": "CORRECT",
      "resolved_at": "2025-04-25T22:00:00Z",
      "binary_correct": true,
      "brier_score": 0.09,
      "weighted_score": 0.91,
      "outcome_notes": "Selected 3rd overall by the Giants"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 142,
  "pages": 8
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 422, meaning: "Invalid query parameter" },
                                { code: 500, meaning: "Backend / BigQuery error" },
                            ]} />
                        </EndpointCard>

                        {/* /v1/predictions/ */}
                        <EndpointCard method="GET" path="/v1/predictions/" description="Search predictions across all pundits with filters">
                            <ParamTable params={[
                                { name: "category", type: "string", required: false, description: "Filter by claim_category (exact match)", example: "?category=draft_pick" },
                                { name: "status", type: "string", required: false, description: "Filter by resolution status: CORRECT, INCORRECT, PENDING", example: "?status=PENDING" },
                                { name: "player", type: "string", required: false, description: "Substring match on target_player_name (case-insensitive)", example: "?player=mahomes" },
                                { name: "pundit_name", type: "string", required: false, description: "Substring match on pundit_name (case-insensitive)", example: "?pundit_name=schefter" },
                                { name: "limit", type: "integer", required: false, description: "Records per page (1–200, default 50)", example: "?limit=100" },
                                { name: "page", type: "integer", required: false, description: "Page number (default 1)", example: "?page=3" },
                            ]} />
                            <CodeBlock language="bash">{`curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/predictions/?category=draft_pick&status=CORRECT&limit=25" \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "ingestion_timestamp": "2025-04-10T08:30:00Z",
      "source_url": "https://x.com/PatMcAfeeShow/status/...",
      "raw_assertion_text": "Chase Young goes top 5",
      "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
      "claim_category": "draft_pick",
      "season_year": 2025,
      "target_player_id": "chase_young_2025",
      "target_player_name": "Chase Young",
      "target_team": null,
      "resolution_status": "CORRECT",
      "resolved_at": "2025-04-25T22:00:00Z",
      "binary_correct": true,
      "brier_score": 0.09,
      "weighted_score": 0.91,
      "outcome_notes": "Selected 3rd overall by the Giants"
    }
  ],
  "page": 1,
  "limit": 25,
  "total": 412,
  "pages": 17
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 422, meaning: "Invalid query parameter" },
                                { code: 500, meaning: "Backend / BigQuery error" },
                            ]} />
                        </EndpointCard>

                        {/* /v1/predictions/recent */}
                        <EndpointCard method="GET" path="/v1/predictions/recent" description="Latest resolved predictions across all pundits">
                            <ParamTable params={[
                                { name: "limit", type: "integer", required: false, description: "Number of predictions to return (1–100, default 20)", example: "?limit=10" },
                            ]} />
                            <CodeBlock language="bash">{`curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/predictions/recent?limit=10" \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "pundit_id": "schefter_adam",
      "pundit_name": "Adam Schefter",
      "ingestion_timestamp": "2025-04-12T14:00:00Z",
      "extracted_claim": "Eagles will trade their first-round pick",
      "claim_category": "trade",
      "season_year": 2025,
      "target_player_id": null,
      "target_team": "PHI",
      "resolution_status": "INCORRECT",
      "resolved_at": "2025-04-25T23:59:00Z",
      "binary_correct": false,
      "brier_score": 0.81,
      "weighted_score": 0.19,
      "outcome_notes": "Eagles did not trade their first-round pick"
    }
  ],
  "count": 10
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 500, meaning: "Backend / BigQuery error" },
                            ]} />
                        </EndpointCard>

                        {/* /v1/draft/{year} */}
                        <EndpointCard method="GET" path="/v1/draft/{year}" description="Draft prediction summary for a given season year">
                            <ParamTable params={[
                                { name: "year", type: "integer", required: true, description: "NFL draft year (path param)", example: "2025" },
                            ]} />
                            <CodeBlock language="bash">{`curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/draft/2025 \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "year": 2025,
  "total": 89,
  "resolved": 72,
  "pending": 17,
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "ingestion_timestamp": "2025-04-10T08:30:00Z",
      "source_url": "https://x.com/PatMcAfeeShow/status/...",
      "raw_assertion_text": "Chase Young goes top 5",
      "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
      "season_year": 2025,
      "target_player_name": "Chase Young",
      "target_team": null,
      "resolution_status": "CORRECT",
      "resolved_at": "2025-04-25T22:00:00Z",
      "binary_correct": true,
      "weighted_score": 0.91,
      "outcome_notes": "Selected 3rd overall by the Giants"
    }
  ]
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 422, meaning: "Validation error (e.g. non-integer year)" },
                                { code: 500, meaning: "Backend / BigQuery error" },
                            ]} />
                        </EndpointCard>

                        {/* /v1/draft/{year}/results */}
                        <EndpointCard method="GET" path="/v1/draft/{year}/results" description="Draft resolution scoreboard grouped by status + per-pundit accuracy">
                            <ParamTable params={[
                                { name: "year", type: "integer", required: true, description: "NFL draft year (path param)", example: "2025" },
                            ]} />
                            <CodeBlock language="bash">{`curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/draft/2025/results \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "year": 2025,
  "total": 89,
  "by_status": {
    "CORRECT": [ { "pundit_name": "Pat McAfee", "extracted_claim": "...", "weighted_score": 0.91 } ],
    "INCORRECT": [ { "..." : "..." } ],
    "PENDING": [ { "..." : "..." } ]
  },
  "pundit_accuracy": [
    {
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "total_predictions": 12,
      "resolved_count": 10,
      "correct_count": 7,
      "accuracy_rate": 0.7,
      "avg_weighted_score": 0.81
    }
  ]
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 422, meaning: "Validation error" },
                                { code: 500, meaning: "Backend / BigQuery error" },
                            ]} />
                        </EndpointCard>

                        {/* /v1/integrity/verify */}
                        <EndpointCard method="GET" path="/v1/integrity/verify" description="Hash chain integrity check — verify the ledger has not been tampered with">
                            <p className="text-sm text-ink-2">
                                Each prediction is SHA-256 hashed at ingest, including the previous record&apos;s hash.
                                This endpoint walks the full chain and returns <code className="font-mono text-ink-2">verified: true</code> if all hashes match.
                                Any modification to a historical record would break all subsequent hashes.
                            </p>
                            <CodeBlock language="bash">{`curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/integrity/verify \\
  -H "x-api-key: capk_live_your_key"`}</CodeBlock>
                            <CodeBlock language="json">{`{
  "verified": true,
  "records_checked": 4821,
  "broken_at": null
}`}</CodeBlock>
                            <ErrorTable codes={[
                                { code: 401, meaning: "Missing or invalid API key" },
                                { code: 500, meaning: "Integrity check failed to run" },
                            ]} />
                        </EndpointCard>

                    </div>
                </section>

                {/* Error format */}
                <section className="space-y-6">
                    <div className="space-y-3">
                        <SectionLabel>Errors</SectionLabel>
                        <h2 className="text-3xl font-black text-ink">Common error shapes</h2>
                        <p className="text-ink-2 leading-relaxed max-w-2xl">
                            All errors follow FastAPI&apos;s standard response format.
                        </p>
                    </div>
                    <CodeBlock language="json">{`// Standard error
{ "detail": "Human-readable error message" }

// Validation error (422) — includes field-level context
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is less than or equal to 100",
      "type": "value_error.number.not_le"
    }
  ]
}`}</CodeBlock>
                </section>

                {/* CTA */}
                <section className="rounded-2xl border border-accent-editorial/20 bg-accent-editorial/5 p-8 text-center space-y-4">
                    <h2 className="text-2xl font-bold text-ink">Need access?</h2>
                    <p className="text-ink-2 max-w-md mx-auto">
                        API keys are provisioned through your Cap Alpha account. Sign up
                        or sign in to get started.
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                        <Link
                            href="/sign-up"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-accent-editorial text-white text-sm font-semibold hover:bg-accent-editorial-light transition-colors"
                        >
                            Get an API key <ArrowRight className="w-4 h-4" />
                        </Link>
                        <a
                            href="mailto:support@cap-alpha.co"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-editorial-border text-sm font-medium text-ink-2 hover:border-ink-3 hover:text-ink transition-colors"
                        >
                            Contact support
                        </a>
                    </div>
                </section>

            </div>

            {/* Footer */}
            <footer className="border-t border-editorial-border px-6 py-8 mt-auto">
                <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-ink-3">
                    <span className="font-black text-sm text-accent-editorial tracking-tight uppercase">
                        Pundit Ledger
                    </span>
                    <div className="flex items-center gap-6">
                        <Link href="/ledger" className="hover:text-ink-2 transition-colors">Leaderboard</Link>
                        <Link href="/methodology" className="hover:text-ink-2 transition-colors">Methodology</Link>
                        <Link href="/docs" className="text-ink-2">API Docs</Link>
                        <Link href="/legal/terms" className="hover:text-ink-2 transition-colors">Terms</Link>
                        <Link href="/legal/privacy" className="hover:text-ink-2 transition-colors">Privacy</Link>
                    </div>
                    <span>&copy; {new Date().getFullYear()} Pundit Ledger. All predictions verified.</span>
                </div>
            </footer>
        </div>
    );
}
