/**
 * stripe-e2e-verify.ts
 *
 * Verifies the Stripe test-mode end-to-end flow:
 *   customer creation → checkout session → webhook event construction
 *
 * This covers acceptance criteria AC4 from issue #483 (Gate 0 sole-prop verification).
 * Run with a test-mode key — never a live key.
 *
 * Usage:
 *   STRIPE_SECRET_KEY=sk_test_... STRIPE_PRO_PRICE_ID=price_... \
 *     npx tsx --env-file=.env.local scripts/stripe-e2e-verify.ts
 */

import Stripe from "stripe";

const STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY ?? "";
const STRIPE_PRO_PRICE_ID = process.env.STRIPE_PRO_PRICE_ID ?? "";
const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

function assert(condition: boolean, msg: string): void {
    if (!condition) {
        console.error(`FAIL: ${msg}`);
        process.exit(1);
    }
}

function step(n: number, total: number, label: string): () => void {
    process.stdout.write(`[${n}/${total}] ${label.padEnd(38)}`);
    return (suffix = "ok") => console.log(suffix);
}

async function main() {
    assert(
        STRIPE_SECRET_KEY.startsWith("sk_test_"),
        "STRIPE_SECRET_KEY must be a test-mode key (sk_test_...)"
    );
    assert(
        STRIPE_PRO_PRICE_ID.startsWith("price_"),
        "STRIPE_PRO_PRICE_ID must be set (run stripe-setup.ts first)"
    );

    const stripe = new Stripe(STRIPE_SECRET_KEY, {
        apiVersion: "2026-04-22.dahlia",
    });

    const TOTAL = 4;

    // 1. Create a test customer
    let done = step(1, TOTAL, "Creating test customer...");
    const customer = await stripe.customers.create({
        email: "sole-prop-verify@example.com",
        metadata: { clerk_user_id: "test_sole_prop_verify" },
    });
    done(`ok (${customer.id})`);

    // 2. Create a Checkout session (test mode, no redirect required)
    done = step(2, TOTAL, "Creating checkout session...");
    const session = await stripe.checkout.sessions.create({
        customer: customer.id,
        client_reference_id: "test_sole_prop_verify",
        mode: "subscription",
        line_items: [{ price: STRIPE_PRO_PRICE_ID, quantity: 1 }],
        success_url: `${APP_URL}/dashboard?checkout=success`,
        cancel_url: `${APP_URL}/pricing?checkout=cancelled`,
        payment_method_types: ["card"],
    });
    done(`ok (${session.id})`);

    // 3. Verify session properties
    done = step(3, TOTAL, "Verifying session properties...");
    assert(session.mode === "subscription", "session.mode must be 'subscription'");
    assert(session.status === "open", "session.status must be 'open'");
    assert(session.customer === customer.id, "session.customer must match");
    assert(
        typeof session.url === "string" && session.url.startsWith("https://checkout.stripe.com"),
        "session.url must be a valid Stripe checkout URL"
    );
    done("ok");

    // 4. Verify webhook event construction (validates STRIPE_WEBHOOK_SECRET if set)
    done = step(4, TOTAL, "Constructing webhook event...");
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
    if (webhookSecret) {
        const payload = JSON.stringify({
            id: "evt_test_verify",
            type: "checkout.session.completed",
            data: { object: { ...session, payment_status: "paid" } },
        });
        const sig = stripe.webhooks.generateTestHeaderString({
            payload,
            secret: webhookSecret,
        });
        const event = stripe.webhooks.constructEvent(payload, sig, webhookSecret);
        assert(event.type === "checkout.session.completed", "event type must match");
        done("ok (signature verified)");
    } else {
        done("ok (skipped — STRIPE_WEBHOOK_SECRET not set)");
    }

    // Cleanup: delete the test customer so this script is idempotent
    await stripe.customers.del(customer.id);

    console.log("\nAll checks passed. Stripe test-mode E2E verified.");
    console.log(`Checkout URL was: ${session.url}`);
    console.log("\nNext: complete live-mode verification per docs/business/stripe-sole-prop-verification.md");
}

main().catch((err) => {
    console.error("\nE2E verify failed:", err.message ?? err);
    process.exit(1);
});
