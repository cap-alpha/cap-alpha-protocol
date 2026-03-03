"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle2, RefreshCw } from "lucide-react";

export function FantasySyncWizard({ onComplete }: { onComplete: () => void }) {
    const [step, setStep] = useState<"SELECT" | "SYNCING" | "ANALYZING" | "DONE">("SELECT");

    const startSync = () => {
        setStep("SYNCING");
        setTimeout(() => setStep("ANALYZING"), 2000);
        setTimeout(() => setStep("DONE"), 4500);
    };

    return (
        <Card className="max-w-lg mx-auto bg-slate-900 border-slate-800 text-center relative overflow-hidden">
            <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-emerald-400 to-cyan-400" />
            <CardHeader className="pt-8">
                <CardTitle className="text-2xl font-bold font-mono tracking-tight text-white mb-2">Fantasy Integration</CardTitle>
                <CardDescription className="text-slate-400 text-sm">
                    Sync your league to project Fair Market Value and unearth waiver wire alpha.
                </CardDescription>
            </CardHeader>
            <CardContent className="pb-8 min-h-[220px] flex flex-col items-center justify-center">
                {step === "SELECT" && (
                    <div className="space-y-4 w-full px-4">
                        <Button
                            variant="outline"
                            className="w-full h-14 border-slate-700 bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-all relative group"
                            onClick={startSync}
                        >
                            <span className="group-hover:-translate-x-1 transition-transform">Connect Yahoo! Fantasy</span>
                            <span className="absolute right-4 opacity-0 group-hover:opacity-100 transition-opacity">→</span>
                        </Button>
                        <Button
                            variant="outline"
                            className="w-full h-14 border-slate-700 bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-all relative group"
                            onClick={startSync}
                        >
                            <span className="group-hover:-translate-x-1 transition-transform">Connect ESPN Fantasy</span>
                            <span className="absolute right-4 opacity-0 group-hover:opacity-100 transition-opacity">→</span>
                        </Button>
                        <p className="text-xs text-slate-500 mt-4">
                            Platform requires Read-Only access to map active rosters.
                        </p>
                    </div>
                )}

                {step === "SYNCING" && (
                    <div className="flex flex-col items-center space-y-4 animate-in fade-in zoom-in duration-300">
                        <RefreshCw className="h-10 w-10 text-emerald-500 animate-spin" />
                        <h3 className="text-lg font-mono text-emerald-400 mt-4">Connecting to Provider...</h3>
                        <p className="text-sm text-slate-500">Retrieving 2026 active roster data</p>
                    </div>
                )}

                {step === "ANALYZING" && (
                    <div className="flex flex-col items-center space-y-4 animate-in fade-in zoom-in duration-300">
                        <Loader2 className="h-10 w-10 text-cyan-500 animate-spin" />
                        <h3 className="text-lg font-mono text-cyan-400 mt-4">Running Cap Alpha Models...</h3>
                        <p className="text-sm text-slate-500">Bypassing standard ADPs. Calculating expected capital exposure.</p>
                    </div>
                )}

                {step === "DONE" && (
                    <div className="flex flex-col items-center space-y-6 animate-in fade-in zoom-in duration-500">
                        <div className="h-16 w-16 bg-emerald-500/10 rounded-full flex items-center justify-center">
                            <CheckCircle2 className="h-8 w-8 text-emerald-500" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-white">Sync Complete</h3>
                            <p className="text-sm text-emerald-400 mt-1 font-mono">14 Assets Ingested & Graded</p>
                        </div>
                        <Button
                            className="bg-emerald-500 hover:bg-emerald-600 text-white w-full h-12 text-sm uppercase tracking-widest font-bold mt-2"
                            onClick={onComplete}
                        >
                            Enter Fantasy War Room
                        </Button>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
