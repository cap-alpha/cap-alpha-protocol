import { Metadata } from "next";
import Link from "next/link";
import { AffiliateInlineLink } from "@/components/affiliate-cta";

export const metadata: Metadata = {
    title: "Pundit Leaderboard",
    description:
        "Live accuracy scores for every tracked sports pundit. See who is actually right.",
};

export default function LedgerLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <>
            {children}
            <footer className="border-t border-zinc-900 px-6 py-8">
                <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-600">
                    <Link
                        href="/"
                        className="font-black text-sm text-emerald-500 tracking-tight uppercase"
                    >
                        Pundit Ledger
                    </Link>
                    <div className="flex items-center gap-6">
                        <Link href="/" className="hover:text-zinc-400 transition-colors">
                            Home
                        </Link>
                        <Link href="/methodology" className="hover:text-zinc-400 transition-colors">
                            Methodology
                        </Link>
                        <Link href="/legal/terms" className="hover:text-zinc-400 transition-colors">
                            Terms
                        </Link>
                        <Link href="/legal/privacy" className="hover:text-zinc-400 transition-colors">
                            Privacy
                        </Link>
                    </div>
                    {/* Placement 3 — Ledger footer affiliate link */}
                    <span className="text-[11px]">
                        Ready to act on the data?{" "}
                        <AffiliateInlineLink
                            platformA="underdog"
                            platformB="prizepicks"
                            label="Sign up at {platform}"
                            placement="ledger_footer"
                        />
                    </span>
                    <span>&copy; {new Date().getFullYear()} Pundit Ledger.</span>
                </div>
            </footer>
        </>
    );
}
