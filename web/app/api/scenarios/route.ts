
import { db } from "@/db";
import { scenarios } from "@/db/schema";
import { auth } from "@clerk/nextjs/server";
import { eq, desc } from "drizzle-orm";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
    const { userId } = auth();

    if (!userId) {
        return new NextResponse("Unauthorized", { status: 401 });
    }

    try {
        const body = await req.json();
        const { name, description, rosterState } = body;

        if (!name || !rosterState) {
            return new NextResponse("Missing required fields", { status: 400 });
        }

        // Insert new scenario
        const [newScenario] = await db
            .insert(scenarios)
            .values({
                userId, // Clerk ID
                name,
                description,
                rosterState,
            })
            .returning();

        return NextResponse.json(newScenario);
    } catch (error) {
        console.error("[SCENARIOS_POST]", error);
        return new NextResponse("Internal Error", { status: 500 });
    }
}

export async function GET(req: Request) {
    const { userId } = auth();

    if (!userId) {
        return new NextResponse("Unauthorized", { status: 401 });
    }

    try {
        const userScenarios = await db
            .select()
            .from(scenarios)
            .where(eq(scenarios.userId, userId))
            .orderBy(desc(scenarios.createdAt));

        return NextResponse.json(userScenarios);
    } catch (error) {
        console.error("[SCENARIOS_GET]", error);
        return new NextResponse("Internal Error", { status: 500 });
    }
}
