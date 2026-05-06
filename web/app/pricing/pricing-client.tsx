"use client";

import { useReducer, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UpgradeButton } from "@/components/upgrade-button";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TierKey = "free" | "pro" | "api_starter" | "api_growth";

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
                "w-full py-2 rounded-lg text-xs font-medium border border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
            }
        >
            {loading ? (
                "Redirecting…"
            ) : (
                <>
                    <span className="text-blue-400 font-semibold">USDC</span>
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
                "w-full py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-60 text-sm font-semibold text-black transition-colors"
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
        cells: { free: "✓", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "Top-line accuracy scores",
        cells: { free: "✓", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "Full prediction history",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "6-axis Credit Score",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "Brier score + calibration",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "Prediction search & filter",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "CSV / JSON export",
        cells: { free: "—", pro: "✓", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "API access",
        cells: { free: "—", pro: "—", api_starter: "50k/mo", api_growth: "Unlimited" },
    },
    {
        label: "Webhooks",
        cells: { free: "—", pro: "—", api_starter: "✓", api_growth: "✓" },
    },
    {
        label: "Custom pundit lists",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "✓" },
    },
    {
        label: "Team collaboration",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "10 seats" },
    },
    {
        label: "White-label embed",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "✓" },
    },
    {
        label: "Dedicated support",
        cells: { free: "—", pro: "—", api_starter: "—", api_growth: "✓" },
    },
];

// ---------------------------------------------------------------------------
// Quiz types and reducer
// ---------------------------------------------------------------------------

