"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton, useUser, SignInButton } from "@clerk/nextjs";
import { GlobalSearch } from "./global-search";
import { useState, useEffect } from "react";
import { useTeam } from "./team-context";

export function Navbar() {
    const pathname = usePathname();
    const { isSignedIn, isLoaded } = useUser();
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

    // Do not show on the absolute index page if you want that to remain a clean landing page,
    // but the user wants navigation, so we'll show it everywhere or maybe skip on '/' if it has a hero.
    // Let's show it everywhere for consistency, but with a transparent background on top of the landing page maybe?
    // A sticky dark navbar is usually fine.
    
    const isRoot = pathname === '/';

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
                            Cap Alpha
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
                        <button 
                            onClick={() => setTeamSelectorOpen(true)}
                            className="transition-colors hover:text-emerald-400 text-slate-400 uppercase tracking-wide font-medium"
                        >
                            {activeTeam ? `TEAM: ${activeTeam}` : "SELECT TEAM"}
                        </button>
                    </nav>
                </div>

                <div className="flex items-center gap-4">
                    <GlobalSearch />
                    
                    {/* Auth */}
                    {isLoaded && (
                        isSignedIn ? (
                            <UserButton afterSignOutUrl="/" appearance={{ elements: { avatarBox: "w-9 h-9 border border-emerald-500/50" } }} />
                        ) : (
                            <SignInButton mode="modal">
                                <span className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white transition-colors bg-white/5 px-4 py-2 rounded-md border border-white/10 hover:border-emerald-500/50 hover:bg-emerald-500/10">
                                    Sign In
                                </span>
                            </SignInButton>
                        )
                    )}
                </div>
            </div>
        </header>
    );
}
