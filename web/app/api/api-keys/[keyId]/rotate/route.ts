// TODO: Wire to real backend (#142)
// Stub POST route for rotating API keys (revoke old + create new)

import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import crypto from "crypto";

function generateKeyId(): string {
    return "key_" + crypto.randomBytes(12).toString("hex");
}

function generatePlaintextKey(mode: "live" | "test"): string {
    const prefix = mode === "live" ? "capk_live_" : "capk_test_";
    return prefix + crypto.randomBytes(24).toString("hex");
}

export async function POST(
    _req: Request,
    { params }: { params: { keyId: string } }
) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // In stub mode, generate a new key with a mock name
    // The real backend (#142) will look up the old key's name and mode
    const { keyId: _oldKeyId } = params;
    const newKeyId = generateKeyId();
    const mode = "live" as const; // stub default
    const plaintextKey = generatePlaintextKey(mode);
    const lastFour = plaintextKey.slice(-4);
    const createdAt = new Date().toISOString();
    const name = "Rotated Key"; // stub — real backend inherits old key's name

    return NextResponse.json({
        keyId: newKeyId,
        plaintextKey,
        lastFour,
        name,
        createdAt,
    });
}
