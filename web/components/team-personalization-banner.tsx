"use client"

import * as React from 'react';
import { ShieldAlert, MapPin } from 'lucide-react';
import { TEAM_NAMES } from '@/lib/team-logos';

export function TeamPersonalizationBanner({ teamName }: { teamName: string }) {
    const [data, setData] = React.useState<{ userCity: string | null; isTrackedTeam: boolean } | null>(null);

    React.useEffect(() => {
        fetch(`/api/personalization?teamName=${encodeURIComponent(teamName)}`)
            .then(res => res.json())
            .then(setData)
            .catch(console.error);
    }, [teamName]);

    if (!data) return null; // Loading state is invisible to avoid layout shift

    const fullTeamName = TEAM_NAMES[teamName] || teamName;
    const isLocalMarket = data.userCity && fullTeamName.toLowerCase().includes(data.userCity.toLowerCase());
    
    if (!isLocalMarket && !data.isTrackedTeam) return null;

    return (
        <div className="bg-emerald-500/10 border border-emerald-500/30 p-4 rounded-lg flex items-center gap-3 mb-6 animate-in slide-in-from-top-4 fade-in duration-700">
            {isLocalMarket ? <MapPin className="h-5 w-5 text-emerald-500" /> : <ShieldAlert className="h-5 w-5 text-emerald-500" />}
            <div>
                <p className="font-bold text-sm text-emerald-400">
                    {isLocalMarket ? `${data.userCity} Local Market Intel` : 'Direct Portfolio Analytics'}
                </p>
                <p className="text-xs text-emerald-500/80 mt-0.5">
                    {isLocalMarket 
                        ? `Displaying deep cap liabilities tailored for the ${data.userCity} broadcast region.` 
                        : `High-priority cap alerts enabled. Rendering absolute portfolio risk for your synced franchise.`}
                </p>
            </div>
        </div>
    );
}
