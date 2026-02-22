import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher(["/dashboard(.*)", "/scenarios(.*)", "/player(.*)"]);

export default clerkMiddleware(async (auth, req) => {
    // @ts-ignore
    if (isProtectedRoute(req)) (await auth()).protect();
});

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
