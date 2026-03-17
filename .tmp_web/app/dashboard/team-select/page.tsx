import "server-only";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";

const NFL_TEAMS = [
    { id: "ARI", name: "Arizona Cardinals", color: "bg-red-700" },
    { id: "ATL", name: "Atlanta Falcons", color: "bg-red-600" },
    { id: "BAL", name: "Baltimore Ravens", color: "bg-purple-900" },
    { id: "BUF", name: "Buffalo Bills", color: "bg-blue-700" },
    { id: "CAR", name: "Carolina Panthers", color: "bg-sky-500" },
    { id: "CHI", name: "Chicago Bears", color: "bg-orange-800" },
    { id: "CIN", name: "Cincinnati Bengals", color: "bg-orange-600" },
    { id: "CLE", name: "Cleveland Browns", color: "bg-orange-900" },
    { id: "DAL", name: "Dallas Cowboys", color: "bg-slate-300 text-slate-900" },
    { id: "DEN", name: "Denver Broncos", color: "bg-orange-500" },
    { id: "DET", name: "Detroit Lions", color: "bg-sky-600" },
    { id: "GB", name: "Green Bay Packers", color: "bg-green-800" },
    { id: "HOU", name: "Houston Texans", color: "bg-slate-800" },
    { id: "IND", name: "Indianapolis Colts", color: "bg-blue-800" },
    { id: "JAX", name: "Jacksonville Jaguars", color: "bg-teal-700" },
    { id: "KC", name: "Kansas City Chiefs", color: "bg-red-600" },
    { id: "LV", name: "Las Vegas Raiders", color: "bg-slate-900 border border-slate-700" },
    { id: "LAC", name: "Los Angeles Chargers", color: "bg-sky-300 text-sky-900" },
    { id: "LAR", name: "Los Angeles Rams", color: "bg-blue-800" },
    { id: "MIA", name: "Miami Dolphins", color: "bg-teal-500" },
    { id: "MIN", name: "Minnesota Vikings", color: "bg-purple-800" },
    { id: "NE", name: "New England Patriots", color: "bg-slate-800" },
    { id: "NO", name: "New Orleans Saints", color: "bg-yellow-600 text-black" },
    { id: "NYG", name: "New York Giants", color: "bg-blue-700" },
    { id: "NYJ", name: "New York Jets", color: "bg-green-700" },
    { id: "PHI", name: "Philadelphia Eagles", color: "bg-emerald-900" },
    { id: "PIT", name: "Pittsburgh Steelers", color: "bg-yellow-500 text-black" },
    { id: "SF", name: "San Francisco 49ers", color: "bg-red-700" },
    { id: "SEA", name: "Seattle Seahawks", color: "bg-green-500 text-black" },
    { id: "TB", name: "Tampa Bay Buccaneers", color: "bg-red-900" },
    { id: "TEN", name: "Tennessee Titans", color: "bg-blue-300 text-blue-900" },
    { id: "WAS", name: "Washington Commanders", color: "bg-red-900" },
];

export default async function TeamSelection() {
    const { userId } = await auth();

    if (!userId) {
        redirect("/");
    }

    // Checking Subscription Status here (Placeholder logic for now before Webhook)
    const isSubscriptionActive = true;

    if (!isSubscriptionActive) {
        // Redirect to Stripe Customer Portal
    }

    return (
        <main className="min-h-[100dvh] bg-background p-8 flex flex-col items-center justify-center">

            <div className="mb-8 flex items-center gap-3 text-emerald-500">
                <ShieldAlert className="w-8 h-8" />
                <h1 className="text-3xl font-bold font-mono tracking-tight">CAP ALPHA PROTOCOL</h1>
            </div>

            <Card className="w-full max-w-5xl bg-card border-border shadow-xl">
                <CardHeader className="text-center pb-8 border-b border-border/50">
                    <CardTitle className="text-4xl font-extrabold tracking-tight">Select Your Roster</CardTitle>
                    <p className="text-muted-foreground mt-2 text-lg">Choose a franchise to load their Cap Sheet and active predictive models.</p>
                </CardHeader>
                <CardContent className="pt-8">
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                        {NFL_TEAMS.map((team) => (
                            <Link key={team.id} href={`/dashboard?active_team=${team.id}`}>
                                <Button
                                    className={`w-full h-20 text-md font-bold hover:opacity-80 transition-opacity ${team.color}`}
                                >
                                    {team.name}
                                </Button>
                            </Link>
                        ))}
                    </div>
                </CardContent>
            </Card>
        </main>
    );
}
