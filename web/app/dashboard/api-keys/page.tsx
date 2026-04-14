import { ApiKeysDashboard } from "@/components/api-keys-dashboard";

export const metadata = {
    title: "API Keys | Pundit Ledger",
    description: "Create, manage, and rotate your Pundit Ledger API keys.",
};

export default function ApiKeysPage() {
    return <ApiKeysDashboard />;
}
