import { getRosterData } from "@/app/actions";
import { FantasyDashboard } from "@/components/fantasy-dashboard";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { SignedIn, SignedOut, SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { SectionHeading } from "@/components/ui/heading";
import { Lock } from "lucide-react";

export default async function FantasyPage() {
    const rosterData = await getRosterData();

    return (
        <main className="min-h-[100dvh] bg-editorial-bg text-ink p-8">
            <PageContainer size="7xl" className="space-y-8">
                <div className="flex items-center gap-4 border-b border-editorial-border pb-6">
                    <Link href="/dashboard" className="p-2 hover:bg-editorial-card rounded-full transition-colors text-ink-3">
                        <ArrowLeft className="h-6 w-6" />
                    </Link>
                    <div>
                        <SectionHeading size="xl" className="uppercase text-accent-editorial">
                            FANTASY ALPHA
                        </SectionHeading>
                        <p className="text-ink-2 uppercase tracking-widest text-sm mt-1">Cross-Platform Roster Synchronization</p>
                    </div>
                </div>

                <SignedIn>
                    <FantasyDashboard rosterData={rosterData} />
                </SignedIn>

                <SignedOut>
                    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center max-w-lg mx-auto p-12 bg-editorial-card border border-editorial-border rounded-xl relative overflow-hidden">
                        <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-accent-editorial to-gold" />
                        <Lock className="h-16 w-16 text-accent-editorial mb-6" />
                        <h2 className="text-3xl font-bold font-mono tracking-tight text-ink mb-4">RESTRICTED ACCESS</h2>
                        <p className="text-ink-2 text-lg mb-8 leading-relaxed">
                            To sync your fantasy league and unlock premium Fair Market Value projections, you must authenticate as an Executive Tier user.
                        </p>
                        <SignInButton mode="modal">
                            <Button className="bg-accent-editorial hover:bg-accent-editorial-light text-white px-8 py-6 uppercase tracking-widest font-bold text-sm w-full">
                                Request Access Token
                            </Button>
                        </SignInButton>
                    </div>
                </SignedOut>
            </PageContainer>
        </main>
    );
}
