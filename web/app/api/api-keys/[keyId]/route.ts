/**
 * DELETE /api/api-keys/[keyId] — Revoke an API key
 *
 * Requires Clerk authentication. User must own the key.
 */
import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import { revokeKey } from "@/lib/api-keys/repository";

export async function DELETE(
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
        await revokeKey(userId, keyId);
        return NextResponse.json({ success: true, keyId });
    } catch (err: any) {
        if (err.message?.includes("not found")) {
            return NextResponse.json(
                { error: err.message },
                { status: 404 }
            );
        }
        console.error("[API Keys] Revoke error:", err);
        return NextResponse.json(
            { error: "Failed to revoke API key" },
            { status: 500 }
        );
    }
}
