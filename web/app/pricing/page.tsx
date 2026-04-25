import { UpgradeButton } from "@/components/upgrade-button";
import Link from "next/link";

export const metadata = {
    title: "Pricing | Pundit Ledger",
    description: "Choose the plan that fits how deeply you want to hold pundits accountable.",
};

const TIERS = [
    {
        key: "free",
        name: "Free",
        price: "$0",
        period: null,
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
        price: "$14.99",
        period: "/mo",
        features: [
            "Everything in Free",
            "Full 6-axis Pundit Credit Score",
            "Complete prediction history",
            "Magnitude tracking (how wrong)",
            "Multi-sport coverage",
            "Bulk CSV export",
        ],
        cta: { plan: "pro", label: "Upgrade to Pro" },
        highlight: true,
    },
    {
        key: "api_starter",
        name: "API Starter",
        price: "$99",
        period: "/mo",
        features: [
            "Everything in Pro",
            "REST API access",
            "10,000 requests/month",
            "Per-pundit scores + history",
            "Resolution data",
        ],
        cta: { plan: "api_starter", label: "Get API Starter" },
        highlight: false,
    },
    {
        key: "api_growth",
        name: "API Growth",
        price: "$499",
        period: "/mo",
        features: [
            "Everything in API Starter",
            "100,000 requests/month",
            "Priority support",
            "SLA guarantee",
        ],
        cta: { plan: "api_growth", label: "Get API Growth" },
        highlight: false,
    },
];

export default function PricingPage() {
    return (
        <main className="bg-black text-white min-h-[100dvh] px-6 py-20">
            <div className="max-w-5xl mx-auto space-y-12">
                <div className="text-center space-y-3">
                    <h1 className="text-4xl font-black tracking-tight">Pricing</h1>
                    <p className="text-zinc-400 max-w-xl mx-auto">
                        Choose how deeply you want to hold pundits accountable. All plans include the
                        cryptographically verified ledger.
                    </p>
                </div>

                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {TIERS.map((tier) => (
                        <div
                            key={tier.key}
                            className={`rounded-2xl p-6 space-y-4 flex flex-col ${
                                tier.highlight
                                    ? "border border-emerald-500/40 bg-emerald-500/5"
                                    : "border border-zinc-800 bg-zinc-900/50"
                            }`}
                        >
                            <div>
                                <div
                                    className={`text-xs font-mono uppercase tracking-widest mb-1 ${
                                        tier.highlight ? "text-emerald-400" : "text-zinc-500"
                                    }`}
                                >
                                    {tier.name}
                                </div>
                                <div className="flex items-baseline gap-0.5">
                                    <span className="text-2xl font-black text-white">{tier.price}</span>
                                    {tier.period && (
                                        <span className="text-zinc-500 text-sm">{tier.period}</span>
                                    )}
                                </div>
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
                                <UpgradeButton
                                    plan={tier.cta.plan}
                                    label={tier.cta.label}
                                    className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors ${
                                        tier.highlight
                                            ? "bg-emerald-500 hover:bg-emerald-400 text-black"
                                            : "bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700"
                                    }`}
                                />
                            ) : (
                                <Link
                                    href="/ledger"
                                    className="block text-center py-2.5 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-300 hover:border-zinc-500 hover:text-white transition-colors"
                                >
                                    View Leaderboard
                                </Link>
                            )}
                        </div>
                    ))}
                </div>

                <p className="text-center text-xs text-zinc-600">
                    Enterprise pricing available for teams and media organizations.{" "}
                    <a href="mailto:hello@cap-alpha.co" className="underline hover:text-zinc-400">
                        Contact us.
                    </a>
                </p>
            </div>
        </main>
    );
}
