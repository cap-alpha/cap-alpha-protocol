"use client";

import { useRouter } from "next/navigation";
import { useRef, FormEvent, useState } from "react";

const EXAMPLE_QUERIES = [
    "Mahomes four Super Bowls",
    "Cowboys NFC Championship",
    "Skip Bayless wrong",
    "2024 NFL Draft",
    "LeBron retirement",
];

interface SearchBarProps {
    initialQuery?: string;
}

export function SearchBar({ initialQuery = "" }: SearchBarProps) {
    const router = useRouter();
    const inputRef = useRef<HTMLInputElement>(null);
    const [value, setValue] = useState(initialQuery);

    function handleSubmit(e: FormEvent<HTMLFormElement>) {
        e.preventDefault();
        const q = (inputRef.current?.value ?? "").trim();
        if (!q) return;
        router.push(`/search?q=${encodeURIComponent(q)}`);
    }

    function handleChipClick(chip: string) {
        setValue(chip);
        router.push(`/search?q=${encodeURIComponent(chip)}`);
    }

    return (
        <div className="w-full max-w-3xl mx-auto text-center">
            {/* Label */}
            <p
                className="text-[11px] font-bold tracking-[2px] uppercase mb-3"
                style={{ color: "var(--search-gold-lt)" }}
            >
                Prediction Search
            </p>

            {/* Title */}
            <h1
                className="font-serif text-4xl font-black text-white mb-6 leading-tight"
            >
                Find every pundit claim,
                <br />
                verified and scored
            </h1>

            {/* Input row */}
            <form onSubmit={handleSubmit} className="flex border-[3px] overflow-hidden" style={{ borderColor: "var(--search-gold)" }}>
                <input
                    ref={inputRef}
                    type="text"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder="Search claims, pundits, players, teams…"
                    className="flex-1 px-5 py-3.5 text-base outline-none"
                    style={{
                        background: "#fff",
                        color: "#1C1C1C",
                        fontFamily: "inherit",
                    }}
                    aria-label="Search predictions"
                />
                <button
                    type="submit"
                    className="px-6 text-[13px] font-bold tracking-[0.8px] uppercase whitespace-nowrap"
                    style={{
                        background: "var(--search-gold)",
                        color: "var(--search-navy)",
                    }}
                >
                    Search
                </button>
            </form>

            {/* Example chips */}
            <div className="mt-3.5 flex justify-center items-center gap-2.5 flex-wrap">
                <span className="text-[12px]" style={{ color: "rgba(255,255,255,.4)" }}>
                    Try:
                </span>
                {EXAMPLE_QUERIES.map((chip) => (
                    <button
                        key={chip}
                        type="button"
                        onClick={() => handleChipClick(chip)}
                        className="text-[12px] font-semibold px-3 py-1 transition-colors"
                        style={{
                            background: "rgba(255,255,255,.08)",
                            border: "1px solid rgba(255,255,255,.15)",
                            color: "rgba(255,255,255,.7)",
                        }}
                        onMouseEnter={(e) => {
                            (e.currentTarget as HTMLButtonElement).style.background =
                                "rgba(255,255,255,.15)";
                            (e.currentTarget as HTMLButtonElement).style.color = "#fff";
                        }}
                        onMouseLeave={(e) => {
                            (e.currentTarget as HTMLButtonElement).style.background =
                                "rgba(255,255,255,.08)";
                            (e.currentTarget as HTMLButtonElement).style.color =
                                "rgba(255,255,255,.7)";
                        }}
                    >
                        {chip}
                    </button>
                ))}
            </div>
        </div>
    );
}
