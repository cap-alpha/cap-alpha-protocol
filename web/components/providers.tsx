"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { PersonaProvider } from "@/components/persona-context";
import { TeamProvider } from "@/components/team-context";
import { ReactNode } from "react";

const hasClerkConfig = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export function Providers({ children }: { children: ReactNode }) {
    // Skip ClerkProvider if Clerk is not configured
    if (!hasClerkConfig) {
        return (
            <TeamProvider>
                <PersonaProvider>
                    {children}
                </PersonaProvider>
            </TeamProvider>
        );
    }

    return (
        <ClerkProvider
            appearance={{
                baseTheme: dark,
                variables: { colorPrimary: '#10b981' },
            }}
        >
            <TeamProvider>
                <PersonaProvider>
                    {children}
                </PersonaProvider>
            </TeamProvider>
        </ClerkProvider>
    );
}
