import { revalidatePath } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
    try {
        const token = request.headers.get("x-revalidate-token");

        if (!token || token !== process.env.REVALIDATE_SECRET) {
            return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
        }

        // Revalidate the entire dashboard and player routes since data refreshed
        revalidatePath('/dashboard');
        revalidatePath('/', 'layout');

        console.log(`[Cache Revalidation] Triggered. Next.js will fetch fresh data.`);
        return NextResponse.json({ revalidated: true, now: Date.now() });
    } catch (err) {
        return NextResponse.json({ message: 'Error revalidating' }, { status: 500 });
    }
}
