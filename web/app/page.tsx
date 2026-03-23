import { auth } from "@clerk/nextjs/server";
import { PersonaShowcase } from "@/components/persona-showcase";
import { AlphaFeedHero } from "@/components/alpha-feed-hero";
import { ProofOfAlphaCarousel } from "@/components/proof-of-alpha-carousel";
import type { Receipt } from "@/components/proof-of-alpha-carousel";
import { GlobalAggregator } from "@/components/global-aggregator";
import { getWarRoomData } from "@/app/actions";

export const revalidate = 3600; // Cache for 1 hour (ISR)

export default async function LandingPage() {
    const { userId } = await auth();
    const warRoomData = await getWarRoomData();
    
    // Map Top Performers to actionable "Receipts" dynamically
    const realReceipts: Receipt[] = warRoomData.roiMetrics.topPerformers.map((p, idx) => ({
        id: `live-${idx}`,
        date: p.year,
        player_name: p.player_name,
        team: "NFL", // Defaulting to NFL if team is omitted in this specific summary view
        prediction: `CRITICAL SELL (Lead: ${p.lead_time}W)`,
        outcome: p.rationale,
        roi: "-100%", // Displaying a stylized "total loss avoided" metric
        pitch: `Alpha Protocol identified impending asset degradation ${p.lead_time} weeks prior to mainstream consensus.`,
        trend: 'down'
    }));

    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* 1. The "Alpha Feed" Hero (Above the Fold) */}
            <AlphaFeedHero />
            
            {/* 2. Historical Proof of Alpha (The "Receipts") */}
            <section className="w-full relative py-20 bg-black">
                <div className="max-w-[1400px] mx-auto px-6">
                    <ProofOfAlphaCarousel receipts={realReceipts} />
                </div>
            </section>

            {/* 3. The Global Aggregator */}
            <GlobalAggregator />
            
            {/* 4. Persona Entry Points */}
            <PersonaShowcase />
        </div>
    );
}
