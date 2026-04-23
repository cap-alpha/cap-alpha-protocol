"use client";

import { PersonaProvider } from "@/components/persona-context";
import { TeamProvider } from "@/components/team-context";
import dynamic from "next/dynamic";
import { ReactNode } from "react";

const hasClerkKey = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

const ClerkProviderWrapper = hasClerkKey
    ? dynamic(() => import("@/components/clerk-provider-wrapper"), { ssr: false })
    : null;

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
    if (!ClerkProviderWrapper) {
        return <InnerProviders>{children}</InnerProviders>;
    }

    return (
        <ClerkProviderWrapper>
            <InnerProviders>{children}</InnerProviders>
        </ClerkProviderWrapper>
    );
}
