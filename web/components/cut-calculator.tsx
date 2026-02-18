'use client';

import { useState } from 'react';
import { PlayerEfficiency } from '@/app/actions';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Lock, AlertTriangle, CheckCircle, Scissors } from 'lucide-react';

interface CutCalculatorProps {
    player: PlayerEfficiency;
}

export function CutCalculator({ player }: CutCalculatorProps) {
    const [isPostJune1, setIsPostJune1] = useState(false);
    const [showPaywall, setShowPaywall] = useState(false);

    const deadCap = isPostJune1 ? player.dead_cap_post_june1 : player.dead_cap_pre_june1;
    const savings = isPostJune1 ? player.savings_post_june1 : player.savings_pre_june1;

    const handleToggle = (checked: boolean) => {
        if (checked) {
            // Trigger user story: "Casual Carl" hits the paywall
            setShowPaywall(true);
            // We don't actually toggle logic yet, we show the wall.
            // For demo purposes, we can let them toggle after a "Fake Paywall" delay or just show the wall.
            // Let's toggle it but show a "Pro Feature" badge/warning.
            setIsPostJune1(true);
        } else {
            setIsPostJune1(false);
            setShowPaywall(false);
        }
    };

    const isSavings = (savings || 0) > 0;

    return (
        <Card className="w-full bg-slate-900 border-slate-800 text-slate-100 shadow-xl overflow-hidden">
            <CardHeader className="border-b border-slate-800 pb-4">
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                        <Scissors className="h-5 w-5 text-emerald-400" />
                        <CardTitle className="text-lg font-bold">Cut Calculator</CardTitle>
                    </div>
                    <div className="flex items-center space-x-2">
                        <span className={`text-sm font-medium ${!isPostJune1 ? 'text-white' : 'text-slate-500'}`}>Pre-June 1</span>
                        <Switch
                            checked={isPostJune1}
                            onChange={(e) => handleToggle(e.target.checked)}
                            className="data-[state=checked]:bg-emerald-600"
                        />
                        <span className={`text-sm font-medium ${isPostJune1 ? 'text-emerald-400' : 'text-slate-500'}`}>
                            Post-June 1 {isPostJune1 && <Lock className="inline h-3 w-3 ml-1" />}
                        </span>
                    </div>
                </div>
                <CardDescription className="text-slate-400">
                    Simulate releasing {player.player_name}. {isPostJune1 ? "Spreads dead money over 2 years." : "Accelerates all dead money to current year."}
                </CardDescription>
            </CardHeader>

            <CardContent className="pt-6 relative">

                {/* Paywall Overlay for Post-June 1 (Simulated) */}
                {showPaywall && (
                    <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-[1px] z-10 flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-300">
                        <div className="bg-gradient-to-br from-indigo-600 to-purple-700 p-6 rounded-xl shadow-2xl border border-indigo-400/30 max-w-sm">
                            <Lock className="h-8 w-8 text-white mx-auto mb-3" />
                            <h3 className="text-xl font-bold text-white mb-2">Unlock Pro Mode</h3>
                            <p className="text-indigo-100 text-sm mb-4">Post-June 1 Designations & multi-year restructure modeling are available in the Executive Suite.</p>
                            <div className="flex gap-2 justify-center">
                                <button
                                    onClick={() => setShowPaywall(false)} // Let them "preview" for now or cancel
                                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm font-medium transition-colors"
                                >
                                    Preview (Demo)
                                </button>
                                <button className="px-4 py-2 bg-white text-indigo-700 hover:bg-indigo-50 rounded-lg text-sm font-bold shadow-lg transition-transform hover:scale-105">
                                    Upgrade $5/mo
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                <div className="grid grid-cols-2 gap-8">
                    {/* Dead Money Section */}
                    <div className="space-y-2">
                        <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Dead Money Hit</p>
                        <div className="flex items-baseline gap-1">
                            <span className="text-3xl font-bold text-red-400">
                                ${(deadCap || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M
                            </span>
                        </div>
                        <p className="text-xs text-slate-500">
                            {isPostJune1 ? "Allocated to 2025 Cap" : "Immediate Charge"}
                        </p>
                    </div>

                    {/* Savings Section */}
                    <div className="space-y-2 text-right">
                        <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Net Cap Savings</p>
                        <div className={`flex items-baseline gap-1 justify-end ${isSavings ? 'text-emerald-400' : 'text-red-400'}`}>
                            {isSavings ? <CheckCircle className="h-5 w-5 mr-1" /> : <AlertTriangle className="h-5 w-5 mr-1" />}
                            <span className="text-3xl font-bold">
                                {isSavings ? '+' : ''}${(savings || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M
                            </span>
                        </div>
                        <p className="text-xs text-slate-500">
                            {isSavings ? "Available for Free Agents" : "Loss of Cap Space"}
                        </p>
                    </div>
                </div>

                {/* Context Bar */}
                <div className="mt-8 pt-4 border-t border-slate-800">
                    <div className="text-sm text-slate-400 flex justify-between">
                        <span>Current Cap Hit: <span className="text-slate-200">${player.cap_hit_millions.toLocaleString()}M</span></span>
                        <span>Efficiency Impact: <span className="text-slate-200">{player.risk_score > 0.5 ? "High Risk Removed" : "Low Risk Loss"}</span></span>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
