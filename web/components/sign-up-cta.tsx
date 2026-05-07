"use client";

import { SignInButton, SignUpButton } from "@clerk/nextjs";

export function SignUpCta() {
    return (
        <p className="text-xs text-zinc-500">
            Already have an account?{" "}
            <SignInButton mode="modal">
                <span className="cursor-pointer text-emerald-400 hover:text-emerald-300 transition-colors underline-offset-2 hover:underline">
                    Sign In →
                </span>
            </SignInButton>
            {" "}·{" "}
            <SignUpButton mode="modal">
                <span className="cursor-pointer text-emerald-400 hover:text-emerald-300 transition-colors underline-offset-2 hover:underline">
                    Create a free account →
                </span>
            </SignUpButton>
        </p>
    );
}
