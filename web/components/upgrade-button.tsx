"use client";

import { useState } from "react";

interface UpgradeButtonProps {
    plan?: string;
    label?: string;
    className?: string;
}

export function UpgradeButton({
    plan = "pro",
    label = "Upgrade to Pro",
    className,
}: UpgradeButtonProps) {
    const [loading, setLoading] = useState(false);

    async function handleUpgrade() {
        setLoading(true);
        try {
            const res = await fetch("/api/billing/checkout", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan }),
            });
            const data = await res.json();
            if (data.url) {
                window.location.href = data.url;
            } else {
                console.error("No checkout URL returned", data);
                setLoading(false);
            }
        } catch (err) {
            console.error("Checkout failed", err);
            setLoading(false);
        }
    }

    return (
        <button
            onClick={handleUpgrade}
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
