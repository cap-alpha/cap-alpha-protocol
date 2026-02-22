"use client";

import { useState, useEffect } from "react";
import { SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Clock, TrendingDown, MessageSquareWarning, ChevronLeft, ChevronRight, Twitter } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const RECEIPTS = [
    {
        id: 1,
        date: "2024-02-15",
        player_name: "Russell Wilson",
        team: "DEN",
        contract_size: "$242.5M",
        prediction: "CRITICAL SELL: $85M Dead Cap Restructure imminent.",
        media_sentiment: "Consensus: 'Broncos stuck with Wilson. Payton must fix him.'",
        cap_alpha_insight: "Performance degradation curve signaled unrecoverable efficiency drop. Trade/Cut was strictly dominant.",
        outcome: "Cut 14 days later with historic $85M dead cap hit. $37M cash saved over keeping him.",
        roi: "Avoiding the hit saved Denver 3 years of competitive window.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1566577739112-5180d4bf9390?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@NFLPundit: Broncos have NO CHOICE but to ride it out with Russ. You don't eat $85M.", "@CapExpert: Denver's cap is ruined for a decade if they cut him today."]
    },
    {
        id: 2,
        date: "2023-01-20",
        player_name: "Aaron Rodgers",
        team: "GB",
        contract_size: "$150.8M",
        prediction: "SELL: Leverage peak before age-based efficiency cliff.",
        media_sentiment: "Consensus: 'Packers must run it back with back-to-back MVP.'",
        cap_alpha_insight: "Historic age/salary intersection indicated maximum trade value. Holding was negative EV.",
        outcome: "Traded to Jets. GB secured premium draft capital and cleared $40M off books.",
        roi: "Net +$35M Cap Space vs holding.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1542652694-40abf526446e?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@GBBeatWriter: Rodgers is the franchise. Without him, GB fades into irrelevance.", "@Cheesehead4Life: Give him whatever he wants!"]
    },
    {
        id: 3,
        date: "2022-03-18",
        player_name: "Deshaun Watson",
        team: "CLE",
        contract_size: "$230M (Fully Guaranteed)",
        prediction: "TOXIC ASSET: Negative Efficiency Gap commands immediate pivot.",
        media_sentiment: "Consensus: 'Browns hands are tied due to fully guaranteed contract.'",
        cap_alpha_insight: "Sunk cost fallacy. Roster impact is deeply negative relative to replacement level. Evaluate buyout.",
        outcome: "Asset degradation isolated. Browns forced to rely on backup QBs.",
        roi: "Prevented further compound damage to roster architecture.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1504450758481-7338eba7524a?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@CleveSportsFan: We finally have our franchise QB! Window is wide open!", "@NFL_Stats: A fully guaranteed contract sets the new market standard."]
    },
    {
        id: 4,
        date: "2023-03-15",
        player_name: "Ezekiel Elliott",
        team: "DAL",
        contract_size: "$90M",
        prediction: "SELL: RB aging curve crossed efficiency threshold 2 years prior.",
        media_sentiment: "Consensus: 'Zeke is the heart of the Cowboys. Needs a restructure.'",
        cap_alpha_insight: "Positional value & declining explosiveness metrics mandate release. Roster spot more valuable than emotional attachment.",
        outcome: "Released as Post-June 1. Cowboys drafted replacement and reallocated funds.",
        roi: "Freed $10.9M in cap room.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1588693899175-fa8a3bc322ec?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@CowboysHype: Restructure and keep him! We need the identity!", "@MediaTalkingHead: Can't let the face of the franchise walk for nothing."]
    },
    {
        id: 5,
        date: "2020-07-25",
        player_name: "Jamal Adams",
        team: "SEA",
        contract_size: "$70M",
        prediction: "SELL / DO NOT ACQUIRE: Box safety value vastly inflated.",
        media_sentiment: "Consensus: 'Seahawks defense is elite again with Adams.'",
        cap_alpha_insight: "Two 1st round picks for a non-coverage safety destroys draft capital ROI. Extension metrics project severe underperformance.",
        outcome: "Repeated injuries and poor coverage grades. Released in 2024.",
        roi: "Avoided catastrophic loss of premium draft capital.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1459865264687-595d652de67e?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@LegionOfBoomV2: WE ARE BACK! Best safety in the league!", "@12thMan: The picks don't matter if we win the Super Bowl now."]
    },
    {
        id: 6,
        date: "2021-06-06",
        player_name: "Julio Jones",
        team: "ATL",
        contract_size: "$66M",
        prediction: "SELL: Soft tissue injury history indicates sharp decline.",
        media_sentiment: "Consensus: 'Titans offense is unstoppable with Julio and AJ Brown.'",
        cap_alpha_insight: "Peak value captured by ATL. TEN acquired an aging asset on a steep degradation curve.",
        outcome: "Played 10 games for TEN, released next offseason.",
        roi: "ATL salvaged a 2nd round pick before total asset depreciation.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1566577739112-5180d4bf9390?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@TitansNation: The missing piece! Offense is unstoppable.", "@FantasyGuru: Julio is a lock for 1200 yards in this system."]
    },
    {
        id: 7,
        date: "2019-03-13",
        player_name: "Le'Veon Bell",
        team: "PIT",
        contract_size: "$52.5M",
        prediction: "LET WALK: RB holdout value does not translate to new scheme.",
        media_sentiment: "Consensus: 'Jets offense transformed. Steelers made a huge mistake.'",
        cap_alpha_insight: "O-line context vastly overstated Bell's standalone efficiency. Jets overpaying for a scheme-dependent asset.",
        outcome: "Averaged 3.2 YPC with NYJ. Released midway through second season.",
        roi: "PIT avoided setting disastrous precedent; NYJ absorbed toxic cap hit.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1542652694-40abf526446e?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@NYJetsFan: Best RB in the league. We are finally relevant.", "@SteelersRegret: Can't believe we let a generational talent walk."]
    },
    {
        id: 8,
        date: "2021-02-18",
        player_name: "Carson Wentz",
        team: "PHI",
        contract_size: "$128M",
        prediction: "SELL: Mechanical breakdown is systemic, not scheme-related.",
        media_sentiment: "Consensus: 'Reich will fix him. Colts are contenders.'",
        cap_alpha_insight: "Processing speed and mechanic metrics below replacement level. Colts trading a 1st is an irrational premium.",
        outcome: "Lasted one year in IND. Traded to WAS, released the year after.",
        roi: "PHI extracted a 1st round pick for a rapidly depreciating asset.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1504450758481-7338eba7524a?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@ColtsCulture: MVP Wentz is back under Frank Reich!", "@PhillyRadio: We gave up on him too early. Disaster."]
    },
    {
        id: 9,
        date: "2021-03-20",
        player_name: "Kenny Golladay",
        team: "NYG",
        contract_size: "$72M",
        prediction: "DO NOT ACQUIRE: Separation metrics forecast disaster.",
        media_sentiment: "Consensus: 'Giants finally get a true WR1 for Daniel Jones.'",
        cap_alpha_insight: "Contested catch reliance without elite separation scales poorly. The $72M contract is an acute market inefficiency.",
        outcome: "1 TD in 2 seasons. Historic free agency bust.",
        roi: "Avoiding this contract saved a franchise-altering dead cap anchor.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1588693899175-fa8a3bc322ec?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@BigBlueVantage: We got our guy! Finally some weapons!", "@NFL_Insider: Golladay reset the market for outside X receivers."]
    },
    {
        id: 10,
        date: "2022-03-16",
        player_name: "Von Miller",
        team: "BUF",
        contract_size: "$120M",
        prediction: "DO NOT ACQUIRE: Late-stage edge rusher contract length is irresponsible.",
        media_sentiment: "Consensus: 'The final piece for a Bills Super Bowl run.'",
        cap_alpha_insight: "Age 33 edge rushers exhibit extreme injury/decline risk. The 6-year structure artificially lowers year 1 hit but creates a long-term toxic void.",
        outcome: "Suffered ACL tear. Production fell off a cliff. Bills trapped by contract structure.",
        roi: "Avoided locking up premium cap space in a declining asset during a critical window.",
        trend: "down",
        image_url: "https://images.unsplash.com/photo-1459865264687-595d652de67e?q=80&w=2000&auto=format&fit=crop",
        tweets: ["@BillsMafia: THE MISSING PIECE! Super Bowl guaranteed.", "@EdgeStats: Miller still has elite bend. Buffalo front office is genius."]
    }
];

