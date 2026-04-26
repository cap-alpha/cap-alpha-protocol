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

// Clerk requires a valid publishable key (starts with "pk_").
// When the key is absent (CI, Docker without secrets) we export a simple passthrough
// instead of calling clerkMiddleware(), which would throw MIDDLEWARE_INVOCATION_FAILED
// and return 500 on every request.
const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const clerkConfigured = publishableKey?.startsWith("pk_") ?? false;

function addForwardedProto(req: NextRequest) {
    const headers = new Headers(req.headers);
    headers.set("x-forwarded-proto", "https");
    return NextResponse.next({ request: { headers } });
}

export default clerkConfigured
    ? clerkMiddleware((auth, req) => {
          if (isProtectedRoute(req)) {
              auth().protect();
          }
          return addForwardedProto(req);
      })
    : addForwardedProto;

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
