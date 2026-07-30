import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { Activity } from "lucide-react";
import { PageContainer } from "@/components/ui/page-container";
import { SectionHeading } from "@/components/ui/heading";
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
        <div className="min-h-screen bg-editorial-bg text-ink">
            {/* Header */}
            <div className="border-b border-editorial-border bg-editorial-card">
                <PageContainer size="4xl" className="px-4 py-8">
                    <div className="flex items-center gap-2 mb-2">
                        <Activity className="w-4 h-4 text-accent-editorial" />
                        <span className="text-xs font-mono uppercase tracking-widest text-accent-editorial">
                            Account
                        </span>
                    </div>
                    <SectionHeading size="xl" className="text-ink">
                        Usage Dashboard
                    </SectionHeading>
                    <p className="mt-1 text-sm text-ink-2 max-w-lg">
                        Monitor your API consumption, rate limits, and upgrade
                        when you need more.
                    </p>
                </PageContainer>
            </div>

            {/* Content */}
            <PageContainer size="4xl" className="px-4 py-8">
                <UsageDashboard />
            </PageContainer>
        </div>
    );
}
