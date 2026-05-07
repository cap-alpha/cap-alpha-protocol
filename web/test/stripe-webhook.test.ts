/**
 * Unit tests for POST /api/webhooks/stripe
 *
 * Covers:
 *   - Signature verification failure → 400
 *   - Missing STRIPE_WEBHOOK_SECRET → 500
 *   - checkout.session.completed → Postgres + Clerk tier update
 *   - customer.subscription.updated / deleted / invoice events
 *   - Replay attack: same event replayed 5× → 1 grant, 4 skips (idempotency)
 *   - Corrupted payload → 400 (signature fails)
 *   - Unrecognised event type → 200 (no-op)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --------------------------------------------------------------------------
// Module mocks
// --------------------------------------------------------------------------

const mockConstructEvent = vi.fn();
const mockSubscriptionsRetrieve = vi.fn();

vi.mock("@/lib/stripe", () => ({
    stripe: {
        webhooks: { constructEvent: mockConstructEvent },
        subscriptions: { retrieve: mockSubscriptionsRetrieve },
    },
    tierFromPriceId: vi.fn().mockReturnValue("pro"),
}));

const mockDbUpdate = vi.fn();
const mockDbSelect = vi.fn();
const mockDbInsert = vi.fn();

vi.mock("@/db", () => ({
    db: {
        update: mockDbUpdate,
        select: mockDbSelect,
        insert: mockDbInsert,
    },
}));

vi.mock("@clerk/nextjs/server", () => ({
    clerkClient: {
        users: { updateUserMetadata: vi.fn() },
    },
}));

vi.mock("@google-cloud/bigquery", () => ({
    BigQuery: vi.fn().mockImplementation(function () {
        return {
            dataset: vi.fn().mockReturnValue({
                table: vi.fn().mockReturnValue({
                    insert: vi.fn().mockResolvedValue(undefined),
                }),
            }),
        };
    }),
}));

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function makeEvent(type: string, data: object, id = `evt_${type.replace(/\W/g, "_")}`) {
    return { id, type, livemode: false, data: { object: data } };
}

function makeRequest(body: string, sig: string | null = "t=1,v1=ok"): Request {
    const headers: Record<string, string> = { "Content-Type": "text/plain" };
    if (sig !== null) headers["stripe-signature"] = sig;
    return new Request("http://localhost/api/webhooks/stripe", {
        method: "POST",
        headers,
        body,
    });
}

function setupDbUpdateChain() {
    const chain = {
        set: vi.fn().mockReturnThis(),
        where: vi.fn().mockResolvedValue(undefined),
    };
    mockDbUpdate.mockReturnValue(chain);
    return chain;
}

function setupDbSelectChain(rows: object[]) {
    const chain = {
        from: vi.fn().mockReturnThis(),
        where: vi.fn().mockReturnThis(),
        limit: vi.fn().mockResolvedValue(rows),
    };
    mockDbSelect.mockReturnValue(chain);
    return chain;
}

// Set up the idempotency insert mock. Pass `alreadyProcessed=true` to simulate replay.
function setupIdempotencyInsert(alreadyProcessed = false) {
    const chain = {
        values: vi.fn().mockReturnThis(),
        onConflictDoNothing: vi.fn().mockReturnThis(),
        returning: vi
            .fn()
            .mockResolvedValue(alreadyProcessed ? [] : [{ id: 1 }]),
    };
    mockDbInsert.mockReturnValue(chain);
    return chain;
}

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("POST /api/webhooks/stripe", () => {
    let POST: (req: Request) => Promise<Response>;
    let mockUpdateUserMetadata: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
        vi.clearAllMocks();
        process.env.STRIPE_WEBHOOK_SECRET = "whsec_test";
        process.env.STRIPE_SECRET_KEY = "sk_test";
        process.env.GCP_PROJECT_ID = "cap-alpha-protocol";

        const mod = await import("@/app/api/webhooks/stripe/route");
        POST = mod.POST;

        const clerk = await import("@clerk/nextjs/server");
        mockUpdateUserMetadata = clerk.clerkClient.users.updateUserMetadata as ReturnType<typeof vi.fn>;
    });

    afterEach(() => {
        vi.resetModules();
    });

    // -----------------------------------------------------------------------
    // Config / signature
    // -----------------------------------------------------------------------

    it("returns 500 when STRIPE_WEBHOOK_SECRET is missing", async () => {
        delete process.env.STRIPE_WEBHOOK_SECRET;
        const res = await POST(makeRequest("{}"));
        expect(res.status).toBe(500);
    });

    it("returns 400 when stripe-signature header is absent", async () => {
        const res = await POST(makeRequest("{}", null));
        expect(res.status).toBe(400);
    });

    it("returns 400 when signature verification throws (corrupted payload)", async () => {
        mockConstructEvent.mockImplementation(() => {
            throw new Error("Invalid signature");
        });
        const res = await POST(makeRequest("{corrupted}", "t=1,v1=bad"));
        expect(res.status).toBe(400);
    });

    // -----------------------------------------------------------------------
    // checkout.session.completed
    // -----------------------------------------------------------------------

    it("grants PRO tier on checkout.session.completed", async () => {
        const sessionObj = {
            mode: "subscription",
            client_reference_id: "user_clerk123",
            customer: "cus_abc",
            subscription: "sub_xyz",
        };
        mockConstructEvent.mockReturnValue(makeEvent("checkout.session.completed", sessionObj));
        mockSubscriptionsRetrieve.mockResolvedValue({
            items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
        });
        setupIdempotencyInsert(false);
        setupDbUpdateChain();

        const res = await POST(makeRequest(JSON.stringify(sessionObj)));

        expect(res.status).toBe(200);
        expect(mockDbUpdate).toHaveBeenCalledTimes(1);
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: "pro" },
        });
    });

    // -----------------------------------------------------------------------
    // Replay attack — idempotency
    // The first delivery inserts the event ID (returns row).
    // Subsequent replays get empty returning() → 200 with no state change.
    // -----------------------------------------------------------------------

    it("replay attack: 5 deliveries → 1 access grant, 4 skipped (idempotency)", async () => {
        const sessionObj = {
            mode: "subscription",
            client_reference_id: "user_replay_victim",
            customer: "cus_replay",
            subscription: "sub_replay",
        };
        const event = makeEvent("checkout.session.completed", sessionObj, "evt_replay_001");
        mockSubscriptionsRetrieve.mockResolvedValue({
            items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
        });

        let grantCount = 0;

        for (let i = 0; i < 5; i++) {
            vi.clearAllMocks();
            mockConstructEvent.mockReturnValue(event);
            mockSubscriptionsRetrieve.mockResolvedValue({
                items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
            });

            if (i === 0) {
                // First delivery: insert succeeds → process event
                setupIdempotencyInsert(false);
                setupDbUpdateChain();
            } else {
                // Subsequent replays: insert returns no rows → skip
                setupIdempotencyInsert(true);
            }

            const res = await POST(makeRequest(JSON.stringify(sessionObj)));
            expect(res.status, `delivery ${i + 1} should be 200`).toBe(200);

            if (mockDbUpdate.mock.calls.length > 0) {
                grantCount++;
            }
        }

        expect(grantCount).toBe(1);
    });

    // -----------------------------------------------------------------------
    // customer.subscription.deleted → free tier
    // -----------------------------------------------------------------------

    it("customer.subscription.deleted → free tier + isPro=false", async () => {
        const subObj = { customer: "cus_abc" };
        mockConstructEvent.mockReturnValue(makeEvent("customer.subscription.deleted", subObj));
        setupIdempotencyInsert(false);
        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        const updateChain = setupDbUpdateChain();

        const res = await POST(makeRequest(JSON.stringify(subObj)));

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: "free" },
        });
        expect(updateChain.set).toHaveBeenCalledWith(
            expect.objectContaining({ isPro: false, stripeSubscriptionStatus: "canceled" })
        );
    });

    // -----------------------------------------------------------------------
    // invoice.payment_failed → past_due only
    // -----------------------------------------------------------------------

    it("invoice.payment_failed → past_due, no tier change", async () => {
        const invoiceObj = { customer: "cus_abc" };
        mockConstructEvent.mockReturnValue(makeEvent("invoice.payment_failed", invoiceObj));
        setupIdempotencyInsert(false);
        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        const updateChain = setupDbUpdateChain();

        const res = await POST(makeRequest(JSON.stringify(invoiceObj)));

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
        expect(updateChain.set).toHaveBeenCalledWith(
            expect.objectContaining({ stripeSubscriptionStatus: "past_due" })
        );
    });

    // -----------------------------------------------------------------------
    // Unknown event type → 200 no-op
    // -----------------------------------------------------------------------

    it("returns 200 for unrecognised event types without touching DB state", async () => {
        mockConstructEvent.mockReturnValue(makeEvent("payment_intent.created", { id: "pi_test" }));
        setupIdempotencyInsert(false);

        const res = await POST(makeRequest("{}"));

        expect(res.status).toBe(200);
        // Only the idempotency insert should have been called, not the users table update
        expect(mockDbUpdate).not.toHaveBeenCalled();
    });
});
