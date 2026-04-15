"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GlobalSearch } from "./global-search";
import { useState, useEffect } from "react";
import { useTeam } from "./team-context";

const hasClerkKey = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

// Safe wrapper: only call useUser() when Clerk is available
function useClerkUser(): { isSignedIn: boolean | undefined; isLoaded: boolean } {
    if (!hasClerkKey) {
        return { isSignedIn: false, isLoaded: true };
    }
    // eslint-disable-next-line @typescript-eslint/no-var-requires, react-hooks/rules-of-hooks
    const { useUser } = require("@clerk/nextjs");
    return useUser();
}

export function Navbar() {
    const pathname = usePathname();
    const { isSignedIn, isLoaded } = useClerkUser();
    const { activeTeam, setTeamSelectorOpen } = useTeam();
    const [isScrolled, setIsScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            if (window.scrollY > 20) {
                setIsScrolled(true);
            } else {
                setIsScrolled(false);
            }
        };

        window.addEventListener("scroll", handleScroll);
        // Fire once on mount
        handleScroll();

        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    const isRoot = pathname === '/';

    // Dynamically render auth UI only when Clerk is available
    const renderAuth = () => {
        if (!hasClerkKey || !isLoaded) return null;
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const { UserButton, SignInButton } = require("@clerk/nextjs");
        if (isSignedIn) {
            return <UserButton afterSignOutUrl="/" appearance={{ elements: { avatarBox: "w-9 h-9 border border-emerald-500/50" } }} />;
        }
        return (
            <SignInButton mode="modal">
                <span className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white transition-colors bg-white/5 px-4 py-2 rounded-md border border-white/10 hover:border-emerald-500/50 hover:bg-emerald-500/10">
                    Sign In
                </span>
            </SignInButton>
        );
    };

    return (
        <header
            className={`sticky top-0 z-50 w-full transition-all duration-300 ${
                isScrolled || !isRoot
                    ? "border-b border-white/10 bg-black/80 backdrop-blur-md"
                    : "border-b-transparent bg-transparent"
            }`}
        >
            <div className="container mx-auto px-4 h-16 flex items-center justify-between">
                <div className="flex items-center gap-6">
                    <Link href="/" className="flex items-center gap-2">
                        <span className="font-black text-xl tracking-tighter uppercase text-emerald-500">
                            Pundit Ledger
                        </span>
                    </Link>

                    {/* Navigation Links */}
                    <nav className="hidden md:flex items-center gap-6 text-sm font-medium tracking-wide">
                        <Link
                            href="/dashboard"
                            className={`transition-colors hover:text-emerald-400 ${pathname?.includes('/dashboard') ? 'text-emerald-500' : 'text-slate-400'}`}
                        >
                            DASHBOARD
                        </Link>
                        <Link
                            href="/dashboard/team-select"
                            className="transition-colors hover:text-emerald-400 text-slate-400 uppercase tracking-wide font-medium"
                        >
                            {activeTeam ? `TEAM: ${activeTeam}` : "SELECT TEAM"}
                        </Link>
                        <Link
                            href="/ledger"
                            className={`transition-colors hover:text-emerald-400 ${pathname?.includes('/ledger') ? 'text-emerald-500' : 'text-slate-400'}`}
                        >
                            LEDGER
                        </Link>
                        <Link
                            href="/dashboard/api-keys"
                            className={`transition-colors hover:text-emerald-400 ${pathname?.includes('/api-keys') ? 'text-emerald-500' : 'text-slate-400'}`}
                        >
                            API KEYS
                        </Link>
                    </nav>
                </div>

                <div className="flex items-center gap-4">
                    <GlobalSearch />
                    {renderAuth()}
                </div>
            </div>
        </header>
    );
}
