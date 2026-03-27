"use client";

import { useState, useRef, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, TrendingUp, AlertTriangle, Activity, Radar, X, Newspaper } from "lucide-react";
import Link from "next/link";
import { ImageWithFallback } from "./image-with-fallback";
import { ProvenanceSnapshot } from "./provenance-snapshot";
import { slugify } from "@/lib/utils";

const DISLOCATIONS = [
    {
        id: "watson",
        name: "Deshaun Watson",
        team: "CLE",
        image: "deshaun_watson.jpg",
        prediction: "CRITICAL SELL",
        metric: "-$42.5M",
        color: "text-rose-500",
        icon: TrendingDown,
        insight: "Efficiency gap expanding. Structurally untradable.",
        news: [
            "Browns cap liability reaches historic levels, models suggest dead cap acceleration is inevitable.",
            "Offensive efficiency strictly negatively correlated with Watson's snap count in Q4.",
            "Restructure options mathematically exhausted; future guarantees lock in long-term dislocation."
        ]
    },
    {
        id: "jones",
        name: "Daniel Jones",
        team: "NYG",
        image: "daniel_jones.jpg",
        prediction: "LIQUIDATE",
        metric: "-$38.0M",
        color: "text-orange-500",
        icon: AlertTriangle,
        insight: "Catastrophic guarantee execution trigger imminent.",
        news: [
            "Injury guarantees threaten to execute next week, triggering $23M in unavoidable future liability.",
            "Front office actively exploring benching to preserve organizational optionality.",
            "Production models show output matches replacement-level free agent QB (Value: $4M)."
        ]
    },
    {
        id: "wilson",
        name: "Russell Wilson",
        team: "DEN",
        image: "russell_wilson.jpg",
        prediction: "TOXIC ASSET",
        metric: "-$85.0M",
        color: "text-red-600",
        icon: TrendingDown,
        insight: "Historic dead cap realization predicted.",
        news: [
            "Denver officially absorbing the largest dead cap charge in NFL history ($85M).",
            "Advanced models signaled velocity decline 18 months prior to public consensus.",
            "Structural roster damage limits free agency optionality for next two cycles."
        ]
    },
    {
        id: "kamara",
        name: "Alvin Kamara",
        team: "NO",
        image: "alvin_kamara.jpg",
        prediction: "CRITICAL SELL",
        metric: "-$18.5M",
        color: "text-rose-500",
        icon: TrendingDown,
        insight: "Efficiency metrics collapsed despite volume preservation.",
        news: [
            "Rush Yards Over Expected (RYOE) dropped to career lows despite volume remaining stable.",
            "New Orleans salary cap restructure cycles have pushed critical void year hits into current ledger.",
            "Running back aging curve indicates non-recoverable decay trajectory."
        ]
    },
    {
        id: "miller",
        name: "Von Miller",
        team: "BUF",
        image: "von_miller.jpg",
        prediction: "LIQUIDATE",
        metric: "-$14.2M",
        color: "text-orange-500",
        icon: AlertTriangle,
        insight: "Age curve acceleration detected in pass rush win rate.",
        news: [
            "Pass Rush Win Rate (PRWR) plummeted post-injury to bottom 15th percentile.",
            "Buffalo's defensive line efficiency actually improves when asset is off the field geometrically.",
            "Cap savings via Post-June 1 cut far outweigh empirical on-field surplus value."
        ]
    },
    {
        id: "elliott",
        name: "Ezekiel Elliott",
        team: "DAL",
        image: "ezekiel_elliott.jpg",
        prediction: "VALUE SURPLUS",
        metric: "+$4.5M",
        color: "text-emerald-500",
        icon: TrendingUp,
        insight: "Situational leverage creates point-in-time surplus value.",
        news: [
            "Veteran minimum contract guarantees hyper-efficient short-yardage situational conversions.",
            "Return to original scheme masks athletic decay; asset utilization optimized perfectly.",
            "Zero dead-cap liability makes this a pure asymmetric upside holding."
        ]
    },
    {
        id: "rodgers",
        name: "Aaron Rodgers",
        team: "NYJ",
        image: "aaron_rodgers.jpg",
        prediction: "UNDERVALUED",
        metric: "+$12.0M",
        color: "text-emerald-500",
        icon: TrendingUp,
        insight: "Pre-season variance is mispriced by current consensus.",
        news: [
            "Media sentiment heavily indexes Achilles injury, ignoring intact throwing mechanics.",
            "Mathematical leverage of supporting cast (Wilson, Hall) artificially props up floor.",
            "Restructured contract actually provides elite APY flexibility for 2025 cap window."
        ]
    },
    {
        id: "lattimore",
        name: "Marshon Lattimore",
        team: "NO",
        image: "marshon_lattimore.jpg",
        prediction: "TOXIC ASSET",
        metric: "-$15.2M",
        color: "text-red-600",
        icon: AlertTriangle,
        insight: "Recurring soft-tissue history heavily correlated with cap liability.",
        news: [
            "Coverage metrics still elite, but availability coefficient wipes out surplus value entirely.",
            "Dead cap prorations limit New Orleans' ability to pivot defensively.",
            "Market trade value significantly lower than internal ledger valuation."
        ]
    }
];

