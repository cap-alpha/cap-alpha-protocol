"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { updateUserTeam } from "@/app/actions/user";

const hasClerkKey = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

interface TeamContextType {
    activeTeam: string | null;
    setActiveTeam: (team: string) => Promise<void>;
    isLoading: boolean;
    isTeamSelectorOpen: boolean;
    setTeamSelectorOpen: (open: boolean) => void;
}

const TeamContext = createContext<TeamContextType | undefined>(undefined);

/**
 * TeamProvider that uses Clerk for user metadata when available,
 * falls back to localStorage-only when Clerk keys are absent (CI/Docker).
 */
export function TeamProvider({ children }: { children: ReactNode }) {
    if (hasClerkKey) {
        return <ClerkTeamProvider>{children}</ClerkTeamProvider>;
    }
    return <LocalTeamProvider>{children}</LocalTeamProvider>;
}

/** Full provider — uses Clerk useUser() for metadata sync. */
function ClerkTeamProvider({ children }: { children: ReactNode }) {
    // Safe to call useUser here — this component only renders when ClerkProvider exists
    const { useUser } = require("@clerk/nextjs");
    const { user, isLoaded } = useUser();
    const [activeTeam, setActiveTeamState] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isTeamSelectorOpen, setTeamSelectorOpen] = useState(false);

    useEffect(() => {
        if (!isLoaded) return;
        const syncTeam = async () => {
            if (user?.publicMetadata?.favorite_team) {
                setActiveTeamState(user.publicMetadata.favorite_team as string);
                localStorage.setItem("favorite_team", user.publicMetadata.favorite_team as string);
            } else {
                const localTeam = localStorage.getItem("favorite_team");
                if (localTeam) setActiveTeamState(localTeam);
            }
            setIsLoading(false);
        };
        syncTeam();
    }, [user, isLoaded]);

    const setActiveTeam = async (team: string) => {
        setActiveTeamState(team);
        localStorage.setItem("favorite_team", team);
        if (user) {
            try {
                await updateUserTeam(team);
                await user.reload();
            } catch (error) {
                console.error("TeamContext: Failed to persist team", error);
            }
        }
    };

    return (
        <TeamContext.Provider value={{ activeTeam, setActiveTeam, isLoading, isTeamSelectorOpen, setTeamSelectorOpen }}>
            {children}
        </TeamContext.Provider>
    );
}

/** Lightweight provider — localStorage only, no Clerk dependency. */
function LocalTeamProvider({ children }: { children: ReactNode }) {
    const [activeTeam, setActiveTeamState] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isTeamSelectorOpen, setTeamSelectorOpen] = useState(false);

    useEffect(() => {
        const localTeam = localStorage.getItem("favorite_team");
        if (localTeam) setActiveTeamState(localTeam);
        setIsLoading(false);
    }, []);

    const setActiveTeam = async (team: string) => {
        setActiveTeamState(team);
        localStorage.setItem("favorite_team", team);
    };

    return (
        <TeamContext.Provider value={{ activeTeam, setActiveTeam, isLoading, isTeamSelectorOpen, setTeamSelectorOpen }}>
            {children}
        </TeamContext.Provider>
    );
}

export function useTeam() {
    const context = useContext(TeamContext);
    if (context === undefined) {
        throw new Error("useTeam must be used within a TeamProvider");
    }
    return context;
}
