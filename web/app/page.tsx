import { auth } from "@clerk/nextjs/server";
import { PersonaShowcase } from "@/components/persona-showcase";
import { AlphaFeedHero } from "@/components/alpha-feed-hero";
import { ProofOfAlphaCarousel } from "@/components/proof-of-alpha-carousel";
import { GlobalAggregator } from "@/components/global-aggregator";

export default async function LandingPage() {
    const { userId } = await auth();

    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* 1. The "Alpha Feed" Hero (Above the Fold) */}
            <AlphaFeedHero />
            
            {/* 2. Historical Proof of Alpha (The "Receipts") */}
            <section className="w-full relative py-20 bg-black">
                <div className="max-w-[1400px] mx-auto px-6">
                    <ProofOfAlphaCarousel />
                </div>
            </section>

            {/* 3. The Global Aggregator */}
            <GlobalAggregator />
            
            {/* 4. Persona Entry Points */}
            <PersonaShowcase />
        </div>
    );
}
