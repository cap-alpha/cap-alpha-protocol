import { auth, clerkClient } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent";

export async function POST(req: Request) {
    const { userId } = await auth();

    if (!userId) {
        return new NextResponse("Unauthorized", { status: 401 });
    }

    try {
        const body = await req.json();
        const { tradeProposal } = body;

        if (!tradeProposal) {
            return new NextResponse("Missing trade proposal", { status: 400 });
        }

        // --- CREDIT CHECK & DEDUCTION ---
        const client = clerkClient;
        const user = await client.users.getUser(userId);
        const credits = (user.publicMetadata.credits as number) || 0;

        if (credits < 1) {
            return new NextResponse("Insufficient Credits. Please upgrade or refill.", { status: 402 });
        }

        // Deduct 1 Credit
        await client.users.updateUserMetadata(userId, {
            publicMetadata: {
                credits: credits - 1
            }
        });

        console.log(`[AI-REPORT] Deducted 1 credit for user ${userId}. New Balance: ${credits - 1}`);

        // Construct Prompt
        const prompt = `
        You are a seasoned NFL General Manager and Scout. Analyze this trade proposal:
        
        Team A: ${tradeProposal.team_a} sends: ${JSON.stringify(tradeProposal.team_a_assets)}
        Team B: ${tradeProposal.team_b} sends: ${JSON.stringify(tradeProposal.team_b_assets)}

        Provide a "War Room Intelligence Report" with the following sections:
        1. **Owner's Reaction** (Team A's Owner): A short, visceral reaction to the deal.
        2. **Locker Room Impact**: How the players will react.
        3. **Hidden Upside/Risk**: One key insight the public misses.
        
        Keep it punchy, professional but insider-y. Max 300 words.
        `;

        if (!GEMINI_API_KEY) {
            // Mock response if no key (Dev mode fallback)
            console.warn("[WARN] No GEMINI_API_KEY found. Returning mock response.");
            return NextResponse.json({
                report: "## MOCK REPORT (Dev Mode)\n\n**Owner's Reaction**: 'We got him for WHAT?!' - The owner is dancing on the table.\n\n**Locker Room**: The veterans are skeptical, but the rookies are excited.\n\n**Hidden Upside**: This clears $15M in cap space for next year's free agency class."
            });
        }

        // Call Gemini API
        const response = await fetch(`${GEMINI_URL}?key=${GEMINI_API_KEY}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }]
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error("Gemini API Error:", errorText);

            // Refund the credit on failure
            await client.users.updateUserMetadata(userId, {
                publicMetadata: { credits: credits } // Restore original
            });

            return new NextResponse("AI Service Unavailable", { status: 502 });
        }

        const data = await response.json();
        const generatedText = data.candidates?.[0]?.content?.parts?.[0]?.text || "No analysis generated.";

        return NextResponse.json({ report: generatedText });

    } catch (error) {
        console.error("[AI_REPORT_ERROR]", error);
        return new NextResponse("Internal Error", { status: 500 });
    }
}
