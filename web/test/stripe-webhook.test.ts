/**
 * Unit tests for POST /api/webhooks/stripe
 *
 * These tests exercise the webhook handler in isolation using mocked
 * Stripe SDK, Drizzle ORM, and Clerk client. The key coverage goals are:
 *   - Signature verification failure → 400
 *   - Missing STRIPE_WEBHOOK_SECRET → 500
 *   - checkout.session.completed → Postgres + Clerk tier update
 *   - customer.subscription.updated → Postgres + Clerk tier update
 *   - customer.subscription.deleted → free tier
 *   - invoice.payment_failed → past_due (no downgrade)
 *   - invoice.payment_succeeded → active restore
 *   - Unrecognised event type → 200 (no-op)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --------------------------------------------------------------------------
// Module mocks — must be declared before any imports that pull in the modules
// --------------------------------------------------------------------------

// Mock Stripe
const mockConstructEvent = vi.fn();
const mockSubscriptionsRetrieve = vi.fn();

vi.mock("stripe", () => {
    const Stripe: any = vi.fn().mockImplementation(() => ({
        webhooks: {
            constructEvent: mockConstructEvent,
        },
        subscriptions: {
            retrieve: mockSubscriptionsRetrieve,
        },
    }));
    return { default: Stripe };
});

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
const mockGetUser = vi.fn();

vi.mock("@clerk/nextjs/server", () => ({
    clerkClient: {
        users: {
            updateUserMetadata: mockUpdateUserMetadata,
            getUser: mockGetUser,
        },
    },
}));

// Mock BigQuery (fire-and-forget audit log)
vi.mock("@google-cloud/bigquery", () => ({
    BigQuery: vi.fn().mockImplementation(() => ({
        dataset: vi.fn().mockReturnValue({
            table: vi.fn().mockReturnValue({
                insert: vi.fn().mockResolvedValue(undefined),
            }),
        }),
    })),
}));

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

/**
 * Build a minimal mock Stripe event.
 */
function makeEvent(type: string, data: object): object {
    return {
        id: `evt_test_${type.replace(/\./g, "_")}`,
        type,
        livemode: false,
        data: { object: data },
    };
}

/**
 * Build a Next.js Request-like object with the given body and optional
 * stripe-signature header.
 */
function makeRequest(body: string, sig: string | null = "t=1,v1=abc"): Request {
    const headers: Record<string, string> = { "Content-Type": "text/plain" };
    if (sig !== null) headers["stripe-signature"] = sig;
    return new Request("http://localhost/api/webhooks/stripe", {
        method: "POST",
        headers,
        body,
    });
}

// --------------------------------------------------------------------------
// Setup a chainable Drizzle update mock
// --------------------------------------------------------------------------

function setupDbUpdateChain(): void {
    const chain = {
        set: vi.fn().mockReturnThis(),
        where: vi.fn().mockResolvedValue(undefined),
    };
    mockDbUpdate.mockReturnValue(chain);
}

