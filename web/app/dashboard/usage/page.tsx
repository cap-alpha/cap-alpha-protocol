import { UsageDashboard } from "@/components/usage-dashboard";

export const metadata = {
    title: "Usage Dashboard | Pundit Ledger",
    description: "Monitor your API usage, quotas, and rate limits.",
};

export default function UsagePage() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">
                    Usage Dashboard
                </h1>
                <p className="text-gray-600 mt-1">
                    Monitor your API consumption and upgrade when ready.
                </p>
            </div>
            <UsageDashboard />
        </div>
    );
}
