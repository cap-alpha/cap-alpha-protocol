import Link from "next/link";
import { UpgradeButton } from "@/components/upgrade-button";
import { ManageBillingButton } from "@/components/manage-billing-button";
import { auth, clerkClient } from "@clerk/nextjs/server";

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
        <main className="min-h-[100dvh] bg-zinc-950 text-white px-6 py-12">
            <div className="max-w-lg mx-auto space-y-8">
                <div>
                    <h1 className="text-2xl font-bold">Billing</h1>
                    <p className="text-zinc-400 text-sm mt-1">
                        Manage your subscription and payment method.
                    </p>
                </div>

                {hasSubscription ? (
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                        <p className="text-sm text-zinc-300">
                            You have an active subscription. Use the Customer Portal to update your
                            payment method, view invoices, or cancel.
                        </p>
                        <ManageBillingButton />
                    </div>
                ) : (
                    <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-6 space-y-4">
                        <div>
                            <div className="text-xs font-mono uppercase tracking-widest text-emerald-400 mb-1">
                                Pro
                            </div>
                            <div className="flex items-baseline gap-0.5">
                                <span className="text-2xl font-black text-white">$14.99</span>
                                <span className="text-zinc-500 text-sm">/mo</span>
                            </div>
                        </div>
                        <ul className="space-y-2 text-sm text-zinc-400">
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Full 6-axis Pundit Credit Score
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Complete prediction history
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Bulk CSV export
                            </li>
                        </ul>
                        <UpgradeButton plan="pro" />
                        <p className="text-xs text-zinc-600 text-center">
                            Need API access?{" "}
                            <Link href="/pricing" className="underline hover:text-zinc-400">
                                View all plans
                            </Link>
                        </p>
                    </div>
                )}
            </div>
        </main>
    );
}
