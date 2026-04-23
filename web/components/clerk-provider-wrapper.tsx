"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { ReactNode } from "react";

export default function ClerkProviderWrapper({ children }: { children: ReactNode }) {
    return (
        <ClerkProvider
            appearance={{
                baseTheme: dark,
                variables: { colorPrimary: '#10b981' },
            }}
        >
            {children}
        </ClerkProvider>
    );
}
