import { getRosterData } from "@/app/actions";
import { FantasyDashboard } from "@/components/fantasy-dashboard";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { SignedIn, SignedOut, SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Lock } from "lucide-react";

export default async function FantasyPage() {
    const rosterData = await getRosterData();

    return (
        <main className="min-h-[100dvh] bg-background text-foreground p-8">
            <div className="max-w-7xl mx-auto space-y-8">
                <div className="flex items-center gap-4 border-b border-border pb-6">
                    <Link href="/dashboard" className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400">
                        <ArrowLeft className="h-6 w-6" />
                    </Link>
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight uppercase text-emerald-500">
                            FANTASY ALPHA
                        </h1>
                        <p className="text-muted-foreground uppercase tracking-widest text-sm mt-1">Cross-Platform Roster Synchronization</p>
                    </div>
                </div>

                <SignedIn>
                    <FantasyDashboard rosterData={rosterData} />
                </SignedIn>

                <SignedOut>
                    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center max-w-lg mx-auto p-12 bg-slate-900 border border-slate-800 rounded-xl relative overflow-hidden">
                        <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-emerald-400 to-cyan-400" />
                        <Lock className="h-16 w-16 text-emerald-500 mb-6" />
                        <h2 className="text-3xl font-bold font-mono tracking-tight text-white mb-4">RESTRICTED ACCESS</h2>
                        <p className="text-slate-400 text-lg mb-8 leading-relaxed">
                            To sync your fantasy league and unlock premium Fair Market Value projections, you must authenticate as an Executive Tier user.
                        </p>
                        <SignInButton mode="modal">
                            <Button className="bg-emerald-500 hover:bg-emerald-600 text-white px-8 py-6 uppercase tracking-widest font-bold text-sm w-full">
                                Request Access Token
                            </Button>
                        </SignInButton>
                    </div>
                </SignedOut>
            </div>
        </main>
    );
}
