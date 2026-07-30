import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { Metadata } from "next";
import { AlertTriangle, Database, ExternalLink } from "lucide-react";
import { BigQuery } from "@google-cloud/bigquery";
import { SectionHeading } from "@/components/ui/heading";

export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
    title: "Extraction Runs | Admin | Pundit Ledger",
    description: "Per-run extraction metrics admin view.",
};

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";

interface RunRow {
    run_id: string;
    run_started_at: string;
    run_completed_at: string | null;
    provider: string | null;
    utterances_written: number;
    claims_promoted: number;
    errors: number;
    status: string;
}

async function getRunData(): Promise<{
    rows: RunRow[];
    tableExists: boolean;
    error: string | null;
}> {
    const bq = new BigQuery({
        projectId: PROJECT_ID,
        credentials:
            process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY
                ? {
                      client_email: process.env.GCP_CLIENT_EMAIL,
                      private_key: process.env.GCP_PRIVATE_KEY.replace(
                          /\\n/g,
                          "\n"
                      ),
                  }
                : undefined,
    });

    try {
        const [rows] = await bq.query({
            query: `
                SELECT
                    run_id,
                    run_started_at,
                    run_completed_at,
                    provider,
                    utterances_written,
                    claims_promoted,
                    errors,
                    status
                FROM \`${PROJECT_ID}.silver_v2_claims.extraction_run\`
                ORDER BY run_started_at DESC
                LIMIT 100
            `,
            jobTimeoutMs: 10000,
        });

        return {
            rows: (rows as Array<Record<string, unknown>>).map((r) => ({
                run_id: String(r.run_id ?? ""),
                run_started_at: String(r.run_started_at ?? ""),
                run_completed_at: r.run_completed_at
                    ? String(r.run_completed_at)
                    : null,
                provider: r.provider ? String(r.provider) : null,
                utterances_written: Number(r.utterances_written ?? 0),
                claims_promoted: Number(r.claims_promoted ?? 0),
                errors: Number(r.errors ?? 0),
                status: String(r.status ?? ""),
            })),
            tableExists: true,
            error: null,
        };
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        const notFound =
            msg.includes("Not found") || msg.includes("does not exist");
        return {
            rows: [],
            tableExists: !notFound,
            error: notFound ? null : msg,
        };
    }
}

