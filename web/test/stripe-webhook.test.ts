/**
 * Unit tests for POST /api/webhooks/stripe
 *
 * Covers:
 *   - Signature verification failure → 400
 *   - Missing STRIPE_WEBHOOK_SECRET → 500
 *   - checkout.session.completed → Postgres + Clerk tier update
 *   - customer.subscription.updated → Postgres + Clerk tier update
 *   - customer.subscription.deleted → free tier
 *   - invoice.payment_failed → past_due (no downgrade)
 *   - invoice.payment_succeeded → active restore
 *   - Idempotency: 5 replays of same checkout event → exactly 1 DB update per call
 *   - Unrecognised event type → 200 (no-op)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --------------------------------------------------------------------------
// Module mocks — declared before any imports that pull in the modules
// --------------------------------------------------------------------------

// Mock @/lib/stripe to avoid instantiating the real Stripe singleton
const mockConstructEvent = vi.fn();
const mockSubscriptionsRetrieve = vi.fn();

vi.mock("@/lib/stripe", () => ({
    stripe: {
        webhooks: { constructEvent: mockConstructEvent },
        subscriptions: { retrieve: mockSubscriptionsRetrieve },
    },
    tierFromPriceId: vi.fn().mockReturnValue("pro"),
}));

// Mock Drizzle db
const mockDbUpdate = vi.fn();
const mockDbSelect = vi.fn();

vi.mock("@/db", () => ({
    db: {
        update: mockDbUpdate,
        select: mockDbSelect,
    },
}));

// Mock Clerk
const mockUpdateUserMetadata = vi.fn();

vi.mock("@clerk/nextjs/server", () => ({
    clerkClient: {
        users: {
            updateUserMetadata: mockUpdateUserMetadata,
        },
    },
}));

// Mock BigQuery (fire-and-forget audit log)
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

function makeEvent(type: string, data: object): object {
    return {
        id: `evt_test_${type.replace(/\./g, "_")}`,
        type,
        livemode: false,
        data: { object: data },
    };
}

function makeRequest(body: string, sig: string | null = "t=1,v1=abc"): Request {
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

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("POST /api/webhooks/stripe", () => {
    let POST: (req: Request) => Promise<Response>;

    beforeEach(async () => {
        vi.clearAllMocks();
        process.env.STRIPE_WEBHOOK_SECRET = "whsec_test";
        process.env.STRIPE_SECRET_KEY = "sk_test_xxx";
        process.env.GCP_PROJECT_ID = "cap-alpha-protocol";

        const mod = await import("@/app/api/webhooks/stripe/route");
        POST = mod.POST;
    });

    afterEach(() => {
        vi.resetModules();
    });

    // -----------------------------------------------------------------------
    // Config guard
    // -----------------------------------------------------------------------

    it("returns 500 when STRIPE_WEBHOOK_SECRET is missing", async () => {
        delete process.env.STRIPE_WEBHOOK_SECRET;
        const res = await POST(makeRequest("{}"));
        expect(res.status).toBe(500);
    });

    // -----------------------------------------------------------------------
    // Signature verification
    // -----------------------------------------------------------------------

    it("returns 400 when stripe-signature header is absent", async () => {
        const res = await POST(makeRequest("{}", null));
        expect(res.status).toBe(400);
    });

    it("returns 400 when Stripe signature verification throws", async () => {
        mockConstructEvent.mockImplementation(() => {
            throw new Error("Signature verification failed");
        });
        const res = await POST(makeRequest("{}", "t=1,v1=bad"));
        expect(res.status).toBe(400);
    });

    // -----------------------------------------------------------------------
    // checkout.session.completed
    // -----------------------------------------------------------------------

    it("checkout.session.completed → grants PRO tier", async () => {
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
        setupDbUpdateChain();

        const res = await POST(makeRequest(JSON.stringify(sessionObj)));

        expect(res.status).toBe(200);
        expect(mockDbUpdate).toHaveBeenCalledTimes(1);
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: "pro" },
        });
    });

    it("checkout.session.completed with no client_reference_id → 200, no Clerk call", async () => {
        const sessionObj = { mode: "subscription", customer: "cus_abc", subscription: "sub_xyz" };
        mockConstructEvent.mockReturnValue(makeEvent("checkout.session.completed", sessionObj));
        mockSubscriptionsRetrieve.mockResolvedValue({
            items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
        });

        const res = await POST(makeRequest(JSON.stringify(sessionObj)));

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
    });

    it("checkout.session.completed non-subscription mode → 200, no DB update", async () => {
        const sessionObj = { mode: "payment", client_reference_id: "user_clerk123" };
        mockConstructEvent.mockReturnValue(makeEvent("checkout.session.completed", sessionObj));

        const res = await POST(makeRequest(JSON.stringify(sessionObj)));

        expect(res.status).toBe(200);
        expect(mockDbUpdate).not.toHaveBeenCalled();
    });

    // -----------------------------------------------------------------------
    // Idempotency — 5 identical replays each process independently
    // The handler itself is stateless; Stripe's delivery guarantee is at-least-once.
    // Each invocation must complete successfully without cross-call contamination.
    // -----------------------------------------------------------------------

    it("idempotency: 5 replay calls each succeed with exactly 1 DB update", async () => {
        const sessionObj = {
            mode: "subscription",
            client_reference_id: "user_idempotent",
            customer: "cus_idempotent",
            subscription: "sub_idempotent",
        };
        const event = makeEvent("checkout.session.completed", sessionObj);

        for (let i = 0; i < 5; i++) {
            vi.clearAllMocks();
            mockConstructEvent.mockReturnValue(event);
            mockSubscriptionsRetrieve.mockResolvedValue({
                items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
            });
            setupDbUpdateChain();

            const res = await POST(makeRequest(JSON.stringify(sessionObj)));
            expect(res.status, `replay ${i + 1} should be 200`).toBe(200);
            expect(mockDbUpdate, `replay ${i + 1} should write DB exactly once`).toHaveBeenCalledTimes(1);
        }
    });

    // -----------------------------------------------------------------------
    // customer.subscription.updated
    // -----------------------------------------------------------------------

    it("customer.subscription.updated → updates tier and status", async () => {
        const subObj = {
            customer: "cus_abc",
            status: "active",
            items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
        };
        mockConstructEvent.mockReturnValue(makeEvent("customer.subscription.updated", subObj));
        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        setupDbUpdateChain();

        const res = await POST(makeRequest(JSON.stringify(subObj)));

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: "pro" },
        });
    });

    it("subscription.updated with unknown customer → 200, no Clerk call", async () => {
        const subObj = {
            customer: "cus_unknown",
            status: "active",
            items: { data: [{ price: { id: "price_pro" }, current_period_end: 9999999999 }] },
        };
        mockConstructEvent.mockReturnValue(makeEvent("customer.subscription.updated", subObj));
        setupDbSelectChain([]);

        const res = await POST(makeRequest(JSON.stringify(subObj)));

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
    });

    // -----------------------------------------------------------------------
    // customer.subscription.deleted
    // -----------------------------------------------------------------------

    it("customer.subscription.deleted → free tier + isPro=false", async () => {
        const subObj = { customer: "cus_abc" };
        mockConstructEvent.mockReturnValue(makeEvent("customer.subscription.deleted", subObj));
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
    // invoice.payment_failed
    // -----------------------------------------------------------------------

    it("invoice.payment_failed → sets past_due, does NOT touch tier", async () => {
        const invoiceObj = { customer: "cus_abc" };
        mockConstructEvent.mockReturnValue(makeEvent("invoice.payment_failed", invoiceObj));
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
    // invoice.payment_succeeded
    // -----------------------------------------------------------------------

    it("invoice.payment_succeeded → restores active + isPro=true", async () => {
        const invoiceObj = { customer: "cus_abc" };
        mockConstructEvent.mockReturnValue(makeEvent("invoice.payment_succeeded", invoiceObj));
        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        const updateChain = setupDbUpdateChain();

        const res = await POST(makeRequest(JSON.stringify(invoiceObj)));

        expect(res.status).toBe(200);
        expect(updateChain.set).toHaveBeenCalledWith(
            expect.objectContaining({ stripeSubscriptionStatus: "active", isPro: true })
        );
    });

    // -----------------------------------------------------------------------
    // Unknown event type
    // -----------------------------------------------------------------------

    it("returns 200 for unrecognised event types (no-op)", async () => {
        mockConstructEvent.mockReturnValue(makeEvent("payment_intent.created", { id: "pi_test" }));

        const res = await POST(makeRequest("{}"));

        expect(res.status).toBe(200);
        expect(mockDbUpdate).not.toHaveBeenCalled();
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
    });
});
