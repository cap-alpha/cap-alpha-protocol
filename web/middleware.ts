import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublicRoute = createRouteMatcher(["/", "/demo", "/player(.*)", "/api/python(.*)"]);

export default clerkMiddleware(async (auth, req) => {
    // @ts-ignore
    if (!isPublicRoute(req)) (await auth()).protect();
});

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