export default async function AdminQualityRunsPage() {
    const { userId } = auth();

    if (!userId) {
        redirect("/sign-in");
    }

    const { rows, tableExists, error } = await getRunData();

    return (
        <div className="bg-editorial-bg text-ink min-h-[100dvh]">
            <section className="border-b border-editorial-border px-6 py-10">
                <div className="max-w-6xl mx-auto space-y-2">
                    <div className="flex items-center gap-2 text-xs text-ink-3 font-mono">
                        <a href="/quality" className="hover:text-ink">
                            Quality Dashboard
                        </a>
                        <span>/</span>
                        <span className="text-ink-2">Extraction Runs</span>
                    </div>
                    <SectionHeading size="lg">
                        Extraction Run Log
                    </SectionHeading>
                    <p className="text-sm text-ink-2">
                        Per-run metrics from{" "}
                        <code className="font-mono text-xs bg-editorial-card px-1.5 py-0.5 rounded">
                            silver_v2_claims.extraction_run
                        </code>
                    </p>
                </div>
            </section>

            <div className="max-w-6xl mx-auto px-6 py-8">
                {!tableExists && (
                    <div className="rounded-xl border border-pending/30 bg-pending/10 p-6 flex items-start gap-4">
                        <AlertTriangle className="w-5 h-5 text-pending shrink-0 mt-0.5" />
                        <div className="space-y-2">
                            <p className="text-sm font-semibold text-pending">
                                extraction_run table not found
                            </p>
                            <p className="text-xs text-ink-2 leading-relaxed">
                                The{" "}
                                <code className="font-mono">
                                    silver_v2_claims.extraction_run
                                </code>{" "}
                                table doesn&apos;t exist yet. This view depends
                                on{" "}
                                <a
                                    href="https://github.com/andrewjsmith00/nfl-dead-money/issues/4"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-accent-editorial hover:text-accent-editorial-light inline-flex items-center gap-1"
                                >
                                    Issue #4
                                    <ExternalLink className="w-3 h-3" />
                                </a>{" "}
                                (per-run metrics table). Once that table exists,
                                this page will populate automatically.
                            </p>
                        </div>
                    </div>
                )}

                {tableExists && error && (
                    <div className="rounded-xl border border-incorrect/30 bg-incorrect/10 p-6 flex items-start gap-4">
                        <AlertTriangle className="w-5 h-5 text-incorrect shrink-0 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-incorrect">
                                Query failed
                            </p>
                            <p className="text-xs text-ink-2 mt-1 font-mono">
                                {error}
                            </p>
                        </div>
                    </div>
                )}

                {tableExists && !error && rows.length === 0 && (
                    <div className="rounded-xl border border-editorial-border bg-editorial-card p-10 text-center space-y-3">
                        <Database className="w-8 h-8 text-ink-3 mx-auto" />
                        <p className="text-ink-2 font-medium">
                            No run records yet
                        </p>
                        <p className="text-sm text-ink-3">
                            Extraction runs will appear here as they complete.
                        </p>
                    </div>
                )}

                {rows.length > 0 && (
                    <div className="rounded-xl border border-editorial-border bg-editorial-card overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs text-left">
                                <thead>
                                    <tr className="border-b border-editorial-border bg-editorial-bg text-ink-3 font-mono uppercase tracking-wider">
                                        <th className="px-4 py-3">Run ID</th>
                                        <th className="px-4 py-3">Started</th>
                                        <th className="px-4 py-3">Provider</th>
                                        <th className="px-4 py-3 text-right">
                                            Utterances
                                        </th>
                                        <th className="px-4 py-3 text-right">
                                            Claims
                                        </th>
                                        <th className="px-4 py-3 text-right">
                                            Errors
                                        </th>
                                        <th className="px-4 py-3">Status</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-editorial-border">
                                    {rows.map((row) => (
                                        <tr
                                            key={row.run_id}
                                            className="text-ink-2 hover:bg-editorial-bg"
                                        >
                                            <td className="px-4 py-2.5 font-mono text-ink-3 max-w-[120px] truncate">
                                                {row.run_id.slice(0, 8)}…
                                            </td>
                                            <td className="px-4 py-2.5 whitespace-nowrap">
                                                {new Date(
                                                    row.run_started_at
                                                ).toLocaleString("en-US", {
                                                    month: "short",
                                                    day: "numeric",
                                                    hour: "2-digit",
                                                    minute: "2-digit",
                                                })}
                                            </td>
                                            <td className="px-4 py-2.5 font-mono text-ink-2">
                                                {row.provider ?? "—"}
                                            </td>
                                            <td className="px-4 py-2.5 text-right tabular-nums">
                                                <span
                                                    className={
                                                        row.utterances_written ===
                                                        0
                                                            ? "text-incorrect font-bold"
                                                            : ""
                                                    }
                                                >
                                                    {row.utterances_written.toLocaleString()}
                                                </span>
                                            </td>
                                            <td className="px-4 py-2.5 text-right tabular-nums">
                                                {row.claims_promoted.toLocaleString()}
                                            </td>
                                            <td className="px-4 py-2.5 text-right tabular-nums">
                                                <span
                                                    className={
                                                        row.errors > 0
                                                            ? "text-pending"
                                                            : "text-ink-3"
                                                    }
                                                >
                                                    {row.errors}
                                                </span>
                                            </td>
                                            <td className="px-4 py-2.5">
                                                <span
                                                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono ${
                                                        row.status ===
                                                        "SUCCESS"
                                                            ? "bg-correct/10 text-correct"
                                                            : row.status ===
                                                              "FAILED"
                                                            ? "bg-incorrect/10 text-incorrect"
                                                            : "bg-editorial-border text-ink-2"
                                                    }`}
                                                >
                                                    {row.status}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="px-4 py-3 border-t border-editorial-border text-xs text-ink-3">
                            Showing last {rows.length} runs. Page cached 1
                            hour.
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
