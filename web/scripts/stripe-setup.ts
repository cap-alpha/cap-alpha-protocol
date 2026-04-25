/**
 * stripe-setup.ts
 *
 * Idempotent IaC script to create Stripe Products + Prices.
 * Run once (or whenever products need to be updated):
 *
 *   STRIPE_SECRET_KEY=sk_test_... npx tsx --env-file=.env.local scripts/stripe-setup.ts
 *
 * Outputs the price IDs you need for .env.local / Vercel env vars:
 *   STRIPE_PRO_PRICE_ID
 *   STRIPE_API_STARTER_PRICE_ID
 *   STRIPE_API_GROWTH_PRICE_ID
 */

import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: "2026-04-22.dahlia",
});

interface ProductSpec {
    key: string;
    name: string;
    description: string;
    unitAmount: number; // cents
    envVar: string;
}

const PRODUCTS: ProductSpec[] = [
    {
        key: "pro",
        name: "Pundit Ledger Pro",
        description:
            "Full 6-axis Pundit Credit Score, complete prediction history, magnitude tracking, multi-sport coverage, and bulk CSV export.",
        unitAmount: 1499, // $14.99/mo
        envVar: "STRIPE_PRO_PRICE_ID",
    },
    {
        key: "api_starter",
        name: "Pundit Ledger API Starter",
        description:
            "REST API access — per-pundit scores, prediction history, and resolution data. 10,000 requests/month.",
        unitAmount: 9900, // $99/mo
        envVar: "STRIPE_API_STARTER_PRICE_ID",
    },
    {
        key: "api_growth",
        name: "Pundit Ledger API Growth",
        description:
            "High-volume REST API access. 100,000 requests/month plus priority support.",
        unitAmount: 49900, // $499/mo
        envVar: "STRIPE_API_GROWTH_PRICE_ID",
    },
];

async function findExistingProduct(name: string): Promise<Stripe.Product | null> {
    const products = await stripe.products.list({ limit: 100, active: true });
    return products.data.find((p) => p.name === name) ?? null;
}

async function findExistingPrice(
    productId: string,
    unitAmount: number
): Promise<Stripe.Price | null> {
    const prices = await stripe.prices.list({
        product: productId,
        active: true,
        limit: 20,
    });
    return (
        prices.data.find(
            (p) =>
                p.unit_amount === unitAmount &&
                p.recurring?.interval === "month" &&
                p.currency === "usd"
        ) ?? null
    );
}

async function main() {
    console.log("Setting up Stripe products and prices...\n");

    const results: Record<string, string> = {};

    for (const spec of PRODUCTS) {
        // Upsert product
        let product = await findExistingProduct(spec.name);
        if (!product) {
            product = await stripe.products.create({
                name: spec.name,
                description: spec.description,
                metadata: { key: spec.key },
            });
            console.log(`Created product: ${spec.name} (${product.id})`);
        } else {
            console.log(`Found existing product: ${spec.name} (${product.id})`);
        }

        // Upsert price
        let price = await findExistingPrice(product.id, spec.unitAmount);
        if (!price) {
            price = await stripe.prices.create({
                product: product.id,
                unit_amount: spec.unitAmount,
                currency: "usd",
                recurring: { interval: "month" },
                metadata: { key: spec.key },
            });
            console.log(
                `Created price: $${(spec.unitAmount / 100).toFixed(2)}/mo (${price.id})`
            );
        } else {
            console.log(
                `Found existing price: $${(spec.unitAmount / 100).toFixed(2)}/mo (${price.id})`
            );
        }

        results[spec.envVar] = price.id;
    }

    console.log("\nAdd these to .env.local and Vercel environment variables:\n");
    for (const [envVar, priceId] of Object.entries(results)) {
        console.log(`${envVar}=${priceId}`);
    }
    console.log();
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
