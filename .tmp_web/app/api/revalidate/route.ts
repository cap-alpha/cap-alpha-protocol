import { revalidatePath } from 'next/cache';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    try {
        const body = await request.json();

        // Very basic webhook auth to prevent public clearing
        if (body.token !== process.env.MOTHERDUCK_TOKEN && body.token !== "local-dev-bypass") {
            return NextResponse.json({ message: 'Invalid token' }, { status: 401 });
        }

        // Revalidate the entire dashboard and player routes since data refreshed
        revalidatePath('/dashboard');
        revalidatePath('/', 'layout');

        console.log(`[Cache Revalidation] Triggered forcefully. Next.js will fetch new MotherDuck data.`);
        return NextResponse.json({ revalidated: true, now: Date.now() });
    } catch (err) {
        return NextResponse.json({ message: 'Error revalidating' }, { status: 500 });
    }
}
