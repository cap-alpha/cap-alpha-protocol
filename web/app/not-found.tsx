import Link from "next/link";
import { Home, Search } from "lucide-react";

export const dynamic = 'force-dynamic';

export default function NotFound() {
    return (
        <div className="flex min-h-[80vh] flex-col items-center justify-center p-4 text-center">
            <p className="text-8xl font-black text-zinc-800 select-none mb-4">404</p>
            <h1 className="text-3xl md:text-4xl font-black uppercase tracking-tighter text-white mb-3">
                Page Not Found
            </h1>
            <p className="text-zinc-400 max-w-md mb-10 text-base mx-auto">
                This page doesn&apos;t exist — or was moved. Check the URL or head back to the
                ledger.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
                <Link
                    href="/"
                    className="px-5 py-2.5 bg-white text-black font-bold uppercase tracking-wider rounded-lg hover:bg-zinc-200 transition-colors flex items-center justify-center gap-2"
                >
                    <Home className="h-4 w-4" /> Home
                </Link>
                <Link
                    href="/ledger"
                    className="px-5 py-2.5 border border-white/10 bg-white/5 text-white font-bold uppercase tracking-wider rounded-lg hover:bg-white/10 transition-colors flex items-center justify-center gap-2"
                >
                    <Search className="h-4 w-4" /> Pundit Ledger
                </Link>
            </div>
        </div>
    );
}
