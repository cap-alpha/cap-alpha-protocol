import { NextResponse, type NextRequest } from "next/server";

// Simple passthrough middleware - always works, no auth dependency.
// Clerk was causing MIDDLEWARE_INVOCATION_FAILED 500 errors on all API
// routes when CLERK_SECRET_KEY was not configured in Vercel.
export default function middleware(request: NextRequest) {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('x-forwarded-proto', 'https');

    return NextResponse.next({
        request: {
            headers: requestHeaders,
        },
    });
}

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
