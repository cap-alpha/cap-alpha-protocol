"use client";

/**
 * Forces a Clerk session refresh after Stripe/LemonSqueezy checkout so that
 * `publicMetadata.tier` reflects the new Pro subscription immediately —
 * without requiring a manual page reload or re-login.
 *
 * Rendered by `/dashboard` only when `?checkout=success` is present in the
 * URL. Clears the query param after the reload to prevent repeated calls.
 *
 * Issue: #771 Phase 1
 */

import { useEffect } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter, useSearchParams } from "next/navigation";

export function CheckoutSuccessHandler() {
    const { user, isLoaded } = useUser();
    const router = useRouter();
    const searchParams = useSearchParams();

    useEffect(() => {
        if (!isLoaded) return;
        if (searchParams.get("checkout") !== "success") return;

        async function refreshAndRedirect() {
            if (user) {
                await user.reload();
            }
            // Strip the checkout param so a hard-refresh doesn't re-trigger this.
            router.replace("/dashboard");
        }

        refreshAndRedirect();
    }, [isLoaded, user, router, searchParams]);

    return null;
}
