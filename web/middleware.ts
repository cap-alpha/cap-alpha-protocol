import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher([
    "/scenarios(.*)", 
    "/fantasy(.*)",
    "/dashboard/gm(.*)",
    "/dashboard/agent(.*)",
    "/dashboard/bettor(.*)"
]);
export default clerkMiddleware(async (auth, req) => {
    // @ts-ignore
    if (isProtectedRoute(req)) (await auth()).protect();
});

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
