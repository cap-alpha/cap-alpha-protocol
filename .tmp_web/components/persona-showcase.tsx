"use client";

import { useState } from "react";
import { SignInButton, SignedIn, SignedOut } from "@clerk/nextjs";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { TrendingUp, User, Briefcase, Activity, ChevronRight, ShieldCheck, AlertCircle, TrendingDown, Target } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useRouter } from "next/navigation";

// Define the 4 Core Personas
const PERSONAS = [
    {
        id: "gm",
        title: "The Front Office",
        icon: ShieldCheck,
        color: "text-blue-400",
        border: "border-blue-500/30",
        bg: "bg-blue-500/10",
        gradient: "from-blue-600 to-indigo-600",
        path: "/dashboard/gm",
        tagline: "Total Roster Architecture",
        description: "Identify overvalued assets, simulate post-June 1st designations, and manage multi-year cap exposure before the market catches on.",
        proofOfAlpha: {
            title: "Cap Liability Managed",
            metric: "+$14.2M",
            subtitle: "Saved vs Expected Variance",
            details: "Model identified critical efficiency drop in WR1 contract 8 weeks before mainstream consensus. Asset traded at peak perceived value."
        }
    },
    {
        id: "agent",
        title: "The Agent",
        icon: Briefcase,
        color: "text-emerald-400",
        border: "border-emerald-500/30",
        bg: "bg-emerald-500/10",
        gradient: "from-emerald-600 to-teal-600",
        path: "/dashboard/agent",
        tagline: "Surplus Value Maximization",
        description: "Find the exact franchises with the cap space and schematic need for your client's unique production profile.",
        proofOfAlpha: {
            title: "Contract Surplus Secured",
            metric: "18.5%",
            subtitle: "Premium over Market Average",
            details: "Matched client's elite pressure metrics with a team projecting $32M in cap space and a bottom-tier pass rush. Secured Top-5 APY."
        }
    },
    {
        id: "bettor",
        title: "The Sharp",
        icon: Activity,
        color: "text-rose-400",
        border: "border-rose-500/30",
        bg: "bg-rose-500/10",
        gradient: "from-rose-600 to-red-600",
        path: "/dashboard/bettor",
        tagline: "Volatility & Pricing Alpha",
        description: "Exploit the lag between point-in-time machine learning predictions and the slow-moving media consensus.",
        proofOfAlpha: {
            title: "Market Inefficiency Exploited",
            metric: "4.2% EV",
            subtitle: "Lead Time Alpha",
            details: "Model detected severe athletic decline in starting RB. Shorted related props 3 weeks before injury/benching hit the news cycle."
        }
    },
    {
        id: "fan",
        title: "The Armchair GM",
        icon: User,
        color: "text-amber-400",
        border: "border-amber-500/30",
        bg: "bg-amber-500/10",
        gradient: "from-amber-600 to-orange-600",
        path: "/dashboard/fan",
        tagline: "Unbiased Player Grades",
        description: "Cut through the punditry. Access the coldest, most ruthless algorithmic grades of every contract on your team.",
        proofOfAlpha: {
            title: "Trade Grade Accuracy",
            metric: "A+",
            subtitle: "Algorithmic Verification",
            details: "Validated public sentiment: The algorithm confirms your team's latest blockbuster trade was a massive overpay in guaranteed money."
        }
    }
];

