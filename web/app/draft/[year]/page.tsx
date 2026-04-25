"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Prediction {
  prediction_hash: string;
  pundit_id: string;
  pundit_name: string;
  extracted_claim: string;
  target_player_name: string | null;
  target_team: string | null;
  source_url: string | null;
  status: string;
  binary_correct: boolean | null;
  outcome_notes: string | null;
}

interface DraftData {
  draft_year: number;
  total_predictions: number;
  resolved: number;
  pending: number;
  predictions: Prediction[];
}

interface PunditScore {
  name: string;
  correct: number;
  incorrect: number;
  pending: number;
  accuracy: number | null;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "CORRECT")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/50 px-2.5 py-0.5 text-xs font-medium text-emerald-400 ring-1 ring-emerald-500/30">
        ✅ Correct
      </span>
    );
  if (status === "INCORRECT")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-900/50 px-2.5 py-0.5 text-xs font-medium text-red-400 ring-1 ring-red-500/30">
        ❌ Wrong
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs font-medium text-zinc-400 ring-1 ring-zinc-700">
      ⏳ Pending
    </span>
  );
}

function buildLeaderboard(predictions: Prediction[]): PunditScore[] {
  const map = new Map<string, PunditScore>();
  for (const p of predictions) {
    const name = p.pundit_name || "Unknown";
    if (!map.has(name)) {
      map.set(name, { name, correct: 0, incorrect: 0, pending: 0, accuracy: null });
    }
    const s = map.get(name)!;
    if (p.status === "CORRECT") s.correct++;
    else if (p.status === "INCORRECT") s.incorrect++;
    else s.pending++;
  }
  const scores = Array.from(map.values());
  for (const s of scores) {
    const resolved = s.correct + s.incorrect;
    s.accuracy = resolved > 0 ? Math.round((s.correct / resolved) * 100) : null;
  }
  scores.sort((a, b) => {
    if (a.accuracy !== null && b.accuracy !== null) return b.accuracy - a.accuracy;
    if (a.accuracy !== null) return -1;
    if (b.accuracy !== null) return 1;
    return b.correct + b.incorrect + b.pending - (a.correct + a.incorrect + a.pending);
  });
  return scores;
}

