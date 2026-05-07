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

                    {/* Public navigation */}
                    <nav className="hidden md:flex items-center gap-6 text-sm font-medium tracking-wide">
                        <Link
                            href="/ledger"
                            className={`transition-colors hover:text-emerald-400 ${
                                pathname?.startsWith("/ledger")
                                    ? "text-emerald-500"
                                    : "text-slate-400"
                            }`}
                        >
                            LEADERBOARD
                        </Link>
                        <Link
                            href="/methodology"
                            className={`transition-colors hover:text-emerald-400 ${
                                pathname?.startsWith("/methodology")
                                    ? "text-emerald-500"
                                    : "text-slate-400"
                            }`}
                        >
                            METHODOLOGY
                        </Link>
                        {/* Auth-only links — shown only when signed in */}
                        {isSignedIn && (
                            <>
                                <Link
                                    href="/dashboard"
                                    className={`transition-colors hover:text-emerald-400 ${
                                        pathname?.startsWith("/dashboard") &&
                                        !pathname?.startsWith("/dashboard/usage")
                                            ? "text-emerald-500"
                                            : "text-slate-400"
                                    }`}
                                >
                                    DASHBOARD
                                </Link>
                                <Link
                                    href="/account"
                                    className={`transition-colors hover:text-emerald-400 ${
                                        pathname?.includes("/account") ||
                                        pathname?.startsWith("/dashboard/usage")
                                            ? "text-emerald-500"
                                            : "text-slate-400"
                                    }`}
                                >
                                    ACCOUNT
                                </Link>
                            </>
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
                                    <span className="cursor-pointer text-sm font-medium text-black transition-colors bg-emerald-500 px-4 py-2 rounded-md hover:bg-emerald-400">
                                        Sign Up Free
                                    </span>
                                </SignUpButton>
                                <SignInButton mode="modal">
                                    <span className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white transition-colors bg-white/5 px-4 py-2 rounded-md border border-white/10 hover:border-emerald-500/50 hover:bg-emerald-500/10">
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
