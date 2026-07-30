import Link from "next/link";
import { UpgradeButton } from "@/components/upgrade-button";
import { ManageBillingButton } from "@/components/manage-billing-button";
import { SectionHeading } from "@/components/ui/heading";
import { auth, clerkClient } from "@clerk/nextjs/server";

export const dynamic = 'force-dynamic';

export const metadata = {
    title: "Billing | Pundit Ledger",
};

export default async function BillingPage() {
    const { userId } = auth();
    let hasSubscription = false;

    if (userId) {
        const user = await clerkClient.users.getUser(userId);
        hasSubscription = !!user.publicMetadata?.stripe_customer_id;
    }

    return (
        <main className="min-h-[100dvh] bg-editorial-bg text-ink px-6 py-12">
            <div className="max-w-lg mx-auto space-y-8">
                <div>
                    <SectionHeading size="lg">Billing</SectionHeading>
                    <p className="text-ink-2 text-sm mt-1">
                        Manage your subscription and payment method.
                    </p>
                </div>

                {hasSubscription ? (
                    <div className="rounded-xl border border-editorial-border bg-editorial-card p-6 space-y-4">
                        <p className="text-sm text-ink-2">
                            You have an active subscription. Use the Customer Portal to update your
                            payment method, view invoices, or cancel.
                        </p>
                        <ManageBillingButton />
                    </div>
                ) : (
                    <div className="rounded-xl border border-accent-editorial/30 bg-accent-editorial/5 p-6 space-y-4">
                        <div>
                            <div className="text-xs font-mono uppercase tracking-widest text-accent-editorial mb-1">
                                Pro
                            </div>
                            <div className="flex items-baseline gap-0.5">
                                <span className="text-2xl font-black text-ink">$14.99</span>
                                <span className="text-ink-3 text-sm">/mo</span>
                            </div>
                        </div>
                        <ul className="space-y-2 text-sm text-ink-2">
                            <li className="flex items-center gap-2">
                                <span className="text-correct">✓</span> Full 6-axis Pundit Credit Score
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-correct">✓</span> Complete prediction history
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-correct">✓</span> Bulk CSV export
                            </li>
                        </ul>
                        <UpgradeButton plan="pro" />
                        <p className="text-xs text-ink-3 text-center">
                            Need API access?{" "}
                            <Link href="/pricing" className="underline hover:text-ink-2">
                                View all plans
                            </Link>
                        </p>
                    </div>
                )}
            </div>
        </main>
    );
}