export default function DraftScoreboard() {
  const params = useParams();
  const year = params.year as string;
  const [data, setData] = useState<DraftData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/v1/draft/${year}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch");
    }
  }, [year]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const leaderboard = data ? buildLeaderboard(data.predictions) : [];
  const resolved = data ? data.predictions.filter((p) => p.status !== "PENDING") : [];
  const pending = data ? data.predictions.filter((p) => p.status === "PENDING") : [];

  return (
    <div className="min-h-screen bg-black text-zinc-100">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <Link
                href="/"
                className="text-xs font-mono text-zinc-500 hover:text-zinc-300 uppercase tracking-wider"
              >
                ← Pundit Ledger
              </Link>
              <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
                {year} NFL Draft
                <span className="ml-3 text-emerald-500">Scoreboard</span>
              </h1>
              <p className="mt-1 text-sm text-zinc-500">
                Tracking which pundits actually know what they&apos;re talking about
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                Auto-refreshes every 60s
              </span>
              <span>
                Updated {lastRefresh.toLocaleTimeString()}
              </span>
              <button
                onClick={fetchData}
                className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 transition-colors"
              >
                Refresh
              </button>
            </div>
          </div>

          {/* Stats bar */}
          {data && (
            <div className="mt-4 flex gap-6 text-sm">
              <div>
                <span className="font-mono text-xl font-bold text-zinc-100">
                  {data.total_predictions}
                </span>
                <span className="ml-1.5 text-zinc-500">predictions</span>
              </div>
              <div>
                <span className="font-mono text-xl font-bold text-emerald-400">
                  {resolved.filter((p) => p.status === "CORRECT").length}
                </span>
                <span className="ml-1.5 text-zinc-500">correct</span>
              </div>
              <div>
                <span className="font-mono text-xl font-bold text-red-400">
                  {resolved.filter((p) => p.status === "INCORRECT").length}
                </span>
                <span className="ml-1.5 text-zinc-500">wrong</span>
              </div>
              <div>
                <span className="font-mono text-xl font-bold text-zinc-400">
                  {pending.length}
                </span>
                <span className="ml-1.5 text-zinc-500">pending</span>
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {error && !data && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-12 text-center">
            <p className="text-lg text-zinc-400">
              Scoreboard loading...
            </p>
            <p className="mt-2 text-sm text-zinc-600">
              The prediction engine is warming up. Retrying automatically.
            </p>
          </div>
        )}

        {data && data.predictions.length === 0 && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-12 text-center">
            <p className="text-lg text-zinc-400">
              No draft predictions captured yet
            </p>
            <p className="mt-2 text-sm text-zinc-600">
              Check back soon — we&apos;re ingesting pundit predictions now.
            </p>
          </div>
        )}

        {data && data.predictions.length > 0 && (
          <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
            {/* Predictions Table */}
            <div>
              {/* Resolved predictions */}
              {resolved.length > 0 && (
                <div className="mb-8">
                  <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-emerald-500">
                    Resolved
                  </h2>
                  <div className="overflow-x-auto rounded-lg border border-zinc-800">
                    <table className="w-full text-sm">
                      <thead className="border-b border-zinc-800 bg-zinc-900/50">
                        <tr>
                          <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-zinc-500">
                            Pundit
                          </th>
                          <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-zinc-500">
                            Prediction
                          </th>
                          <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-zinc-500">
                            Result
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800/50">
                        {resolved.map((p) => (
                          <tr
                            key={p.prediction_hash}
                            className="hover:bg-zinc-900/30 transition-colors"
                          >
                            <td className="whitespace-nowrap px-4 py-3 font-medium">
                              {p.pundit_name}
                            </td>
                            <td className="px-4 py-3 text-zinc-300">
                              <div>{p.extracted_claim}</div>
                              {p.outcome_notes && (
                                <div className="mt-1 text-xs text-zinc-500">
                                  {p.outcome_notes}
                                </div>
                              )}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3">
                              <StatusBadge status={p.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Pending predictions */}
              {pending.length > 0 && (
                <div>
                  <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-zinc-500">
                    Awaiting Results ({pending.length})
                  </h2>
                  <div className="overflow-x-auto rounded-lg border border-zinc-800">
                    <table className="w-full text-sm">
                      <thead className="border-b border-zinc-800 bg-zinc-900/50">
                        <tr>
                          <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-zinc-500">
                            Pundit
                          </th>
                          <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-zinc-500">
                            Prediction
                          </th>
                          <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-zinc-500">
                            Player
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800/50">
                        {pending.map((p) => (
                          <tr
                            key={p.prediction_hash}
                            className="hover:bg-zinc-900/30 transition-colors"
                          >
                            <td className="whitespace-nowrap px-4 py-3 font-medium">
                              {p.pundit_name}
                            </td>
                            <td className="px-4 py-3 text-zinc-300">
                              {p.extracted_claim}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-zinc-400">
                              {p.target_player_name || "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* Leaderboard Sidebar */}
            <aside>
              <div className="sticky top-8 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
                <h2 className="mb-4 font-mono text-xs uppercase tracking-wider text-emerald-500">
                  Pundit Leaderboard
                </h2>
                <div className="space-y-3">
                  {leaderboard.map((s, i) => (
                    <div
                      key={s.name}
                      className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2"
                    >
                      <div className="flex items-center gap-3">
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-800 font-mono text-xs font-bold text-zinc-400">
                          {i + 1}
                        </span>
                        <span className="text-sm font-medium">{s.name}</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        {s.correct > 0 && (
                          <span className="text-emerald-400">{s.correct}✅</span>
                        )}
                        {s.incorrect > 0 && (
                          <span className="text-red-400">{s.incorrect}❌</span>
                        )}
                        {s.pending > 0 && (
                          <span className="text-zinc-500">{s.pending}⏳</span>
                        )}
                        {s.accuracy !== null && (
                          <span
                            className={`ml-1 font-mono font-bold ${
                              s.accuracy >= 60
                                ? "text-emerald-400"
                                : s.accuracy >= 40
                                  ? "text-yellow-400"
                                  : "text-red-400"
                            }`}
                          >
                            {s.accuracy}%
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {leaderboard.length === 0 && (
                  <p className="text-center text-sm text-zinc-600">
                    No pundits scored yet
                  </p>
                )}
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
