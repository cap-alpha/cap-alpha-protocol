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

## Build & Deployment

To build the application for production:

```bash
npm run build
npm start
```
\n<!-- Trigger Vercel Deployment -->
