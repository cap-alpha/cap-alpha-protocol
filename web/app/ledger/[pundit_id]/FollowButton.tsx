"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { followPundit, unfollowPundit } from "@/app/actions/follow";

interface FollowButtonProps {
    punditId: string;
    punditName: string;
    isFollowing: boolean;
    isAuthenticated: boolean;
}

export function FollowButton({
    punditId,
    punditName,
    isFollowing: initialIsFollowing,
    isAuthenticated,
}: FollowButtonProps) {
    const [isFollowing, setIsFollowing] = useState(initialIsFollowing);
    const [isPending, startTransition] = useTransition();
    const router = useRouter();

    const DS = {
        navy: "#1A2744",
        gold: "#B8860B",
        pos: "#1A7A4A",
        border: "#DDD8D0",
        textLt: "#6B6B6B",
    } as const;

    function handleClick() {
        if (!isAuthenticated) {
            // Redirect to sign-in with return URL
            router.push(`/sign-in?redirect_url=${encodeURIComponent(`/ledger/${punditId}`)}`);
            return;
        }

        // Optimistic update
        const newState = !isFollowing;
        setIsFollowing(newState);

        startTransition(async () => {
            const action = newState ? followPundit : unfollowPundit;
            const result = await action(punditId);
            if (!result.success) {
                // Revert on error
                setIsFollowing(!newState);
                console.error("Follow action failed:", result.error);
            }
        });
    }

    const label = isAuthenticated
        ? isFollowing
            ? "✓ Following"
            : "Follow"
        : "Follow";

    const ariaLabel = isAuthenticated
        ? isFollowing
            ? `Unfollow ${punditName}`
            : `Follow ${punditName}`
        : `Sign in to follow ${punditName}`;

    return (
        <button
            onClick={handleClick}
            disabled={isPending}
            aria-label={ariaLabel}
            title={!isAuthenticated ? "Sign in to follow this pundit" : undefined}
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "7px 16px",
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                cursor: isPending ? "wait" : "pointer",
                border: `1px solid ${isFollowing ? DS.pos : "rgba(255,255,255,0.3)"}`,
                background: isFollowing
                    ? "rgba(26,122,74,0.15)"
                    : "rgba(255,255,255,0.08)",
                color: isFollowing ? "#4ADE80" : "rgba(255,255,255,0.75)",
                borderRadius: 4,
                transition: "all 0.15s ease",
                opacity: isPending ? 0.6 : 1,
            }}
        >
            <span style={{ fontSize: 14, lineHeight: 1 }}>
                {isFollowing ? "★" : "☆"}
            </span>
            {label}
        </button>
    );
}