type UserType = "fan" | "fantasy" | "bettor" | "developer" | "organization";
type CareAbout = "leaderboard" | "tracking" | "api" | "team";
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
            if (careAbout === "api") {
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
    const btnUnselected = "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500 hover:text-white";
    const btnSelected = "border-emerald-500 bg-emerald-500/10 text-emerald-400";

    if (state.step === "done") {
        return (
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 flex items-center justify-between gap-4 flex-wrap">
                <p className="text-sm text-zinc-400">
                    Based on your answers, we recommend{" "}
                    <span className="text-emerald-400 font-semibold">
                        {TIERS.find((t) => t.key === state.recommendation)?.name}
                    </span>
                    .
                </p>
                <button
                    onClick={() => dispatch({ type: "RESET" })}
                    className="text-xs text-zinc-400 hover:text-zinc-300 underline transition-colors"
                >
                    Start over
                </button>
            </div>
        );
    }

    return (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-5">
            <p className="text-xs font-mono uppercase tracking-widest text-zinc-400">
                Help me choose
            </p>

            {/* Step 1 */}
            <div>
                <p className="text-sm text-zinc-300 mb-3">
                    <span className="text-zinc-400 mr-2">1 of {state.step === 3 ? "3" : "2+"}.</span>
                    I am a…
                </p>
                <div className="flex flex-wrap gap-2">
                    {(
                        [
                            ["fan", "Sports fan"],
                            ["fantasy", "Fantasy player"],
                            ["bettor", "Bettor"],
                            ["developer", "Developer / Builder"],
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
                    <p className="text-sm text-zinc-300 mb-3">
                        <span className="text-zinc-400 mr-2">2.</span>
                        I care most about…
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {(
                            [
                                ["leaderboard", "Browsing the leaderboard"],
                                ["tracking", "Tracking specific pundits"],
                                ["api", "API access"],
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
                    <p className="text-sm text-zinc-300 mb-3">
                        <span className="text-zinc-400 mr-2">3.</span>
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
    const tierOrder: TierKey[] = ["free", "pro", "api_starter", "api_growth"];

    return (
        <div className="overflow-x-auto rounded-2xl border border-zinc-800">
            <table className="w-full min-w-[640px] text-sm border-collapse">
                {/* Sticky header */}
                <thead>
                    <tr className="border-b border-zinc-800">
                        <th className="sticky left-0 z-10 bg-zinc-950 text-left px-5 py-4 font-medium text-zinc-400 w-56">
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
                                            ? "text-emerald-400"
                                            : "text-zinc-300"
                                    } ${isRecommended ? "relative" : ""}`}
                                >
                                    <div className="flex flex-col items-center gap-1">
                                        <span>{tier.name}</span>
                                        <span className="text-xs font-mono font-normal text-zinc-400">
                                            {formatPrice(tier.monthlyPrice, annual)}
                                            {tier.monthlyPrice > 0 && (
                                                <span className="text-zinc-400">/mo</span>
                                            )}
                                        </span>
                                        {isRecommended && (
                                            <span className="text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full px-2 py-0.5 animate-pulse">
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
                            className={`border-b border-zinc-800/60 ${
                                i % 2 === 0 ? "bg-zinc-950" : "bg-zinc-900/30"
                            }`}
                        >
                            <td className="sticky left-0 z-10 px-5 py-3.5 text-zinc-300 font-medium bg-inherit">
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
                                                ? "border-x border-emerald-500/20"
                                                : ""
                                        } ${
                                            isRecommended && !isPro
                                                ? "border-x border-emerald-400/30"
                                                : ""
                                        }`}
                                    >
                                        {val === "✓" ? (
                                            <span className="text-emerald-400 font-bold">✓</span>
                                        ) : val === "—" ? (
                                            <span className="text-zinc-700">—</span>
                                        ) : (
                                            <span className="text-zinc-400 text-xs font-mono">{val}</span>
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
                    className={`text-sm ${!annual ? "text-white font-medium" : "text-zinc-400"}`}
                >
                    Monthly
                </span>
                <button
                    role="switch"
                    aria-checked={annual}
                    onClick={() => setAnnual(!annual)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        annual ? "bg-emerald-500" : "bg-zinc-700"
                    }`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                            annual ? "translate-x-6" : "translate-x-1"
                        }`}
                    />
                </button>
                <span
                    className={`text-sm ${annual ? "text-white font-medium" : "text-zinc-400"}`}
                >
                    Annual{" "}
                    <span className="text-emerald-400 text-xs font-mono">(save 20%)</span>
                </span>
            </div>

            {/* ── Card grid (existing, preserved) ── */}
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {TIERS.map((tier) => {
                    const isRecommended = recommendedTier === tier.key;
                    return (
                        <div
                            key={tier.key}
                            data-tier={tier.key}
                            className={`rounded-2xl p-6 space-y-4 flex flex-col transition-all ${
                                isRecommended
                                    ? "ring-2 ring-emerald-400 ring-offset-2 ring-offset-black"
                                    : ""
                            } ${
                                tier.highlight
                                    ? "border border-emerald-500/40 bg-emerald-500/5"
                                    : "border border-zinc-800 bg-zinc-900/50"
                            }`}
                        >
                            <div>
                                <div
                                    className={`text-xs font-mono uppercase tracking-widest mb-1 ${
                                        tier.highlight ? "text-emerald-400" : "text-zinc-400"
                                    }`}
                                >
                                    {tier.name}
                                    {isRecommended && (
                                        <span className="ml-2 text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full px-1.5 py-0.5 animate-pulse">
                                            Recommended
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-baseline gap-0.5">
                                    <span className="text-2xl font-black text-white">
                                        {formatPrice(tier.monthlyPrice, annual)}
                                    </span>
                                    {tier.monthlyPrice > 0 && (
                                        <span className="text-zinc-400 text-sm">/mo</span>
                                    )}
                                </div>
                                {annual && tier.monthlyPrice > 0 && (
                                    <p className="text-xs text-zinc-400 mt-0.5">
                                        billed ${Math.round(tier.monthlyPrice * ANNUAL_DISCOUNT * 12)}/yr
                                    </p>
                                )}
                            </div>

                            <ul className="space-y-2 text-sm text-zinc-400 flex-1">
                                {tier.features.map((f) => (
                                    <li key={f} className="flex items-start gap-2">
                                        <span className="text-emerald-400 mt-0.5">✓</span>
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
                                                ? "bg-emerald-500 hover:bg-emerald-400 text-black"
                                                : "bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700"
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
                                    className="block text-center py-2.5 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-300 hover:border-zinc-500 hover:text-white transition-colors"
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
                <h2 className="text-lg font-semibold text-white mb-4">Compare all features</h2>
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
