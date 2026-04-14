import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const isProtectedRoute = createRouteMatcher([
    "/scenarios(.*)",
    "/fantasy(.*)",
    "/dashboard/gm(.*)",
    "/dashboard/agent(.*)",
    "/dashboard/bettor(.*)",
    "/dashboard/api-keys(.*)",
    "/api/api-keys(.*)"
]);

export default clerkMiddleware((auth, req) => {
    if (isProtectedRoute(req)) {
        auth().protect();
    }
    
    const requestHeaders = new Headers(req.headers);
    requestHeaders.set('x-forwarded-proto', 'https'); // Often needed for local headless testing behind proxies
    
    const response = NextResponse.next({
        request: {
            headers: requestHeaders,
        },
    });

    // We can also set CSP here if next.config.js headers are not enough:
    // response.headers.set('Content-Security-Policy', "worker-src 'self' blob:;");
    
    return response;
});

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
