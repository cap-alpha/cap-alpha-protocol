import { NextResponse } from "next/server";
import type { NextRequest, NextFetchEvent } from "next/server";

const hasClerkKeys = !!(
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
    process.env.CLERK_SECRET_KEY
);

// Cache the Clerk handler so we only do the dynamic import once.
let clerkHandler: ((req: NextRequest, event: NextFetchEvent) => Promise<NextResponse> | NextResponse) | null = null;

async function getClerkHandler() {
    if (clerkHandler) return clerkHandler;
    const { clerkMiddleware, createRouteMatcher } = await import("@clerk/nextjs/server");

    const isProtectedRoute = createRouteMatcher([
        "/scenarios(.*)",
        "/fantasy(.*)",
        "/dashboard/gm(.*)",
        "/dashboard/agent(.*)",
        "/dashboard/bettor(.*)",
        "/dashboard/api-keys(.*)",
        "/api/api-keys(.*)"
    ]);

    clerkHandler = clerkMiddleware((auth, req) => {
        if (isProtectedRoute(req)) {
            auth().protect();
        }

        const requestHeaders = new Headers(req.headers);
        requestHeaders.set('x-forwarded-proto', 'https');

        return NextResponse.next({
            request: { headers: requestHeaders },
        });
    });

    return clerkHandler;
}

// When Clerk keys are present, delegate to clerkMiddleware.
// When absent (CI / Docker E2E), use a simple pass-through so the app
// doesn't crash with HTTP 500 on every request.
export default async function middleware(req: NextRequest, event: NextFetchEvent) {
    if (hasClerkKeys) {
        const handler = await getClerkHandler();
        return handler(req, event);
    }

    // No Clerk keys — pass-through middleware
    const requestHeaders = new Headers(req.headers);
    requestHeaders.set('x-forwarded-proto', 'https');
    return NextResponse.next({
        request: { headers: requestHeaders },
    });
}

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