function setupDbSelectChain(rows: object[]): void {
    const chain = {
        from: vi.fn().mockReturnThis(),
        where: vi.fn().mockReturnThis(),
        limit: vi.fn().mockResolvedValue(rows),
    };
    mockDbSelect.mockReturnValue(chain);
}

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("POST /api/webhooks/stripe", () => {
    // We import the route handler lazily inside each test so vi.mock hoisting
    // has taken effect. We store the imported POST function here.
    let POST: (req: Request) => Promise<Response>;

    beforeEach(async () => {
        vi.clearAllMocks();
        // Reset env
        process.env.STRIPE_WEBHOOK_SECRET = "whsec_test";
        process.env.STRIPE_SECRET_KEY = "sk_test_xxx";
        process.env.GCP_PROJECT_ID = "cap-alpha-protocol";

        // Default: import the route handler
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

        const req = makeRequest("{}");
        const res = await POST(req);

        expect(res.status).toBe(500);
    });

    // -----------------------------------------------------------------------
    // Signature verification
    // -----------------------------------------------------------------------

    it("returns 400 when stripe-signature header is absent", async () => {
        const req = makeRequest("{}", null);
        const res = await POST(req);

        expect(res.status).toBe(400);
    });

    it("returns 400 when Stripe signature verification fails", async () => {
        mockConstructEvent.mockImplementation(() => {
            throw new Error("Signature verification failed");
        });

        const req = makeRequest("{}", "t=1,v1=bad");
        const res = await POST(req);

        expect(res.status).toBe(400);
    });

    // -----------------------------------------------------------------------
    // checkout.session.completed
    // -----------------------------------------------------------------------

    it("handles checkout.session.completed → PRO tier", async () => {
        const sessionObj = {
            client_reference_id: "user_clerk123",
            customer: "cus_abc",
            subscription: "sub_xyz",
        };
        const event = makeEvent("checkout.session.completed", sessionObj);
        mockConstructEvent.mockReturnValue(event);

        mockSubscriptionsRetrieve.mockResolvedValue({
            items: { data: [{ price: { id: process.env.STRIPE_PRICE_PRO ?? "price_pro" } }] },
            current_period_end: Math.floor(Date.now() / 1000) + 2592000,
        });

        setupDbUpdateChain();

        const req = makeRequest(JSON.stringify(sessionObj));
        const res = await POST(req);

        expect(res.status).toBe(200);
        expect(mockDbUpdate).toHaveBeenCalled();
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: expect.any(String) },
        });
    });

    it("handles checkout.session.completed with no client_reference_id gracefully", async () => {
        const sessionObj = { customer: "cus_abc", subscription: "sub_xyz" };
        const event = makeEvent("checkout.session.completed", sessionObj);
        mockConstructEvent.mockReturnValue(event);

        const req = makeRequest(JSON.stringify(sessionObj));
        const res = await POST(req);

        // No Clerk call since we couldn't identify the user
        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
    });

    // -----------------------------------------------------------------------
    // customer.subscription.updated
    // -----------------------------------------------------------------------

    it("handles customer.subscription.updated → updates tier and status", async () => {
        const subObj = {
            customer: "cus_abc",
            status: "active",
            items: { data: [{ price: { id: "price_pro" } }] },
            current_period_end: Math.floor(Date.now() / 1000) + 2592000,
        };
        const event = makeEvent("customer.subscription.updated", subObj);
        mockConstructEvent.mockReturnValue(event);

        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        setupDbUpdateChain();

        const req = makeRequest(JSON.stringify(subObj));
        const res = await POST(req);

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: expect.any(String) },
        });
    });

    it("handles customer.subscription.updated with unknown customer gracefully", async () => {
        const subObj = {
            customer: "cus_unknown",
            status: "active",
            items: { data: [{ price: { id: "price_pro" } }] },
            current_period_end: Math.floor(Date.now() / 1000) + 2592000,
        };
        const event = makeEvent("customer.subscription.updated", subObj);
        mockConstructEvent.mockReturnValue(event);

        setupDbSelectChain([]); // no rows → unknown customer

        const req = makeRequest(JSON.stringify(subObj));
        const res = await POST(req);

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
    });

    // -----------------------------------------------------------------------
    // customer.subscription.deleted
    // -----------------------------------------------------------------------

    it("handles customer.subscription.deleted → free tier", async () => {
        const subObj = { customer: "cus_abc" };
        const event = makeEvent("customer.subscription.deleted", subObj);
        mockConstructEvent.mockReturnValue(event);

        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        setupDbUpdateChain();

        const req = makeRequest(JSON.stringify(subObj));
        const res = await POST(req);

        expect(res.status).toBe(200);
        expect(mockUpdateUserMetadata).toHaveBeenCalledWith("user_clerk123", {
            publicMetadata: { tier: "free" },
        });
    });

    // -----------------------------------------------------------------------
    // invoice.payment_failed
    // -----------------------------------------------------------------------

    it("handles invoice.payment_failed → sets past_due, does NOT downgrade tier", async () => {
        const invoiceObj = { customer: "cus_abc" };
        const event = makeEvent("invoice.payment_failed", invoiceObj);
        mockConstructEvent.mockReturnValue(event);

        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        const updateChain = {
            set: vi.fn().mockReturnThis(),
            where: vi.fn().mockResolvedValue(undefined),
        };
        mockDbUpdate.mockReturnValue(updateChain);

        const req = makeRequest(JSON.stringify(invoiceObj));
        const res = await POST(req);

        expect(res.status).toBe(200);
        // Tier NOT changed — only status updated to past_due
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
        expect(updateChain.set).toHaveBeenCalledWith(
            expect.objectContaining({ stripeSubscriptionStatus: "past_due" })
        );
    });

    // -----------------------------------------------------------------------
    // invoice.payment_succeeded
    // -----------------------------------------------------------------------

    it("handles invoice.payment_succeeded → restores active status", async () => {
        const invoiceObj = { customer: "cus_abc" };
        const event = makeEvent("invoice.payment_succeeded", invoiceObj);
        mockConstructEvent.mockReturnValue(event);

        setupDbSelectChain([{ clerkId: "user_clerk123" }]);
        const updateChain = {
            set: vi.fn().mockReturnThis(),
            where: vi.fn().mockResolvedValue(undefined),
        };
        mockDbUpdate.mockReturnValue(updateChain);

        const req = makeRequest(JSON.stringify(invoiceObj));
        const res = await POST(req);

        expect(res.status).toBe(200);
        expect(updateChain.set).toHaveBeenCalledWith(
            expect.objectContaining({ stripeSubscriptionStatus: "active", isPro: true })
        );
    });

    // -----------------------------------------------------------------------
    // Unknown event type
    // -----------------------------------------------------------------------

    it("returns 200 for unrecognised event types (no-op)", async () => {
        const event = makeEvent("payment_intent.created", { id: "pi_test" });
        mockConstructEvent.mockReturnValue(event);

        const req = makeRequest("{}");
        const res = await POST(req);

        expect(res.status).toBe(200);
        expect(mockDbUpdate).not.toHaveBeenCalled();
        expect(mockUpdateUserMetadata).not.toHaveBeenCalled();
    });
});
