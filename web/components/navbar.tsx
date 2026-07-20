"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton, useUser, SignInButton, SignUpButton } from "@clerk/nextjs";
import { useState, useEffect } from "react";
import { PunditSearchBar } from "@/components/pundit-search-bar";

// Routes visible only to signed-in users
const AUTH_ONLY_ROUTES = ["/dashboard", "/scenarios", "/fantasy"];

export function Navbar() {
    const pathname = usePathname();
    const { isSignedIn, isLoaded } = useUser();
    const [isScrolled, setIsScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 20);
        };
        window.addEventListener("scroll", handleScroll);
        handleScroll();
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    const isRoot = pathname === "/";

    return (
        <header
            className={`sticky top-0 z-50 w-full transition-all duration-300 ${
                isScrolled || !isRoot
                    ? "border-b-[3px] border-b-gold-light bg-navy/95 backdrop-blur-md"
                    : "border-b-[3px] border-b-transparent bg-navy/80"
            }`}
            style={{ borderBottomColor: isScrolled || !isRoot ? 'hsl(var(--gold-light))' : 'transparent', backgroundColor: 'hsl(var(--navy))' }}
        >
            <div className="container mx-auto px-4 h-16 flex items-center justify-between">
                <div className="flex items-center gap-6">
                    <Link href="/" className="flex items-center gap-2 min-h-[44px]">
                        <span className="logo-mark text-xl text-white">
                            Cap<span className="logo-alpha">α</span>
                        </span>
                    </Link>

                    {/* Bettor-first navigation — primary: Ledger, secondary: Pundits, tertiary: Draft */}
                    <nav className="hidden md:flex items-center gap-6 text-sm font-body font-semibold tracking-wide">
                        {/* Primary: Ledger (in-play + leaderboard) */}
                        <Link
                            href="/ledger"
                            className={`transition-colors hover:text-yellow-300 ${
                                pathname?.startsWith("/ledger")
                                    ? "text-yellow-300"
                                    : "text-white/80"
                            }`}
                        >
                            LEDGER
                        </Link>
                        {/* Secondary: In Play — surfaces live predictions directly */}
                        <Link
                            href="/ledger?view=in-play"
                            className={`transition-colors hover:text-yellow-300 ${
                                pathname?.startsWith("/ledger") && pathname === "/ledger"
                                    ? "text-white/60"
                                    : "text-white/60"
                            } text-xs tracking-widest`}
                            aria-label="In Play predictions"
                        >
                            IN PLAY
                        </Link>
                        {/* Trust: Methodology */}
                        <Link
                            href="/methodology"
                            className={`transition-colors hover:text-yellow-300 ${
                                pathname?.startsWith("/methodology")
                                    ? "text-yellow-300"
                                    : "text-white/80"
                            }`}
                        >
                            METHODOLOGY
                        </Link>
                        {/* Auth-only: Account management */}
                        {isSignedIn && (
                            <Link
                                href="/account"
                                className={`transition-colors hover:text-yellow-300 ${
                                    pathname?.includes("/account") ||
                                    pathname?.startsWith("/dashboard/usage")
                                        ? "text-yellow-300"
                                        : "text-white/80"
                                }`}
                            >
                                ACCOUNT
                            </Link>
                        )}
                    </nav>
                </div>

                {/* Desktop pundit search — center of navbar, ≥1024px only */}
                <div className="hidden lg:flex flex-1 justify-center px-8 max-w-sm mx-auto">
                    <PunditSearchBar
                        placeholder="Search pundits..."
                        className="w-full"
                    />
                </div>

                <div className="flex items-center gap-4">
                    {/* Auth */}
                    {isLoaded && (
                        isSignedIn ? (
                            <UserButton
                                afterSignOutUrl="/"
                                appearance={{
                                    elements: {
                                        avatarBox: "w-9 h-9 border border-emerald-500/50",
                                    },
                                }}
                            />
                        ) : (
                            <div className="flex items-center gap-2">
                                <SignUpButton mode="modal">
                                    <span className="cursor-pointer text-sm font-medium text-black transition-colors bg-emerald-500 px-3 sm:px-4 py-2 min-h-[44px] inline-flex items-center rounded-md hover:bg-emerald-400">
                                        <span className="hidden sm:inline">Sign Up Free</span>
                                        <span className="sm:hidden">Sign Up</span>
                                    </span>
                                </SignUpButton>
                                <SignInButton mode="modal">
                                    <span className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white transition-colors bg-white/5 px-3 sm:px-4 py-2 min-h-[44px] inline-flex items-center rounded-md border border-white/10 hover:border-emerald-500/50 hover:bg-emerald-500/10">
                                        Sign In
                                    </span>
                                </SignInButton>
                            </div>
                        )
                    )}
                </div>
            </div>
        </header>
    );
}
