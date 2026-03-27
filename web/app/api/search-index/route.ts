import { NextResponse } from 'next/server';
import { getSearchIndex } from '@/app/actions';

export const revalidate = 3600; // SSG/ISR at the route level

export async function GET() {
    try {
        const index = await getSearchIndex();
        
        return NextResponse.json(index, {
            headers: {
                // Public edge caching. Stale-while-revalidate ensures it never blocks.
                'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
            },
        });
    } catch (error) {
        console.error('Error fetching search index:', error);
        return NextResponse.json({ error: 'Failed to load index' }, { status: 500 });
    }
}
