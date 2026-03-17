"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { PersonaProvider } from "@/components/persona-context";
import { TeamProvider } from "@/components/team-context";
import { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
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
