"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useUser } from "@clerk/nextjs";
import { updateUserTeam } from "@/app/actions/user";

interface TeamContextType {
    activeTeam: string | null;
    setActiveTeam: (team: string) => Promise<void>;
    isLoading: boolean;
}

const TeamContext = createContext<TeamContextType | undefined>(undefined);

export function TeamProvider({ children }: { children: ReactNode }) {
    const { user, isLoaded } = useUser();
    const [activeTeam, setActiveTeamState] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Sync with User Metadata or Local Storage
    useEffect(() => {
        if (!isLoaded) return;

        const syncTeam = async () => {
            // 1. Check User Metadata (Server Truth)
            if (user?.publicMetadata?.favorite_team) {
                console.log("TeamContext: Found team in metadata:", user.publicMetadata.favorite_team);
                setActiveTeamState(user.publicMetadata.favorite_team as string);
                localStorage.setItem("favorite_team", user.publicMetadata.favorite_team as string); // Sync local
            }
            // 2. Check Local Storage (Guest / Fallback)
            else {
                const localTeam = localStorage.getItem("favorite_team");
                if (localTeam) {
                    console.log("TeamContext: Found team in localStorage:", localTeam);
                    setActiveTeamState(localTeam);
                }
            }
            setIsLoading(false);
        };

        syncTeam();
    }, [user, isLoaded]);

    const setActiveTeam = async (team: string) => {
        // Optimistic Update
        setActiveTeamState(team);
        localStorage.setItem("favorite_team", team);

        // Persist to Server if logged in
        if (user) {
            try {
                await updateUserTeam(team);
                // Also update client-side user object to reflect change immediately? 
                // Clerk usually handles this via revalidation, but we might need user.reload() if strictly necessary.
                await user.reload();
            } catch (error) {
                console.error("TeamContext: Failed to persist team", error);
                // Revert? For now, we keep optimistic update.
            }
        }
    };

    return (
        <TeamContext.Provider value={{ activeTeam, setActiveTeam, isLoading }}>
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
