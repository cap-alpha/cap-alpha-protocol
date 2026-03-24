"use client";

import { useState, useEffect } from "react";
import { SignInButton } from "@clerk/nextjs";
import { WaitlistForm } from "./waitlist-form";
import { Button } from "@/components/ui/button";
import { Clock, TrendingDown, MessageSquareWarning, ChevronLeft, ChevronRight, Twitter, Pause, Play, Heart, Repeat, MessageSquare, Calendar } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { slugify } from "@/lib/utils";

type Tweet = {
    text: string;
    author: string;
    url: string;
    source: string;
    likes: string;
    reposts: string;
};

type Receipt = {
    id: number;
    date: string;
    player_name: string;
    team: string;
    contract_size: string;
    prediction: string;
    media_sentiment: string;
    cap_alpha_insight: string;
    outcome: string;
    outcome_date?: string;
    roi: string;
    trend: string;
    image_url?: string;
    image_position?: string;
    tweets: Tweet[];
};

export function LandingHero({ receipts }: { receipts: Receipt[] }) {
    const RECEIPTS = receipts;
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isPaused, setIsPaused] = useState(false);

    // Auto-rotate every 8 seconds
    useEffect(() => {
        if (isPaused) return;
        const timer = setInterval(() => {
            setCurrentIndex((prev) => (prev + 1) % RECEIPTS.length);
        }, 8000);
        return () => clearInterval(timer);
    }, [isPaused]);

    const nextSlide = () => {
        setCurrentIndex((prev) => (prev + 1) % RECEIPTS.length);
        setIsPaused(true);
    };
    const prevSlide = () => {
        setCurrentIndex((prev) => (prev - 1 + RECEIPTS.length) % RECEIPTS.length);
        setIsPaused(true);
    };

    const currentReceipt = RECEIPTS[currentIndex];

    return (
        <main className="min-h-[100dvh] bg-black text-white relative overflow-hidden flex flex-col">

            {/* Background Images Carousel */}
            {RECEIPTS.map((receipt, idx) => (
                <div
                    key={receipt.id}
                    className={`absolute inset-0 transition-opacity duration-1000 ease-in-out ${idx === currentIndex ? 'opacity-30' : 'opacity-0'}`}
                    style={{
                        backgroundImage: `url('/players/${receipt.player_name.toLowerCase().replace(" ", "_").replace("'", "")}.jpg')`,
                        backgroundSize: 'cover',
                        backgroundPosition: (receipt as any).image_position || 'center',
                    }}
                />
            ))}

            {/* Top Header */}
            <header className="w-full flex justify-between items-center py-4 px-8 border-b border-white/10 relative z-20 bg-black/50 backdrop-blur-sm">
                <div className="text-xl font-bold font-mono tracking-tight text-emerald-500">CAP ALPHA PROTOCOL</div>
                <nav className="flex items-center gap-6 text-sm">
                    <a href="/legal/terms" className="hover:text-emerald-500 transition-colors">Terms of Service</a>
                    <SignInButton mode="modal" fallbackRedirectUrl="/dashboard" signUpFallbackRedirectUrl="/dashboard">
                        <button className="bg-emerald-500 hover:bg-emerald-600 text-black font-semibold h-10 px-4 py-2 rounded-md inline-flex items-center justify-center transition-colors">
                            Executive Login
                        </button>
                    </SignInButton>
                </nav>
            </header>

            {/* Main Content Area */}
            <div className="relative z-10 flex-grow flex flex-col items-center justify-start pt-24 px-8 pb-8 lg:px-16 lg:pt-32">

                {/* Hero Text */}
                <div className="text-center space-y-6 max-w-4xl mb-16">
                    <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-teal-200 pb-2">
                        The Signal in the Noise.
                    </h1>
                    <p className="text-xl md:text-2xl text-slate-300 leading-relaxed max-w-3xl mx-auto">
                        Actionable, point-in-time analytics for NFL Roster construction.
                        We expose what the prevailing wisdom misses, saving teams millions.
                    </p>
                    <div className="pt-8 w-full max-w-2xl mx-auto">
                        <WaitlistForm />
                    </div>
                </div>

                {/* Rotating Ledger & Tweets Overlay */}
                <div className="w-full max-w-7xl relative flex flex-col lg:flex-row items-stretch gap-8">

                    {/* Left Navigation Arrow (Global) */}
                    <div className="absolute top-1/2 -translate-y-1/2 -left-16 hidden xl:flex z-50">
                        <Button variant="ghost" size="icon" onClick={prevSlide} className="rounded-full h-12 w-12 border border-white/20 bg-black/50 backdrop-blur-md text-white hover:bg-white/10 hover:text-white shadow-xl transition-all hover:scale-110">
                            <ChevronLeft className="h-6 w-6" />
                        </Button>
                    </div>

                    {/* Right Navigation Arrow (Global) */}
                    <div className="absolute top-1/2 -translate-y-1/2 -right-16 hidden xl:flex z-50">
                        <Button variant="ghost" size="icon" onClick={nextSlide} className="rounded-full h-12 w-12 border border-white/20 bg-black/50 backdrop-blur-md text-white hover:bg-white/10 hover:text-white shadow-xl transition-all hover:scale-110">
                            <ChevronRight className="h-6 w-6" />
                        </Button>
                    </div>

                    {/* Unified Ledger Receipt Card */}
                    <div className="w-full relative group min-h-[500px]">
                        <Card className="bg-black/60 backdrop-blur-xl border border-white/10 overflow-hidden relative shadow-2xl h-full w-full">
                            <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/20 rounded-full blur-[100px] pointer-events-none -mr-32 -mt-32" />

                            <CardContent className="p-0 h-full flex flex-col">
                                <div className="grid lg:grid-cols-3 flex-grow">

                                    {/* Column 1: Prevailing Wisdom (Tweets) */}
                                    <div className="p-8 border-b lg:border-b-0 lg:border-r border-white/10 bg-black/40 flex flex-col justify-start relative">
                                        <div className="flex items-center gap-3 mb-6">
                                            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-800 text-slate-300 font-bold border border-slate-700 shadow-lg">1</span>
                                            <h3 className="text-sm font-bold uppercase tracking-widest text-slate-400 drop-shadow-md">
                                                Prevailing Wisdom
                                            </h3>
                                        </div>
                                        <div className="flex flex-col gap-4 flex-grow">
                                            {currentReceipt.tweets.map((tweet, i) => (
                                                <a key={i} href={tweet.url} target="_blank" rel="noopener noreferrer" className="block relative group/tweet">
                                                    <Card className="bg-black/40 backdrop-blur-md border-white/10 group-hover/tweet:border-sky-500/50 group-hover/tweet:bg-black/60 transition-all shadow-xl">
                                                        <CardContent className="p-4 flex items-start gap-3">
                                                            {tweet.source === 'twitter' ? (
                                                                <Twitter className="w-5 h-5 text-sky-400 group-hover/tweet:text-sky-300 shrink-0 mt-1 transition-colors" />
                                                            ) : (
                                                                <MessageSquare className="w-5 h-5 text-orange-500 group-hover/tweet:text-orange-400 shrink-0 mt-1 transition-colors" />
                                                            )}
                                                            <div className="flex flex-col gap-1 w-full">
                                                                <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider group-hover/tweet:text-slate-400 transition-colors">{tweet.author}</span>
                                                                <p className="text-sm text-slate-200 leading-relaxed font-sans italic group-hover/tweet:text-white transition-colors">"{tweet.text}"</p>
                                                                <div className="flex items-center gap-4 mt-2 text-xs text-slate-500 group-hover/tweet:text-slate-400 font-mono">
                                                                    <div className="flex items-center gap-1">
                                                                        {tweet.source === 'twitter' ? <Repeat className="w-3 h-3" /> : <MessageSquare className="w-3 h-3" />}
                                                                        {tweet.reposts}
                                                                    </div>
                                                                    <div className="flex items-center gap-1">
                                                                        <Heart className="w-3 h-3" />
                                                                        {tweet.likes}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </CardContent>
                                                    </Card>
                                                </a>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Column 2: Our Prediction */}
                                    <div className="p-8 border-b lg:border-b-0 lg:border-r border-white/10 bg-white/5 flex flex-col justify-start relative">
                                        <div className="flex items-center gap-3 mb-6">
                                            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.2)]">2</span>
                                            <h3 className="text-sm font-bold uppercase tracking-widest text-emerald-400">
                                                Our Prediction
                                            </h3>
                                        </div>
                                        <Badge variant="outline" className="w-fit mb-4 bg-black/50 px-3 py-1 font-mono text-emerald-400 border-emerald-500/30">
                                            <Clock className="w-3 h-3 mr-2" />
                                            Point-in-Time: {currentReceipt.date}
                                        </Badge>
                                        <h3 className="text-4xl font-black tracking-tight text-white mb-2">
                                            <Link 
                                                href={`/player/${encodeURIComponent(slugify(currentReceipt.player_name))}`}
                                                className="hover:underline hover:text-emerald-400 transition-colors pointer-events-auto"
                                            >
                                                {currentReceipt.player_name}
                                            </Link>
                                        </h3>
                                        <p className="text-emerald-500 font-mono text-sm mb-6">{currentReceipt.team} | TCV: {currentReceipt.contract_size}</p>
                                        <div className="mb-6">
                                            <span className="inline-flex items-center px-4 py-2 rounded-md text-sm font-bold bg-red-500/20 text-red-400 border border-red-500/30">
                                                <TrendingDown className="w-4 h-4 mr-2" />
                                                {currentReceipt.prediction}
                                            </span>
                                        </div>
                                        <div>
                                            <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-500 mb-2">
                                                Cap Alpha Insight
                                            </h4>
                                            <p className="text-md font-medium text-slate-300">{currentReceipt.cap_alpha_insight}</p>
                                        </div>
                                    </div>

                                    {/* Column 3: The Truth */}
                                    <div className="p-8 flex flex-col justify-start relative z-10">
                                        <div className="flex items-center gap-3 mb-6">
                                            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-white/10 text-white/80 font-bold border border-white/20 shadow-lg">3</span>
                                            <h3 className="text-sm font-bold uppercase tracking-widest text-white/80">
                                                What Actually Happened
                                            </h3>
                                        </div>
                                        <div className="space-y-6">
                                            <div>
                                                {currentReceipt.outcome_date && (
                                                    <div className="flex items-center gap-2 mb-3 text-sm font-mono text-slate-400">
                                                        <Calendar className="w-4 h-4" />
                                                        Resolution Date: {currentReceipt.outcome_date}
                                                    </div>
                                                )}
                                                <p className="text-md text-slate-300 mb-4">{currentReceipt.outcome}</p>
                                                <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-md">
                                                    <h4 className="text-[10px] font-bold uppercase text-emerald-500 mb-1">Impact of Ignoring Cap Alpha</h4>
                                                    <p className="text-sm font-mono text-emerald-400">{currentReceipt.roi}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>

                {/* Navigation Dots */}
                <div className="flex justify-center items-center gap-3 mt-12 relative z-[60] pointer-events-auto">
                    <button
                        onClick={() => setIsPaused(prev => !prev)}
                        className="flex items-center gap-2 px-4 py-2 bg-zinc-900/80 hover:bg-zinc-800 border border-white/10 rounded-full text-white/80 hover:text-white transition-all shadow-lg backdrop-blur-md font-mono text-xs tracking-widest mr-4"
                        aria-label={isPaused ? "Play" : "Pause"}
                    >
                        {isPaused ? (
                            <>
                                <Play className="h-3 w-3 fill-emerald-500 text-emerald-500" />
                                <span>PLAY</span>
                            </>
                        ) : (
                            <>
                                <Pause className="h-3 w-3 fill-zinc-400 text-zinc-400" />
                                <span>PAUSE</span>
                            </>
                        )}
                    </button>
                    {RECEIPTS.map((_, idx) => (
                        <button
                            key={idx}
                            onClick={() => {
                                setCurrentIndex(idx);
                                setIsPaused(true);
                            }}
                            className={`h-2 rounded-full transition-all duration-300 ${idx === currentIndex ? "bg-emerald-500 w-8" : "bg-white/20 w-2 hover:bg-white/50"
                                }`}
                            aria-label={`Go to slide ${idx + 1}`}
                        />
                    ))}
                </div>

            </div>
        </main>
    );
}
