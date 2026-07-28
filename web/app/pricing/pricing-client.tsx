"use client";

import { useReducer, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UpgradeButton } from "@/components/upgrade-button";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TierKey = "free" | "pro" | "api_starter" | "api_growth" | "agent_standard" | "agent_pro";

export interface Tier {
    key: TierKey;
    name: string;
    monthlyPrice: number;
    period: string | null;
    features: string[];
    cta: { plan: string; label: string } | null;
    highlight: boolean;
}

// ---------------------------------------------------------------------------
// Tiers (authoritative data — used by both card grid + matrix)
// ---------------------------------------------------------------------------

export const TIERS: Tier[] = [
    {
        key: "free",
        name: "Free",
        monthlyPrice: 0,
        period: "/mo",
        features: [
            "Pundit leaderboard",
            "Top-line accuracy scores",
            "Current season predictions",
            "Shareable pundit cards",
        ],
        cta: null,
        highlight: false,
    },
    {
        key: "pro",
        name: "Pro",
        monthlyPrice: 9,
        period: "/mo",
        features: [
            "Everything in Free",
            "Full 6-axis Pundit Credit Score",
            "Complete prediction history",
            "Brier score + calibration",
            "Prediction search & filter",
            "Multi-sport coverage",
            "CSV / JSON export",
        ],
        cta: { plan: "pro", label: "Upgrade to Pro" },
        highlight: true,
    },
    {
        key: "api_starter",
        name: "API Starter",
        monthlyPrice: 49,
        period: "/mo",
        features: [
            "Everything in Pro",
            "REST API access",
            "50,000 requests/month",
            "Per-pundit scores + history",
            "Resolution data",
            "Webhooks",
        ],
        cta: { plan: "api_starter", label: "Get API Starter" },
        highlight: false,
    },
    {
        key: "api_growth",
        name: "API Growth",
        monthlyPrice: 199,
        period: "/mo",
        features: [
            "Everything in API Starter",
            "Unlimited API calls",
            "Custom pundit lists",
            "Team collaboration (10 seats)",
            "White-label embed",
            "Dedicated support + SLA",
        ],
        cta: { plan: "api_growth", label: "Get API Growth" },
        highlight: false,
    },
    {
        key: "agent_standard",
        name: "Agent Standard",
        monthlyPrice: 199,
        period: "/mo",
        features: [
            "MCP server access",
            "Query claims + pundit profiles",
            "Entity relationship graph",
            "Semantic search",
            "Cluster membership",
            "10,000 calls/day",
        ],
        cta: { plan: "agent_standard", label: "Get Agent Standard" },
        highlight: false,
    },
    {
        key: "agent_pro",
        name: "Agent Pro",
        monthlyPrice: 299,
        period: "/mo",
        features: [
            "Everything in Agent Standard",
            "Anomaly detection signals",
            "Lead-time scoring",
            "Coordinated narrative flags",
            "Bulk export",
            "50,000 calls/day",
        ],
        cta: { plan: "agent_pro", label: "Get Agent Pro" },
        highlight: false,
    },
];

// ---------------------------------------------------------------------------
// USDC payment button (Coinbase Commerce)
// ---------------------------------------------------------------------------

function CryptoUpgradeButton({ plan, className }: { plan: string; className?: string }) {
    const [loading, setLoading] = useState(false);

    async function handleCrypto() {
        setLoading(true);
        try {
            const res = await fetch("/api/billing/coinbase", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan }),
            });
            const data = await res.json();
            if (data.url) {
                window.location.href = data.url;
            } else {
                console.error("No Coinbase checkout URL returned", data);
                setLoading(false);
            }
        } catch (err) {
            console.error("Coinbase checkout failed", err);
            setLoading(false);
        }
    }

    return (
        <button
            onClick={handleCrypto}
            disabled={loading}
            className={
                className ??
                "w-full py-2 rounded-lg text-xs font-medium border border-editorial-border bg-editorial-card text-ink-2 hover:border-ink-3 hover:text-ink disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
            }
        >
            {loading ? (
                "Redirecting…"
            ) : (
                <>
                    <span className="text-accent-editorial font-semibold">USDC</span>
                    Pay with crypto
                </>
            )}
        </button>
    );
}

