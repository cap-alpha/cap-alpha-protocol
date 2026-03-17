import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export async function POST(req: Request) {
    try {
        const { userId } = await auth();
        // Fallback to anonymous voting if unauthenticated (freemium engagement)
        const voterId = userId || "anonymous_fan";

        const body = await req.json();
        const { playerId, direction, timestamp } = body;

        if (!playerId || !direction) {
            return NextResponse.json({ error: "Missing parameters" }, { status: 400 });
        }

        /**
         * MotherDuck Ingestion Logic (SP10-5)
         * In a production deployment, bypassing direct DB writes from Serverless 
         * and pushing to Kafka/Upstash Redis before batch sinking to MotherDuck is standard.
         * For this phase, we mock the successful write to the Consensus Engine.
         */
        
        console.log(`[Consensus Engine] Logged Vote: ${voterId} -> ${direction} on ${playerId} @ ${timestamp}`);

        return NextResponse.json({ 
            success: true, 
            status: "LOGGED_TO_LAKE",
            credits_awarded: 50
        });
    } catch (e) {
        console.error(e);
        return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }
}
