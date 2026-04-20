"use client";

import { PersonaProvider } from "@/components/persona-context";
import { TeamProvider } from "@/components/team-context";
import { ReactNode } from "react";

const hasClerkKey = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

function InnerProviders({ children }: { children: ReactNode }) {
    return (
        <TeamProvider>
            <PersonaProvider>
                {children}
            </PersonaProvider>
        </TeamProvider>
    );
}

export function Providers({ children }: { children: ReactNode }) {
    if (!hasClerkKey) {
        return <InnerProviders>{children}</InnerProviders>;
    }

    // Dynamic require avoids importing @clerk/nextjs when keys are absent.
    // This is a top-level component, not a hook — safe to require conditionally.
    const { ClerkProvider } = require("@clerk/nextjs");
    const { dark } = require("@clerk/themes");

    return (
        <ClerkProvider
            appearance={{
                baseTheme: dark,
                variables: { colorPrimary: '#10b981' },
            }}
        >
            <InnerProviders>{children}</InnerProviders>
        </ClerkProvider>
    );
}