export function AlphaFeedHero() {
    return (
        <section className="relative w-full pt-24 pb-12 px-4 lg:px-8 bg-black overflow-hidden flex flex-col">
            <div className="relative z-10 w-full max-w-7xl mx-auto space-y-4 mb-8">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-3">
                        <Radar className="w-5 h-5 text-emerald-500 animate-pulse" />
                        <h1 className="text-xl md:text-2xl font-mono tracking-tighter text-emerald-400 drop-shadow-sm uppercase">
                            Terminal Alpha Feed // Live Dislocations
                        </h1>
                    </div>
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/30 font-mono tracking-widest uppercase py-1 px-3">
                        SYS: ONLINE | T-0.1ms
                    </Badge>
                </div>
                <p className="text-sm font-mono text-zinc-500 max-w-4xl leading-relaxed">
                    MARKET INEFFICIENCY SENSORS ACTIVE. Synthesizing real-time telemetry against ledger constraints.
                </p>
            </div>

            <div className="relative z-10 w-full max-w-7xl mx-auto">
                <div className="overflow-x-auto rounded border border-zinc-800 bg-zinc-950/50">
                    <table className="w-full text-left font-mono text-xs md:text-sm">
                        <thead className="bg-zinc-900 text-zinc-400 border-b border-zinc-800 uppercase tracking-widest">
                            <tr>
                                <th className="p-3 font-semibold">Asset ID</th>
                                <th className="p-3 font-semibold hidden sm:table-cell">Team</th>
                                <th className="p-3 font-semibold">Signal</th>
                                <th className="p-3 font-semibold text-right">Proj. Liability/Surplus</th>
                                <th className="p-3 font-semibold hidden md:table-cell">Structural Logic</th>
                                <th className="p-3 font-semibold text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800/50">
                            {DISLOCATIONS.map((asset, i) => {
                                const Icon = asset.icon;
                                const isNegative = asset.metric.includes('-');
                                return (
                                    <tr key={asset.id} className="hover:bg-zinc-900/50 transition-colors group">
                                        <td className="p-3 font-bold text-zinc-200">
                                            <Link href={`/player/${slugify(asset.name)}`} className="hover:text-emerald-400 group-hover:underline">
                                                {asset.name}
                                            </Link>
                                        </td>
                                        <td className="p-3 text-zinc-500 hidden sm:table-cell">{asset.team}</td>
                                        <td className="p-3">
                                            <div className="flex items-center gap-2">
                                                <Icon className={`w-3 h-3 ${asset.color}`} />
                                                <span className={`${asset.color} font-bold`}>{asset.prediction}</span>
                                            </div>
                                        </td>
                                        <td className={`p-3 text-right font-black ${isNegative ? 'text-rose-500' : 'text-emerald-500'}`}>
                                            {asset.metric}
                                        </td>
                                        <td className="p-3 text-zinc-400 hidden md:table-cell truncate max-w-md">
                                            {asset.insight}
                                        </td>
                                        <td className="p-3 text-right">
                                            <Link href={`/player/${slugify(asset.name)}`} className="text-[10px] bg-zinc-900 border border-zinc-700 hover:border-emerald-500 hover:text-emerald-400 px-2 py-1 rounded transition-colors uppercase tracking-widest">
                                                Trace
                                            </Link>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}
