import { auth } from '@clerk/nextjs/server';
import { db } from '@/db';
import { scenarios } from '@/db/schema';
import { eq, desc } from 'drizzle-orm';
import { redirect } from 'next/navigation';
import { UserButton, SignedIn } from '@clerk/nextjs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Scissors, Calendar, DollarSign } from 'lucide-react';

export default async function ScenariosPage() {
    const { userId } = auth();

    if (!userId) {
        redirect('/');
    }

    const savedScenarios = await db.select().from(scenarios)
        .where(eq(scenarios.userId, userId))
        .orderBy(desc(scenarios.createdAt));

    return (
        <main className="min-h-screen bg-slate-950 font-sans selection:bg-indigo-500/30">
            {/* Header: The War Room */}
            <header className="mb-8 flex items-center justify-between border-b border-border pb-4 px-8 pt-8">
                <div>
                    <h1 className="text-4xl font-bold tracking-tight text-foreground">CAP ALPHA PROTOCOL // <span className="text-emerald-500">EXECUTIVE SUITE</span></h1>
                </div>
                <div className="flex gap-4 items-center">
                    <SignedIn>
                        <UserButton afterSignOutUrl="/" />
                    </SignedIn>
                </div>
            </header>
            <div className="container mx-auto px-4 py-4 max-w-6xl">
                <div className="mb-10">
                    <h1 className="text-4xl font-black text-white tracking-tight mb-4">My Dashboard</h1>
                    <p className="text-slate-400 text-lg">Review your saved roster manipulations and Cut Calculator scenarios.</p>
                </div>

                {savedScenarios.length === 0 ? (
                    <div className="text-center py-20 border border-slate-800 rounded-xl bg-slate-900 border-dashed">
                        <Scissors className="mx-auto h-12 w-12 text-slate-600 mb-4" />
                        <h2 className="text-xl font-bold text-white mb-2">No scenarios yet</h2>
                        <p className="text-slate-400">Head over to the Cut Calculator to start building your cap strategy.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {savedScenarios.map((s) => {
                            const roster = s.rosterState as any;
                            const financials = roster?.financials || {};

                            return (
                                <Card key={s.id} className="bg-slate-900 border-slate-800 text-slate-100 hover:border-indigo-500/50 transition-colors">
                                    <CardHeader className="pb-3">
                                        <CardTitle className="text-lg font-bold flex items-center gap-2">
                                            <Scissors className="h-4 w-4 text-emerald-400" />
                                            {s.name}
                                        </CardTitle>
                                        <CardDescription className="text-slate-500 text-xs flex items-center gap-1 mt-1">
                                            <Calendar className="h-3 w-3" />
                                            {new Date(s.createdAt!).toLocaleDateString()}
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <p className="text-sm text-slate-400 mb-6 line-clamp-2">
                                            {s.description}
                                        </p>

                                        <div className="grid grid-cols-2 gap-4 border-t border-slate-800 pt-4">
                                            <div>
                                                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1 flex items-center gap-1">
                                                    <DollarSign className="h-3 w-3" /> Net Savings
                                                </p>
                                                <p className="text-xl font-bold text-emerald-400">
                                                    ${financials.savings?.toLocaleString() ?? 0}M
                                                </p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                                                    Dead Money
                                                </p>
                                                <p className="text-xl font-bold text-red-400">
                                                    ${financials.deadCap?.toLocaleString() ?? 0}M
                                                </p>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>
                )}
            </div>
        </main>
    );
}
