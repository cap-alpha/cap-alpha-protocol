"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { PersonaProvider } from "@/components/persona-context";
import { TeamProvider } from "@/components/team-context";
import { ReactNode } from "react";

const hasClerkKey = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export function Providers({ children }: { children: ReactNode }) {
    const inner = (
        <TeamProvider>
            <PersonaProvider>
                {children}
            </PersonaProvider>
        </TeamProvider>
    );

    if (!hasClerkKey) {
        // No Clerk publishable key (CI / Docker E2E) — render without auth provider
        return inner;
    }

    return (
        <ClerkProvider
            appearance={{
                baseTheme: dark,
                variables: { colorPrimary: '#10b981' },
            }}
        >
            {inner}
        </ClerkProvider>
    );
}
