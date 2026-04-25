# Web Application Documentation

## Overview

The **Cap Alpha Protocol Frontend** is a Next.js application designed to visualize roster capital efficiency and potential "dead money" risks. It provides an executive dashboard for traversing the $20B+ contract landscape.

### Tech Stack
- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS
- **Visualization**: Recharts
- **State Management**: React Server Components (RSC) + Context

---

## Setup & Development

### Prerequisites
- Node.js 18+
- npm or yarn

### Installation

```bash
# 1. Install Dependencies
npm install

# 2. Configure Environment
# Copy the example environment file
cp .env.example .env.local
```

### Running Locally

```bash
# Start the development server
npm run dev
```

The application will be available at `http://localhost:3000`.

---

## Architecture

### Component Hierarchy
- `app/`: Next.js App Router pages and layouts.
- `components/ui/`: Reusable UI primitives (buttons, cards, etc.).
- `components/dashboard/`: Business logic components (charts, tables).
- `lib/`: Utility functions and API clients.

### Data Fetching
Data is hydrated via Server Actions or API routes that interface with the `pipeline` output (JSON/Parquet/DuckDB).

---

## Stripe Billing

### Setup

1. Run the IaC script once to create products + prices in Stripe (test mode):

```bash
STRIPE_SECRET_KEY=sk_test_... npx tsx --env-file=.env.local scripts/stripe-setup.ts
```

2. Copy the output price IDs into `.env.local` and Vercel environment variables.

### Required environment variables

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret key (`sk_test_...` or `sk_live_...`) |
| `STRIPE_PRO_PRICE_ID` | Price ID for the Pro plan ($14.99/mo) |
| `STRIPE_API_STARTER_PRICE_ID` | Price ID for API Starter ($99/mo) |
| `STRIPE_API_GROWTH_PRICE_ID` | Price ID for API Growth ($499/mo) |
| `NEXT_PUBLIC_APP_URL` | Public app URL for redirect URLs (e.g. `https://cap-alpha.co`) |

### Testing the end-to-end flow

1. Start the dev server: `npm run dev`
2. Sign in with a Clerk test account
3. Navigate to `/pricing` and click **Upgrade to Pro**
4. Complete checkout with Stripe test card `4242 4242 4242 4242`
5. Confirm redirect back to `/dashboard?checkout=success`
6. Confirm `stripe_customer_id` appears in Clerk user public metadata
7. Navigate to `/dashboard/billing` → click **Manage Subscription** → confirm Customer Portal loads

---

## Build & Deployment

To build the application for production:

```bash
npm run build
npm start
```
\n<!-- Trigger Vercel Deployment -->
