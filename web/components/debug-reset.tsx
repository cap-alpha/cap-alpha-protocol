"use client";

import { Trash2 } from "lucide-react";

export function DebugReset() {
    const handleReset = () => {
        // Clear all local app state
        localStorage.clear();
        sessionStorage.clear();

        // 1. Delete Clerk cookies manually to force session purge on client.
        // The __session cookie and __client_uat are typically what keeps the clerk state alive
        document.cookie = "__session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        document.cookie = "__client_uat=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";

        // 2. Hard redirect to the root page, which handles the unauthenticated state
        window.location.href = "/";
    };

    if (process.env.NODE_ENV !== "development") {
        return null;
    }

    return (
        <button
            onClick={handleReset}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-semibold rounded-md border border-red-900 bg-red-950 text-red-400 hover:bg-red-900 transition-colors"
            title="Clear cookies & local storage to simulate brand new user"
        >
            <Trash2 className="w-3 h-3" />
            <span>Reset State (Dev)</span>
        </button>
    );
}
