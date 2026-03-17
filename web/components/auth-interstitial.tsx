"use client";

import { useEffect, useState } from "react";
import { useAuth, SignIn } from "@clerk/nextjs";

export function AuthInterstitial() {
    const { isLoaded, isSignedIn } = useAuth();
    const [showSignIn, setShowSignIn] = useState(false);

    useEffect(() => {
        if (!isLoaded) return;
        if (isSignedIn) return; // user is logged in, no interstitial

        const lastSeenStr = localStorage.getItem("last_seen");
        const now = Date.now();

        if (lastSeenStr) {
            const lastSeen = parseInt(lastSeenStr, 10);
            const daysSince = (now - lastSeen) / (1000 * 60 * 60 * 24);

            if (daysSince < 7) {
                // Returning user within 7 days, show immediate modal
                setShowSignIn(true);
            } else {
                // Older than 7 days, treat as new user (no forced roam)
                localStorage.setItem("last_seen", now.toString());
            }
        } else {
            // Completely new user (no forced roam)
            localStorage.setItem("last_seen", now.toString());
        }
    }, [isLoaded, isSignedIn]);

    if (!showSignIn || isSignedIn) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/90 backdrop-blur-xl animate-in fade-in duration-300">
            <div className="animate-in zoom-in-95 fill-mode-both duration-300 delay-150 relative">
                <button
                    onClick={() => setShowSignIn(false)}
                    className="absolute -top-10 right-0 text-zinc-400 hover:text-white transition-colors"
                    aria-label="Close"
                >
                    ✕ Close
                </button>
                <SignIn routing="hash" />
            </div>
        </div>
    );
}
