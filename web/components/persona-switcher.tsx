"use client";

import React from "react";
import { usePersona, Persona } from "./persona-context";
import { Activity, CircleDollarSign, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth, SignInButton } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

export default function PersonaSwitcher() {
    const { persona, setPersona } = usePersona();
    const { isSignedIn } = useAuth();
    const router = useRouter();

    const options: { id: Persona; label: string; icon: React.ReactNode; isPro: boolean; path: string }[] = [
        { id: "FAN", label: "Fan", icon: <Users className="h-4 w-4" />, isPro: false, path: "/dashboard/fan" },
        { id: "BETTOR", label: "Bettor", icon: <Activity className="h-4 w-4" />, isPro: true, path: "/dashboard/bettor" },
        { id: "AGENT", label: "Agent", icon: <CircleDollarSign className="h-4 w-4" />, isPro: true, path: "/dashboard/agent" },
    ];

    const handleSwitch = (id: Persona, path: string) => {
        setPersona(id);
        router.push(path);
    };

    return (
        <div className="flex items-center space-x-1 bg-gray-900/50 backdrop-blur-md p-1 rounded-lg border border-white/10">
            {options.map((option) => {
                const ButtonContent = (
                    <button
                        key={option.id}
                        onClick={() => {
                            if (!option.isPro || isSignedIn) {
                                handleSwitch(option.id, option.path);
                            }
                        }}
                        className={cn(
                            "flex items-center space-x-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200",
                            persona === option.id
                                ? "bg-blue-600 text-white shadow-lg shadow-blue-500/20"
                                : "text-gray-400 hover:text-white hover:bg-white/5"
                        )}
                    >
                        {option.icon}
                        <span>{option.label}</span>
                    </button>
                );

                if (option.isPro && !isSignedIn) {
                    return (
                        <SignInButton key={option.id} mode="modal" fallbackRedirectUrl={option.path}>
                            {ButtonContent}
                        </SignInButton>
                    );
                }

                return ButtonContent;
            })}
        </div>
    );
}
