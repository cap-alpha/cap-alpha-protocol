import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";

export const metadata = {
    title: "Account | Pundit Ledger",
    description: "Your usage, tier, and API settings.",
};

/**
 * /account — auth-gated entry point.
 * Redirects signed-in users to the usage dashboard.
 * Unauthenticated users are sent to sign-in.
 */
export default async function AccountPage() {
    const { userId } = auth();

    if (!userId) {
        redirect("/sign-in");
    }

    redirect("/dashboard/usage");
}
