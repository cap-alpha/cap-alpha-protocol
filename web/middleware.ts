import { NextResponse } from "next/server";
import type { NextRequest, NextFetchEvent } from "next/server";

const hasClerkKeys = !!(
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
    process.env.CLERK_SECRET_KEY
);

// Passthrough middleware when Clerk is not configured (CI/Docker)
function passthroughMiddleware(req: NextRequest) {
    const requestHeaders = new Headers(req.headers);
    requestHeaders.set('x-forwarded-proto', 'https');
    return NextResponse.next({
        request: { headers: requestHeaders },
    });
}

// Clerk middleware — only loaded when keys are present
let clerkHandler: ((req: NextRequest, event: NextFetchEvent) => any) | null = null;

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

export default async function middleware(req: NextRequest, event: NextFetchEvent) {
    if (!hasClerkKeys) {
        return passthroughMiddleware(req);
    }
    const handler = await getClerkHandler();
    return handler(req, event);
}

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
