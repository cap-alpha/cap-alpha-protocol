import { NextResponse, type NextRequest } from "next/server";

const isProtectedRoute = (pathname: string) => {
    const protectedPaths = [
        "/scenarios",
        "/fantasy",
        "/dashboard/gm",
        "/dashboard/agent",
        "/dashboard/bettor",
        "/dashboard/api-keys",
        "/api/api-keys"
    ];
    return protectedPaths.some(path => pathname.startsWith(path));
};

// Simple passthrough middleware that always works
function safeMiddleware(req: NextRequest) {
    const requestHeaders = new Headers(req.headers);
    requestHeaders.set('x-forwarded-proto', 'https');

    return NextResponse.next({
        request: {
            headers: requestHeaders,
        },
    });
}

// Try to use Clerk middleware, fall back to safe middleware on error
let clerkMiddlewareHandler: any = null;
try {
    const { clerkMiddleware, createRouteMatcher } = require("@clerk/nextjs/server");
    const protectedRouteMatcher = createRouteMatcher([
        "/scenarios(.*)",
        "/fantasy(.*)",
        "/dashboard/gm(.*)",
        "/dashboard/agent(.*)",
        "/dashboard/bettor(.*)",
        "/dashboard/api-keys(.*)",
        "/api/api-keys(.*)"
    ]);

    clerkMiddlewareHandler = clerkMiddleware((auth: any, req: NextRequest) => {
        if (protectedRouteMatcher(req)) {
            auth().protect();
        }

        const requestHeaders = new Headers(req.headers);
        requestHeaders.set('x-forwarded-proto', 'https');

        return NextResponse.next({
            request: {
                headers: requestHeaders,
            },
        });
    });
} catch (error) {
    // Clerk initialization failed, use safe middleware
    console.warn("Clerk middleware initialization failed, using safe middleware fallback");
}

// Export either Clerk middleware or safe fallback
export default clerkMiddlewareHandler || safeMiddleware;

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
