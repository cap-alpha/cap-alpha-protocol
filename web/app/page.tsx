import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { LandingHero } from "@/components/landing-hero";
import { getProofOfAlpha } from "./actions/proof-of-alpha";

export default async function LandingPage() {
    const { userId } = await auth();

    // Bypass logic: if user is authenticated, send them to dashboard
    if (userId) {
        redirect("/dashboard");
    }

    const receipts = await getProofOfAlpha();

    return <LandingHero receipts={receipts} />;
}
