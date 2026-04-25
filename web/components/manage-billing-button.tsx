"use client";

import { useState } from "react";

interface ManageBillingButtonProps {
    label?: string;
}

export function ManageBillingButton({ label = "Manage Subscription" }: ManageBillingButtonProps) {
    const [loading, setLoading] = useState(false);

    async function handleManage() {
        setLoading(true);
        try {
            const res = await fetch("/api/billing/portal", { method: "POST" });
            const data = await res.json();
            if (data.url) {
                window.location.href = data.url;
            } else {
                console.error("No portal URL returned", data);
                setLoading(false);
            }
        } catch (err) {
            console.error("Portal redirect failed", err);
            setLoading(false);
        }
    }

    return (
        <button
            onClick={handleManage}
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 disabled:opacity-60 border border-zinc-700 text-sm font-semibold text-white transition-colors"
        >
            {loading ? "Redirecting…" : label}
        </button>
    );
}
