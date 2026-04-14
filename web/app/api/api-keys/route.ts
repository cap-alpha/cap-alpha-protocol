/**
 * POST /api/api-keys — Create a new API key
 * GET  /api/api-keys — List user's keys
 *
 * Both require Clerk authentication.
 */
import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import { createKey, listKeys } from "@/lib/api-keys/repository";
import type { KeyMode } from "@/lib/api-keys/index";

export async function POST(req: Request) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    let body: { name?: string; mode?: string };
    try {
        body = await req.json();
    } catch {
        return NextResponse.json(
            { error: "Invalid JSON body" },
            { status: 400 }
        );
    }

    const name = body.name?.trim();
    if (!name || name.length === 0) {
        return NextResponse.json(
            { error: "Key name is required" },
            { status: 400 }
        );
    }

    if (name.length > 64) {
        return NextResponse.json(
            { error: "Key name must be 64 characters or fewer" },
            { status: 400 }
        );
    }

    const mode: KeyMode =
        body.mode === "test" || body.mode === "live" ? body.mode : "live";

    try {
        const result = await createKey(userId, name, mode);
        return NextResponse.json(result, { status: 201 });
    } catch (err: any) {
        // Tier cap errors are user-facing
        if (err.message?.includes("Key limit reached")) {
            return NextResponse.json(
                { error: err.message },
                { status: 403 }
            );
        }
        console.error("[API Keys] Create error:", err);
        return NextResponse.json(
            { error: "Failed to create API key" },
            { status: 500 }
        );
    }
}

export async function GET() {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    try {
        const keys = await listKeys(userId);
        return NextResponse.json({ keys });
    } catch (err) {
        console.error("[API Keys] List error:", err);
        return NextResponse.json(
            { error: "Failed to list API keys" },
            { status: 500 }
        );
    }
}
