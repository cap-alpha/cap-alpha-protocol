import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { Activity } from "lucide-react";
import { UsageDashboard } from "@/components/usage-dashboard";

export const dynamic = 'force-dynamic';

export const metadata = {
    title: "Usage Dashboard | Pundit Ledger",
    description: "Monitor your API usage, quotas, and rate limits.",
};

export default async function UsagePage() {
    const { userId } = auth();

    if (!userId) {
        redirect("/sign-in");
    }

    return (
        <div className="min-h-screen bg-black text-white">
            {/* Header */}
            <div className="border-b border-zinc-900 bg-zinc-950/50">
                <div className="max-w-4xl mx-auto px-4 py-8">
                    <div className="flex items-center gap-2 mb-2">
                        <Activity className="w-4 h-4 text-emerald-400" />
                        <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                            Account
                        </span>
                    </div>
                    <h1 className="text-3xl font-black tracking-tight text-white">
                        Usage Dashboard
                    </h1>
                    <p className="mt-1 text-sm text-zinc-400 max-w-lg">
                        Monitor your API consumption, rate limits, and upgrade
                        when you need more.
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-4xl mx-auto px-4 py-8">
                <UsageDashboard />
            </div>
        </div>
    );
}