// ---------------------------------------------------------------------------
// LemonSqueezy upgrade button (primary checkout flow — no LLC needed)
// ---------------------------------------------------------------------------

function LemonSqueezyUpgradeButton({
    plan,
    label,
    className,
}: {
    plan: string;
    label: string;
    className?: string;
}) {
    const [loading, setLoading] = useState(false);
    const router = useRouter();

    async function handleLS() {
        setLoading(true);
        try {
            const res = await fetch("/api/billing/lemon-squeezy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan }),
            });
            const data = (await res.json()) as { url?: string; error?: string };
            if (data.url) {
                router.push(data.url);
            } else {
                console.error("[LemonSqueezy] No checkout URL returned", data);
                setLoading(false);
            }
        } catch (err) {
            console.error("[LemonSqueezy] Checkout failed", err);
            setLoading(false);
        }
    }

    return (
        <button
            onClick={handleLS}
            disabled={loading}
            className={
                className ??
                "w-full py-2.5 rounded-lg bg-accent-editorial hover:bg-accent-editorial-light disabled:opacity-60 text-sm font-semibold text-white transition-colors"
            }
        >
            {loading ? "Redirecting…" : label}
        </button>
    );
}

// ---------------------------------------------------------------------------
// Feature matrix definition
// ---------------------------------------------------------------------------

interface MatrixRow {
    label: string;
    cells: Record<TierKey, string>;
}

export const MATRIX_ROWS: MatrixRow[] = [
    {
        label: "Pundit leaderboard (public)",
        cells: { free: "✓", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "Top-line accuracy scores",
        cells: { free: "✓", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "Full prediction history",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "6-axis Credit Score",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "Brier score + calibration",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "Prediction search & filter",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "CSV / JSON export",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓", agent_standard: "—", agent_pro: "Bulk" },
    },
    {
        label: "API access",
        cells: { free: "—", pro: "—", api_starter: "50k/mo", api_growth: "Unlimited", agent_standard: "—", agent_pro: "—" },
    },
    {
        label: "Webhooks",
        cells: { free: "—", pro: "—", api_starter: "✓", api_growth: "✓", agent_standard: "—", agent_pro: "—" },
    },
    {
        label: "MCP server (graph tools)",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "—", agent_standard: "10k/day", agent_pro: "50k/day" },
    },
    {
        label: "Semantic search + clusters",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "—", agent_standard: "✓", agent_pro: "✓" },
    },
    {
        label: "Anomaly detection signals",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "—", agent_standard: "—", agent_pro: "✓" },
    },
    {
        label: "Lead-time scoring",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "—", agent_standard: "—", agent_pro: "✓" },
    },
    {
        label: "Coordinated narrative flags",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "—", agent_standard: "—", agent_pro: "✓" },
    },
    {
        label: "Custom pundit lists",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "✓", agent_standard: "—", agent_pro: "—" },
    },
    {
        label: "Team collaboration",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "10 seats", agent_standard: "—", agent_pro: "—" },
    },
    {
        label: "White-label embed",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "✓", agent_standard: "—", agent_pro: "—" },
    },
    {
        label: "Dedicated support",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "✓", agent_standard: "—", agent_pro: "✓" },
    },
];

// ---------------------------------------------------------------------------
// Quiz types and reducer
// ---------------------------------------------------------------------------

type UserType = "fan" | "fantasy" | "bettor" | "developer" | "organization" | "ai_builder";
type CareAbout = "leaderboard" | "tracking" | "api" | "team" | "mcp";
type ApiVolume = "low" | "mid" | "high";

