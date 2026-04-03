'use client';

import { useState } from "react";
import { submitWaitlist } from "@/app/actions/submit-waitlist";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CheckCircle2, ChevronRight } from "lucide-react";

export function WaitlistForm({ source }: { source?: string } = {}) {
    const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
    const [message, setMessage] = useState("");
    const [submittedEmail, setSubmittedEmail] = useState("");

    async function action(formData: FormData) {
        setStatus("loading");

        const email = formData.get("email") as string;
        setSubmittedEmail(email);

        // Grab the current URL path to infer persona context, or default to general
        const persona = source || (window.location.pathname.includes("agent") ? "Agent" : "General");
        formData.append("persona", persona);

        const result = await submitWaitlist(formData);

        if (result?.error) {
            setStatus("error");
            setMessage(result.error);
        } else {
            setStatus("success");
            setMessage(result?.message || `You're on the list. We'll be in touch at ${email}.`);
        }
    }

    if (status === "success") {
        return (
            <div className="w-full max-w-2xl mx-auto flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="flex items-center justify-center p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400 mr-3 shrink-0" />
                    <p className="text-emerald-300 font-mono text-sm">{message}</p>
                </div>

                <div className="p-6 bg-black/60 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-[80px] pointer-events-none -mr-20 -mt-20" />
                    <h4 className="text-xs font-bold uppercase tracking-widest text-emerald-500 mb-4 flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                        Exclusive Insight Unlocked
                    </h4>
                    <p className="text-slate-300 text-sm mb-4">While you wait for your invite, here are two assets our models currently flag as massively undervalued relative to consensus:</p>

                    <div className="grid sm:grid-cols-2 gap-4">
                        <div className="p-4 bg-white/5 border border-white/10 rounded-lg hover:border-emerald-500/30 transition-colors">
                            <div className="flex justify-between items-start mb-2">
                                <div>
                                    <h5 className="font-bold text-white">Amon-Ra St. Brown</h5>
                                    <p className="text-xs font-mono text-emerald-400">DET | WR</p>
                                </div>
                                <span className="text-xs font-bold px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded">STRONG BUY</span>
                            </div>
                            <p className="text-xs text-slate-400">Efficiency Gap +42%. Projected to outperform $30M AAV market reset by a 2.1x margin over front-loaded years.</p>
                        </div>
                        <div className="p-4 bg-white/5 border border-white/10 rounded-lg hover:border-emerald-500/30 transition-colors">
                            <div className="flex justify-between items-start mb-2">
                                <div>
                                    <h5 className="font-bold text-white">Brock Purdy</h5>
                                    <p className="text-xs font-mono text-emerald-400">SF | QB</p>
                                </div>
                                <span className="text-xs font-bold px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded">HOLD / EXTEND</span>
                            </div>
                            <p className="text-xs text-slate-400">Current contract produces $40M+ in surplus value. Extrapolation models suggest extending early prevents a catastrophic market correction.</p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <form action={action} className="w-full max-w-md mx-auto flex flex-col sm:flex-row gap-3">
            <div className="relative flex-grow">
                <Input
                    type="email"
                    name="email"
                    placeholder="Enter your email..."
                    required
                    className="h-14 bg-white/5 border-white/10 text-white placeholder:text-slate-500 focus-visible:ring-emerald-500 focus-visible:border-emerald-500 pl-4 w-full"
                    disabled={status === "loading"}
                />
            </div>
            <Button
                type="submit"
                disabled={status === "loading"}
                className="h-14 px-8 bg-emerald-500 hover:bg-emerald-600 text-black font-bold text-lg rounded-md transition-all shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:shadow-[0_0_30px_rgba(16,185,129,0.5)] whitespace-nowrap group"
            >
                {status === "loading" ? (
                    <span className="animate-pulse">Joining...</span>
                ) : (
                    <>
                        Join Waitlist
                        <ChevronRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
                    </>
                )}
            </Button>
            {status === "error" && (
                <p className="absolute -bottom-8 left-0 text-red-400 text-xs font-mono">{message}</p>
            )}
        </form>
    );
}
