// TODO: Wire to real backend (#142)
// Stub API routes returning mock data for development

import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import crypto from "crypto";

// In-memory store for development — replaced by DB in #142
const keyStore = new Map<
    string,
    {
        keyId: string;
        name: string;
        lastFour: string;
        status: "active" | "revoked";
        mode: "live" | "test";
        createdAt: string;
        lastUsedAt: string | null;
    }[]
>();

function generateKeyId(): string {
    return "key_" + crypto.randomBytes(12).toString("hex");
}

function generatePlaintextKey(mode: "live" | "test"): string {
    const prefix = mode === "live" ? "capk_live_" : "capk_test_";
    return prefix + crypto.randomBytes(24).toString("hex");
}

// Per-tier key caps
const TIER_CAPS: Record<string, number> = {
    free: 1,
    pro: 3,
    api: 10,
    enterprise: 25,
};

function getUserTier(_userId: string): string {
    // TODO: Resolve from Stripe subscription (#142)
    return "free";
}

export async function GET() {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const tier = getUserTier(userId);
    const maxKeys = TIER_CAPS[tier] ?? 1;
    const userKeys = (keyStore.get(userId) ?? []).filter(
        (k) => k.status === "active"
    );

    return NextResponse.json({
        keys: keyStore.get(userId) ?? [],
        tier,
        maxKeys,
    });
}

export async function POST(req: Request) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();
    const name: string = body.name;
    const mode: "live" | "test" = body.mode ?? "live";

    if (!name || typeof name !== "string" || name.trim().length === 0) {
        return NextResponse.json(
            { error: "Key name is required" },
            { status: 400 }
        );
    }

    const tier = getUserTier(userId);
    const maxKeys = TIER_CAPS[tier] ?? 1;
    const existing = (keyStore.get(userId) ?? []).filter(
        (k) => k.status === "active"
    );

    if (existing.length >= maxKeys) {
        return NextResponse.json(
            {
                error: `Key limit reached. ${tier} tier allows ${maxKeys} active key(s).`,
            },
            { status: 403 }
        );
    }

    const keyId = generateKeyId();
    const plaintextKey = generatePlaintextKey(mode);
    const lastFour = plaintextKey.slice(-4);
    const createdAt = new Date().toISOString();

    const newKey = {
        keyId,
        name: name.trim(),
        lastFour,
        status: "active" as const,
        mode,
        createdAt,
        lastUsedAt: null,
    };

    const userKeys = keyStore.get(userId) ?? [];
    userKeys.push(newKey);
    keyStore.set(userId, userKeys);

    return NextResponse.json({
        keyId,
        plaintextKey,
        lastFour,
        name: newKey.name,
        mode,
        createdAt,
    });
}
