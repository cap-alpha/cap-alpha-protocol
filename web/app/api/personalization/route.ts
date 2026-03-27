import { NextResponse } from 'next/server';
import { headers, cookies } from 'next/headers';

export const runtime = 'edge'; // Edge function for absolute lowest latency

export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const teamName = searchParams.get('teamName');

    if (!teamName) {
        return NextResponse.json({ error: 'Missing teamName' }, { status: 400 });
    }

    const headersList = headers();
    const userCity = headersList.get('x-vercel-ip-city');
    
    // Simple substring match for local market. Full mapping should be handled by the UI.
    const isLocalMarket = userCity ? true : false; 

    const cookieStore = cookies();
    const trackedTeam = cookieStore.get('nfl_tracked_team')?.value;
    const isTrackedTeam = trackedTeam === teamName;

    return NextResponse.json({
        userCity: userCity || null,
        isLocalMarket,
        isTrackedTeam
    });
}