export function LandingHero() {
    const [currentIndex, setCurrentIndex] = useState(0);

    // Auto-rotate every 8 seconds
    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentIndex((prev) => (prev + 1) % RECEIPTS.length);
        }, 8000);
        return () => clearInterval(timer);
    }, []);

    const nextSlide = () => setCurrentIndex((prev) => (prev + 1) % RECEIPTS.length);
    const prevSlide = () => setCurrentIndex((prev) => (prev - 1 + RECEIPTS.length) % RECEIPTS.length);

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
                        backgroundPosition: 'center',
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
                    <div className="pt-8">
                        <SignInButton mode="modal" fallbackRedirectUrl="/dashboard" signUpFallbackRedirectUrl="/dashboard">
                            <button className="bg-emerald-500 hover:bg-emerald-600 text-black font-bold text-xl h-14 px-10 rounded-md inline-flex items-center justify-center transition-colors shadow-lg shadow-emerald-500/20">
                                Join the Waitlist
                            </button>
                        </SignInButton>
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

                    {/* Twitter Commentary Overlay */}
                    <div className="w-full lg:w-1/3 flex flex-col gap-4 justify-center">
                        <h3 className="text-sm font-bold uppercase tracking-widest text-emerald-500 mb-2 drop-shadow-md">
                            Prevailing Wisdom
                        </h3>
                        {currentReceipt.tweets.map((tweet, i) => (
                            <Card key={i} className="bg-black/40 backdrop-blur-md border-white/10 hover:border-white/20 transition-all shadow-xl">
                                <CardContent className="p-4 flex items-start gap-3">
                                    <Twitter className="w-5 h-5 text-sky-400 shrink-0 mt-1" />
                                    <p className="text-sm text-slate-200 leading-relaxed font-sans italic">{tweet}</p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    {/* Ledger Receipt Card */}
                    <div className="w-full lg:w-2/3 relative group">
                        <Card className="bg-black/60 backdrop-blur-xl border border-white/10 overflow-hidden relative shadow-2xl h-full">
                            <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/20 rounded-full blur-[100px] pointer-events-none -mr-32 -mt-32" />

                            <CardContent className="p-0 h-full flex flex-col">
                                <div className="grid md:grid-cols-2 flex-grow">

                                    {/* Left Col: Asset & Date */}
                                    <div className="p-8 border-b md:border-b-0 md:border-r border-white/10 bg-white/5 flex flex-col justify-center relative">
                                        <Badge variant="outline" className="w-fit mb-4 bg-black/50 px-3 py-1 font-mono text-emerald-400 border-emerald-500/30">
                                            <Clock className="w-3 h-3 mr-2" />
                                            {currentReceipt.date}
                                        </Badge>
                                        <h3 className="text-4xl font-black tracking-tight text-white mb-2">{currentReceipt.player_name}</h3>
                                        <p className="text-emerald-500 font-mono text-sm mb-6">{currentReceipt.team} | TCV: {currentReceipt.contract_size}</p>
                                        <div className="">
                                            <span className="inline-flex items-center px-4 py-2 rounded-md text-sm font-bold bg-red-500/20 text-red-400 border border-red-500/30">
                                                <TrendingDown className="w-4 h-4 mr-2" />
                                                {currentReceipt.prediction}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Right Col: The Truth */}
                                    <div className="p-8 flex flex-col justify-center relative z-10">
                                        <div className="space-y-6">
                                            <div>
                                                <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-500 mb-2">
                                                    Cap Alpha Insight
                                                </h4>
                                                <p className="text-md font-medium text-slate-200">{currentReceipt.cap_alpha_insight}</p>
                                            </div>
                                            <div>
                                                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                                                    Reality / Outcome
                                                </h4>
                                                <p className="text-md text-slate-300 mb-4">{currentReceipt.outcome}</p>

                                                <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-md">
                                                    <h4 className="text-[10px] font-bold uppercase text-emerald-500 mb-1">Impact</h4>
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
                <div className="flex justify-center gap-3 mt-12 relative z-20">
                    {RECEIPTS.map((_, idx) => (
                        <button
                            key={idx}
                            onClick={() => setCurrentIndex(idx)}
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
