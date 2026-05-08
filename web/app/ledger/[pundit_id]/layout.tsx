import { Metadata } from "next";

export const metadata: Metadata = {
    title: "Pundit Accuracy Profile | Pundit Ledger",
    description:
        "Prediction accuracy independently audited by Cap Alpha. Full public record of claims, outcomes, and accountability — permanently on record.",
    openGraph: {
        description:
            "Prediction accuracy independently audited by Cap Alpha. Every public claim scored and permanently on record.",
    },
};

export default function PunditDetailLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <>{children}</>;
}
