// TODO: Wire to real backend (#142)
// Stub DELETE route for revoking API keys

import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Shared in-memory store — in production this is the DB
// For the stub, we import indirectly by re-reading from the parent route's store.
// Since Next.js API routes are isolated, we use a simple module-level map here too.
// The real implementation (#142) will use the DB so this duplication won't matter.

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

export async function DELETE(
    _req: Request,
    { params }: { params: { keyId: string } }
) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { keyId } = params;
    const userKeys = keyStore.get(userId) ?? [];
    const keyIndex = userKeys.findIndex(
        (k) => k.keyId === keyId && k.status === "active"
    );

    if (keyIndex === -1) {
        // In stub mode, just return success since the real backend handles this
        return NextResponse.json({ success: true });
    }

    userKeys[keyIndex].status = "revoked";
    keyStore.set(userId, userKeys);

    return NextResponse.json({ success: true });
}
