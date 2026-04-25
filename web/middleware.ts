import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest } from "next/server";

const isProtectedRoute = createRouteMatcher([
    "/scenarios(.*)",
    "/fantasy(.*)",
    "/dashboard/gm(.*)",
    "/dashboard/agent(.*)",
    "/dashboard/bettor(.*)",
    "/dashboard/api-keys(.*)",
    "/api/api-keys(.*)"
]);

// Fallback middleware when Clerk is not configured
function passthroughMiddleware(req: NextRequest) {
    const requestHeaders = new Headers(req.headers);
    requestHeaders.set('x-forwarded-proto', 'https');

    return NextResponse.next({
        request: {
            headers: requestHeaders,
        },
    });
}

// Use Clerk if keys are available, otherwise passthrough
const hasClerkConfig = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY && !!process.env.CLERK_SECRET_KEY;

export default hasClerkConfig
    ? clerkMiddleware((auth, req) => {
        if (isProtectedRoute(req)) {
            auth().protect();
        }

        const requestHeaders = new Headers(req.headers);
        requestHeaders.set('x-forwarded-proto', 'https');

        return NextResponse.next({
            request: {
                headers: requestHeaders,
            },
        });
    })
    : passthroughMiddleware;

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
