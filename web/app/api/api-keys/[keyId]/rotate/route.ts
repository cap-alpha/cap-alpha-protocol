/**
 * POST /api/api-keys/[keyId]/rotate — Rotate an API key
 *
 * Revokes the existing key and creates a new one with the same name.
 * The new key gets a fresh key_id. Returns the new plaintext key exactly once.
 *
 * Requires Clerk authentication. User must own the key.
 */
import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import { rotateKey } from "@/lib/api-keys/repository";

export async function POST(
    _req: Request,
    { params }: { params: { keyId: string } }
) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { keyId } = params;
    if (!keyId) {
        return NextResponse.json(
            { error: "Key ID is required" },
            { status: 400 }
        );
    }

    try {
        const result = await rotateKey(userId, keyId);
        return NextResponse.json(result, { status: 201 });
    } catch (err: any) {
        if (err.message?.includes("not found")) {
            return NextResponse.json(
                { error: err.message },
                { status: 404 }
            );
        }
        console.error("[API Keys] Rotate error:", err);
        return NextResponse.json(
            { error: "Failed to rotate API key" },
            { status: 500 }
        );
    }
}