interface QuizState {
    step: 1 | 2 | 3 | "done";
    userType: UserType | null;
    careAbout: CareAbout | null;
    apiVolume: ApiVolume | null;
    recommendation: TierKey | null;
}

type QuizAction =
    | { type: "SET_USER_TYPE"; payload: UserType }
    | { type: "SET_CARE_ABOUT"; payload: CareAbout }
    | { type: "SET_API_VOLUME"; payload: ApiVolume }
    | { type: "RESET" };

function computeRecommendation(
    userType: UserType,
    careAbout: CareAbout,
    apiVolume: ApiVolume | null,
): TierKey {
    if (careAbout === "mcp" || userType === "ai_builder") {
        if (apiVolume === "high") return "agent_pro";
        return "agent_standard";
    }
    if (careAbout === "team" || userType === "organization") return "api_growth";
    if (careAbout === "api") {
        if (apiVolume === "high") return "api_growth";
        return "api_starter";
    }
    if (careAbout === "leaderboard" && (userType === "fan" || userType === "fantasy")) return "free";
    if (careAbout === "tracking" || userType === "bettor") return "pro";
    return "pro";
}

function quizReducer(state: QuizState, action: QuizAction): QuizState {
    switch (action.type) {
        case "SET_USER_TYPE":
            return { ...state, userType: action.payload, step: 2 };
        case "SET_CARE_ABOUT": {
            const careAbout = action.payload;
            if (careAbout === "api" || careAbout === "mcp") {
                return { ...state, careAbout, step: 3 };
            }
            const recommendation = computeRecommendation(state.userType!, careAbout, null);
            return { ...state, careAbout, step: "done", recommendation };
        }
        case "SET_API_VOLUME": {
            const recommendation = computeRecommendation(
                state.userType!,
                state.careAbout!,
                action.payload,
            );
            return { ...state, apiVolume: action.payload, step: "done", recommendation };
        }
        case "RESET":
            return initialQuizState;
        default:
            return state;
    }
}

const initialQuizState: QuizState = {
    step: 1,
    userType: null,
    careAbout: null,
    apiVolume: null,
    recommendation: null,
};

// ---------------------------------------------------------------------------
// Annual toggle
// ---------------------------------------------------------------------------

const ANNUAL_DISCOUNT = 0.8;
const LS_KEY = "pricing_billing_period";

function formatPrice(monthly: number, annual: boolean): string {
    if (monthly === 0) return "$0";
    const price = annual ? Math.round(monthly * ANNUAL_DISCOUNT) : monthly;
    return `$${price}`;
}

// ---------------------------------------------------------------------------
// QuizPanel component
// ---------------------------------------------------------------------------

interface QuizPanelProps {
    recommendation: TierKey | null;
    onRecommend: (tier: TierKey) => void;
}

