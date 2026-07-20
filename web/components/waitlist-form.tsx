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
                <div className="flex items-center justify-center p-4 bg-navy/10 border border-navy/30 rounded-lg">
                    <CheckCircle2 className="w-5 h-5 text-navy mr-3 shrink-0" />
                    <p className="text-navy font-mono text-sm">{message}</p>
                </div>

                {/* Editorial palette (#1069): dropped backdrop-blur-md, the glow
                    blur div, and shadow-2xl — this was the design brief's #1
                    named example of glassmorphism ("bg-black/60 backdrop-blur-md
                    border border-white/10 rounded-xl shadow-2xl"). Flat card
                    surface + border, no live/pulse dot (matches the hero's
                    "no live/pulse chrome" rule). Copy/content unchanged — that's
                    a product decision outside this PR's scope. */}
                <div className="p-6 bg-editorial-card border border-editorial-border rounded-xl">
                    <h4 className="text-xs font-bold uppercase tracking-widest text-navy mb-4 flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-navy"></span>
                        Exclusive Insight Unlocked
                    </h4>
                    <p className="text-ink-2 text-sm mb-4">While you wait for your invite, here are two assets our models currently flag as massively undervalued relative to consensus:</p>

                    <div className="grid sm:grid-cols-2 gap-4">
                        <div className="p-4 bg-editorial-bg border border-editorial-border rounded-lg hover:border-navy/30 transition-colors">
                            <div className="flex justify-between items-start mb-2">
                                <div>
                                    <h5 className="font-bold text-ink">Amon-Ra St. Brown</h5>
                                    <p className="text-xs font-mono text-navy">DET | WR</p>
                                </div>
                                <span className="text-xs font-bold px-2 py-1 bg-navy/10 text-navy rounded">STRONG BUY</span>
                            </div>
                            <p className="text-xs text-ink-2">Efficiency Gap +42%. Projected to outperform $30M AAV market reset by a 2.1x margin over front-loaded years.</p>
                        </div>
                        <div className="p-4 bg-editorial-bg border border-editorial-border rounded-lg hover:border-navy/30 transition-colors">
                            <div className="flex justify-between items-start mb-2">
                                <div>
                                    <h5 className="font-bold text-ink">Brock Purdy</h5>
                                    <p className="text-xs font-mono text-navy">SF | QB</p>
                                </div>
                                <span className="text-xs font-bold px-2 py-1 bg-navy/10 text-navy rounded">HOLD / EXTEND</span>
                            </div>
                            <p className="text-xs text-ink-2">Current contract produces $40M+ in surplus value. Extrapolation models suggest extending early prevents a catastrophic market correction.</p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="w-full max-w-md mx-auto space-y-2">
            <form action={action} className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-grow min-w-0">
                    <Input
                        type="email"
                        name="email"
                        placeholder="Enter your email..."
                        required
                        className="h-14 bg-editorial-card border-editorial-border text-ink placeholder:text-ink-3 focus-visible:ring-navy/30 focus-visible:border-navy pl-4 w-full"
                        disabled={status === "loading"}
                    />
                </div>
                {/* Flat navy, no glow shadow — matches the hero CTA (#1069) */}
                <Button
                    type="submit"
                    disabled={status === "loading"}
                    className="h-14 min-h-[44px] px-8 bg-navy hover:bg-accent-editorial-light text-white font-bold text-lg rounded-md transition-all whitespace-nowrap group"
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
            </form>
            {status === "error" && (
                <p className="text-incorrect text-xs font-mono text-left">{message}</p>
            )}
        </div>
    );
}