export function PersonaShowcase() {
    const router = useRouter();
    const [activeIndex, setActiveIndex] = useState(0);

    const activePersona = PERSONAS[activeIndex];
    const Icon = activePersona.icon;

    const handleSelectPersona = (path: string) => {
        router.push(path);
    };

    return (
        <section id="personas" className="w-full relative overflow-hidden flex flex-col justify-center bg-black py-24 border-t border-white/10">
            {/* Background effects */}
            <div className={`absolute top-0 right-0 w-full h-[500px] bg-gradient-to-bl ${activePersona.gradient} opacity-10 blur-[120px] pointer-events-none transition-all duration-1000`} />
            <div className="absolute inset-0 bg-[url('/grid.svg')] bg-center [mask-image:linear-gradient(180deg,white,rgba(255,255,255,0))]" />

            <div className="relative z-10 w-full max-w-7xl mx-auto px-6">
                
                {/* Header CTA */}
                <div className="text-center mb-16 space-y-4">
                    <Badge variant="outline" className={`bg-black text-slate-300 font-mono tracking-widest uppercase transition-colors duration-500 border-white/20 hover:${activePersona.border}`}>
                        Persona Entry Points
                    </Badge>
                    <h2 className="text-5xl md:text-7xl font-black tracking-tighter">
                        Choose your <span className={`text-transparent bg-clip-text bg-gradient-to-r ${activePersona.gradient} transition-all duration-700`}>Context.</span>
                    </h2>
                    <p className="text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed">
                        Cap Alpha Protocol is a multi-dimensional analytics engine. 
                        Your tools, telemetry, and permissions adapt to your specific role in the ecosystem.
                    </p>
                </div>

                {/* The Interactive Interface */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                    
                    {/* Left: Toggles */}
                    <div className="lg:col-span-5 flex flex-col gap-3">
                        {PERSONAS.map((persona, idx) => {
                            const PIcon = persona.icon;
                            const isActive = idx === activeIndex;
                            return (
                                <button
                                    key={persona.id}
                                    onClick={() => setActiveIndex(idx)}
                                    className={`relative flex items-center justify-between p-6 rounded-xl border transition-all duration-300 text-left group overflow-hidden ${
                                        isActive 
                                        ? `bg-slate-900 border-white/20 shadow-xl scale-100` 
                                        : `bg-transparent border-transparent hover:bg-white/5 opacity-60 hover:opacity-100 scale-95`
                                    }`}
                                >
                                    {isActive && (
                                        <div className={`absolute left-0 top-0 bottom-0 w-1 ${persona.bg} border-l-2 ${persona.border} shadow-[0_0_15px_currentColor] ${persona.color}`} />
                                    )}
                                    <div className="flex items-center gap-4 relative z-10">
                                        <div className={`p-3 rounded-lg ${isActive ? persona.bg : 'bg-white/5 group-hover:bg-white/10'} transition-colors`}>
                                            <PIcon className={`w-6 h-6 ${isActive ? persona.color : 'text-slate-500 group-hover:text-slate-300'}`} />
                                        </div>
                                        <div>
                                            <h3 className={`text-xl font-bold ${isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'}`}>
                                                {persona.title}
                                            </h3>
                                            <p className={`text-sm ${isActive ? persona.color : 'text-slate-600'} font-mono mt-1`}>
                                                {persona.tagline}
                                            </p>
                                        </div>
                                    </div>
                                    <ChevronRight className={`w-5 h-5 transition-transform duration-300 ${isActive ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-4'}`} />
                                </button>
                            );
                        })}
                    </div>

                    {/* Right: Dynamic Persona Display */}
                    <div className="lg:col-span-7 relative h-full min-h-[450px]">
                        <Card className={`h-full border border-white/10 bg-black/50 backdrop-blur-2xl overflow-hidden transition-all duration-500 shadow-2xl ${activePersona.border}`}>
                            <CardContent className="p-8 md:p-12 flex flex-col h-full justify-between relative relative z-10">
                                {/* Top Content */}
                                <div>
                                    <div className="flex items-center gap-3 mb-6">
                                        <div className={`p-2 rounded border ${activePersona.border} ${activePersona.bg}`}>
                                            <Icon className={`w-8 h-8 ${activePersona.color}`} />
                                        </div>
                                        <h2 className="text-3xl font-bold tracking-tight text-white">{activePersona.title}</h2>
                                    </div>
                                    <p className="text-xl text-slate-300 leading-relaxed mb-10 min-h-[80px]">
                                        {activePersona.description}
                                    </p>

                                    {/* Proof of Alpha Receipt */}
                                    <div className={`p-6 rounded-lg bg-zinc-950 border ${activePersona.border} mb-8 shadow-inner`}>
                                        <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4 pb-2 border-b border-white/5">
                                            Historical Receipt
                                        </h4>
                                        <div className="flex flex-col md:flex-row gap-6 md:items-center">
                                            <div className="flex flex-col">
                                                <span className={`text-4xl font-black ${activePersona.color} tracking-tight`}>
                                                    {activePersona.proofOfAlpha.metric}
                                                </span>
                                                <span className="text-xs font-mono text-slate-400 mt-1 uppercase">
                                                    {activePersona.proofOfAlpha.subtitle}
                                                </span>
                                            </div>
                                            <div className="w-px h-16 bg-white/10 hidden md:block" />
                                            <p className="text-sm text-slate-300 leading-relaxed flex-1 italic">
                                                "{activePersona.proofOfAlpha.details}"
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Bottom Action (Enter Dashboard) */}
                                <div>
                                    <SignedOut>
                                        <SignInButton mode="modal" fallbackRedirectUrl={activePersona.path} signUpFallbackRedirectUrl={activePersona.path}>
                                            <Button className={`w-full py-8 text-lg font-bold bg-gradient-to-r ${activePersona.gradient} hover:opacity-90 text-white shadow-lg shadow-black/50 border-0 uppercase tracking-widest rounded-xl transition-all hover:scale-[1.02] active:scale-95`}>
                                                Enter the {activePersona.title} Dashboard
                                            </Button>
                                        </SignInButton>
                                    </SignedOut>
                                    <SignedIn>
                                        <Link href={activePersona.path} className="w-full block">
                                            <Button className={`w-full py-8 text-lg font-bold bg-gradient-to-r ${activePersona.gradient} hover:opacity-90 text-white shadow-lg shadow-black/50 border-0 uppercase tracking-widest rounded-xl transition-all hover:scale-[1.02] active:scale-95`}>
                                                Enter the {activePersona.title} Dashboard
                                            </Button>
                                        </Link>
                                    </SignedIn>
                                    <p className="text-center text-xs text-slate-500 font-mono mt-4">
                                        Standard Executive Authentication via Clerk
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                </div>
            </div>
        </section>
    );
}