function QuizPanel({ onRecommend }: QuizPanelProps) {
    const [state, dispatch] = useReducer(quizReducer, initialQuizState);

    useEffect(() => {
        if (state.recommendation) {
            onRecommend(state.recommendation);
        }
    }, [state.recommendation, onRecommend]);

    const btnBase =
        "px-4 py-2.5 rounded-lg border text-sm font-medium transition-all cursor-pointer";
    const btnUnselected = "border-editorial-border bg-editorial-card text-ink-2 hover:border-ink-3 hover:text-ink";
    const btnSelected = "border-accent-editorial bg-accent-editorial/10 text-accent-editorial";

    if (state.step === "done") {
        return (
            <div className="rounded-2xl border border-editorial-border bg-editorial-card p-6 flex items-center justify-between gap-4 flex-wrap">
                <p className="text-sm text-ink-2">
                    Based on your answers, we recommend{" "}
                    <span className="text-accent-editorial font-semibold">
                        {TIERS.find((t) => t.key === state.recommendation)?.name}
                    </span>
                    .
                </p>
                <button
                    onClick={() => dispatch({ type: "RESET" })}
                    className="text-xs text-ink-3 hover:text-ink-2 underline transition-colors"
                >
                    Start over
                </button>
            </div>
        );
    }

    return (
        <div className="rounded-2xl border border-editorial-border bg-editorial-card p-6 space-y-5">
            <p className="text-xs font-mono uppercase tracking-widest text-ink-3">
                Help me choose
            </p>

            {/* Step 1 */}
            <div>
                <p className="text-sm text-ink-2 mb-3">
                    <span className="text-ink-3 mr-2">1 of {state.step === 3 ? "3" : "2+"}.</span>
                    I am a…
                </p>
                <div className="flex flex-wrap gap-2">
                    {(
                        [
                            ["fan", "Sports fan"],
                            ["fantasy", "Fantasy player"],
                            ["bettor", "Bettor"],
                            ["developer", "Developer / Builder"],
                            ["ai_builder", "AI / Agent Builder"],
                            ["organization", "Team / Organization"],
                        ] as [UserType, string][]
                    ).map(([value, label]) => (
                        <button
                            key={value}
                            onClick={() => dispatch({ type: "SET_USER_TYPE", payload: value })}
                            className={`${btnBase} ${state.userType === value ? btnSelected : btnUnselected}`}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Step 2 */}
            {(state.step === 2 || state.step === 3) && (
                <div>
                    <p className="text-sm text-ink-2 mb-3">
                        <span className="text-ink-3 mr-2">2.</span>
                        I care most about…
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {(
                            [
                                ["leaderboard", "Browsing the leaderboard"],
                                ["tracking", "Tracking specific pundits"],
                                ["api", "API access"],
                                ["mcp", "MCP / AI agent tools"],
                                ["team", "Team workflows"],
                            ] as [CareAbout, string][]
                        ).map(([value, label]) => (
                            <button
                                key={value}
                                onClick={() => dispatch({ type: "SET_CARE_ABOUT", payload: value })}
                                className={`${btnBase} ${state.careAbout === value ? btnSelected : btnUnselected}`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Step 3 — conditional on API */}
            {state.step === 3 && (
                <div>
                    <p className="text-sm text-ink-2 mb-3">
                        <span className="text-ink-3 mr-2">3.</span>
                        How many API calls per month?
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {(
                            [
                                ["low", "< 1,000"],
                                ["mid", "1,000–50,000"],
                                ["high", "50,000+"],
                            ] as [ApiVolume, string][]
                        ).map(([value, label]) => (
                            <button
                                key={value}
                                onClick={() => dispatch({ type: "SET_API_VOLUME", payload: value })}
                                className={`${btnBase} ${state.apiVolume === value ? btnSelected : btnUnselected}`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// FeatureMatrix component
// ---------------------------------------------------------------------------

interface FeatureMatrixProps {
    annual: boolean;
    recommendedTier: TierKey | null;
}

function FeatureMatrix({ annual, recommendedTier }: FeatureMatrixProps) {
    const tierOrder: TierKey[] = ["free", "pro", "api_starter", "api_growth", "agent_standard", "agent_pro"];

    return (
        <div className="overflow-x-auto rounded-2xl border border-editorial-border">
            <table className="w-full min-w-[640px] text-sm border-collapse">
                {/* Sticky header */}
                <thead>
                    <tr className="border-b border-editorial-border">
                        <th className="sticky left-0 z-10 bg-editorial-bg text-left px-5 py-4 font-medium text-ink-2 w-56">
                            Feature
                        </th>
                        {TIERS.map((tier) => {
                            const isRecommended = recommendedTier === tier.key;
                            const isPro = tier.key === "pro";
                            return (
                                <th
                                    key={tier.key}
                                    className={`px-5 py-4 text-center font-semibold ${
                                        isPro
                                            ? "text-accent-editorial"
                                            : "text-ink-2"
                                    } ${isRecommended ? "relative" : ""}`}
                                >
                                    <div className="flex flex-col items-center gap-1">
                                        <span>{tier.name}</span>
                                        <span className="text-xs font-mono font-normal text-ink-3">
                                            {formatPrice(tier.monthlyPrice, annual)}
                                            {tier.monthlyPrice > 0 && (
                                                <span className="text-ink-3">/mo</span>
                                            )}
                                        </span>
                                        {isRecommended && (
                                            <span className="text-[10px] font-mono uppercase tracking-wider bg-accent-editorial/20 text-accent-editorial border border-accent-editorial/30 rounded-full px-2 py-0.5 animate-pulse">
                                                Recommended for you
                                            </span>
                                        )}
                                    </div>
                                </th>
                            );
                        })}
                    </tr>
                </thead>
                <tbody>
                    {MATRIX_ROWS.map((row, i) => (
                        <tr
                            key={row.label}
                            className={`border-b border-editorial-border ${
                                i % 2 === 0 ? "bg-editorial-bg" : "bg-editorial-card"
                            }`}
                        >
                            <td className="sticky left-0 z-10 px-5 py-3.5 text-ink-2 font-medium bg-inherit">
                                {row.label}
                            </td>
                            {tierOrder.map((key) => {
                                const val = row.cells[key];
                                const isPro = key === "pro";
                                const isRecommended = recommendedTier === key;
                                return (
                                    <td
                                        key={key}
                                        className={`px-5 py-3.5 text-center ${
                                            isPro
                                                ? "border-x border-accent-editorial/20"
                                                : ""
                                        } ${
                                            isRecommended && !isPro
                                                ? "border-x border-accent-editorial/30"
                                                : ""
                                        }`}
                                    >
                                        {val === "✓" ? (
                                            <span className="text-correct font-bold">✓</span>
                                        ) : val === "—" ? (
                                            <span className="text-ink-3">—</span>
                                        ) : (
                                            <span className="text-ink-2 text-xs font-mono">{val}</span>
                                        )}
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main PricingClient component
// ---------------------------------------------------------------------------

export function PricingClient() {
    const [annual, setAnnual] = useLocalStorage(LS_KEY, false);
    const [recommendedTier, setRecommendedTier] = useReducerState<TierKey | null>(null);
    const matrixRef = useRef<HTMLDivElement>(null);

    function handleRecommend(tier: TierKey) {
        setRecommendedTier(tier);
        // Small delay so the badge renders before we scroll
        setTimeout(() => {
            matrixRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 150);
    }

    return (
        <div className="space-y-10">
            {/* ── Annual / Monthly toggle ── */}
            <div className="flex items-center justify-center gap-3">
                <span
                    className={`text-sm ${!annual ? "text-ink font-medium" : "text-ink-3"}`}
                >
                    Monthly
                </span>
                <button
                    role="switch"
                    aria-checked={annual}
                    onClick={() => setAnnual(!annual)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        annual ? "bg-accent-editorial" : "bg-editorial-border"
                    }`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-editorial-card shadow transition-transform ${
                            annual ? "translate-x-6" : "translate-x-1"
                        }`}
                    />
                </button>
                <span
                    className={`text-sm ${annual ? "text-ink font-medium" : "text-ink-3"}`}
                >
                    Annual{" "}
                    <span className="text-accent-editorial text-xs font-mono">(save 20%)</span>
                </span>
            </div>

            {/* ── Card grid (existing, preserved) ── */}
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
                {TIERS.map((tier) => {
                    const isRecommended = recommendedTier === tier.key;
                    return (
                        <div
                            key={tier.key}
                            data-tier={tier.key}
                            className={`rounded-2xl p-6 space-y-4 flex flex-col transition-all ${
                                isRecommended
                                    ? "ring-2 ring-accent-editorial ring-offset-2 ring-offset-editorial-bg"
                                    : ""
                            } ${
                                tier.highlight
                                    ? "border border-accent-editorial/40 bg-accent-editorial/5"
                                    : "border border-editorial-border bg-editorial-card"
                            }`}
                        >
                            <div>
                                <div
                                    className={`text-xs font-mono uppercase tracking-widest mb-1 ${
                                        tier.highlight ? "text-accent-editorial" : "text-ink-3"
                                    }`}
                                >
                                    {tier.name}
                                    {isRecommended && (
                                        <span className="ml-2 text-[10px] bg-accent-editorial/20 text-accent-editorial border border-accent-editorial/30 rounded-full px-1.5 py-0.5 animate-pulse">
                                            Recommended
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-baseline gap-0.5">
                                    <span className="text-2xl font-black text-ink">
                                        {formatPrice(tier.monthlyPrice, annual)}
                                    </span>
                                    {tier.monthlyPrice > 0 && (
                                        <span className="text-ink-3 text-sm">/mo</span>
                                    )}
                                </div>
                                {annual && tier.monthlyPrice > 0 && (
                                    <p className="text-xs text-ink-3 mt-0.5">
                                        billed ${Math.round(tier.monthlyPrice * ANNUAL_DISCOUNT * 12)}/yr
                                    </p>
                                )}
                            </div>

                            <ul className="space-y-2 text-sm text-ink-2 flex-1">
                                {tier.features.map((f) => (
                                    <li key={f} className="flex items-start gap-2">
                                        <span className="text-correct mt-0.5">✓</span>
                                        {f}
                                    </li>
                                ))}
                            </ul>

                            {tier.cta ? (
                                <div className="space-y-2">
                                    {/* Primary CTA: LemonSqueezy (MoR — no LLC needed) */}
                                    <LemonSqueezyUpgradeButton
                                        plan={tier.cta.plan}
                                        label={tier.cta.label}
                                        className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors ${
                                            tier.highlight
                                                ? "bg-accent-editorial hover:bg-accent-editorial-light text-white"
                                                : "bg-editorial-card hover:bg-editorial-border text-ink border border-editorial-border"
                                        }`}
                                    />
                                    {/* USDC alternative (Coinbase Commerce) */}
                                    {(tier.key === "pro" || tier.key === "api_starter") && (
                                        <CryptoUpgradeButton plan={tier.cta.plan} />
                                    )}
                                    {/* Stripe checkout kept in codebase for future use.
                                        Swap LemonSqueezyUpgradeButton → UpgradeButton above
                                        to re-enable Stripe checkout once LLC is in place. */}
                                </div>
                            ) : (
                                <Link
                                    href="/ledger"
                                    className="block text-center py-2.5 rounded-lg border border-editorial-border text-sm font-medium text-ink-2 hover:border-ink-3 hover:text-ink transition-colors"
                                >
                                    View Leaderboard
                                </Link>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* ── Help me choose quiz ── */}
            <QuizPanel recommendation={recommendedTier} onRecommend={handleRecommend} />

            {/* ── Feature comparison matrix ── */}
            <div ref={matrixRef}>
                <h2 className="text-lg font-semibold text-ink mb-4">Compare all features</h2>
                <FeatureMatrix annual={annual} recommendedTier={recommendedTier} />
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Minimal hooks
// ---------------------------------------------------------------------------

function useLocalStorage(key: string, defaultValue: boolean): [boolean, (v: boolean) => void] {
    const [value, setValue] = useReducer(
        (_: boolean, next: boolean) => {
            try {
                localStorage.setItem(key, JSON.stringify(next));
            } catch {
                // ignore SSR / private mode
            }
            return next;
        },
        defaultValue,
        (init) => {
            if (typeof window === "undefined") return init;
            try {
                const stored = localStorage.getItem(key);
                return stored !== null ? (JSON.parse(stored) as boolean) : init;
            } catch {
                return init;
            }
        },
    );
    return [value, setValue];
}

function useReducerState<T>(initial: T): [T, (v: T) => void] {
    const [state, dispatch] = useReducer((_: T, next: T) => next, initial);
    return [state, dispatch];
}
