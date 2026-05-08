"use client";

import { type SearchFilters } from "./SearchResults";

interface FilterPanelProps {
    filters: SearchFilters;
    onChange: (next: SearchFilters) => void;
}

interface CheckboxRowProps {
    label: string;
    checked: boolean;
    count?: number;
    onChange: (checked: boolean) => void;
}

function CheckboxRow({ label, checked, count, onChange }: CheckboxRowProps) {
    return (
        <div className="flex items-center justify-between py-1.5 cursor-pointer">
            <label
                className="flex items-center gap-2 text-[13px] cursor-pointer select-none"
                style={{ color: "var(--search-md)" }}
            >
                <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => onChange(e.target.checked)}
                    className="w-3.5 h-3.5"
                    style={{ accentColor: "var(--search-navy)" }}
                />
                {label}
            </label>
            {count !== undefined && (
                <span
                    className="text-[11px]"
                    style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        color: "var(--search-lt)",
                    }}
                >
                    {count}
                </span>
            )}
        </div>
    );
}

function GroupTitle({ children }: { children: React.ReactNode }) {
    return (
        <p
            className="text-[12px] font-bold tracking-[0.5px] uppercase pb-2 mb-2.5"
            style={{
                color: "var(--search-navy)",
                borderBottom: "1px solid var(--search-border)",
            }}
        >
            {children}
        </p>
    );
}

export function FilterPanel({ filters, onChange }: FilterPanelProps) {
    function toggle<K extends keyof SearchFilters>(
        key: K,
        value: string
    ) {
        const current = filters[key] as string[];
        const next = current.includes(value)
            ? current.filter((v) => v !== value)
            : [...current, value];
        onChange({ ...filters, [key]: next });
    }

    return (
        <aside className="sticky top-4 self-start">
            <p
                className="text-[11px] font-bold tracking-[2px] uppercase mb-3.5"
                style={{ color: "var(--search-lt)" }}
            >
                Filters
            </p>

            {/* Verdict */}
            <div className="mb-6">
                <GroupTitle>Verdict</GroupTitle>
                <CheckboxRow
                    label="Correct"
                    checked={filters.verdicts.includes("correct")}
                    count={218}
                    onChange={() => toggle("verdicts", "correct")}
                />
                <CheckboxRow
                    label="Incorrect"
                    checked={filters.verdicts.includes("incorrect")}
                    count={91}
                    onChange={() => toggle("verdicts", "incorrect")}
                />
                <CheckboxRow
                    label="Pending"
                    checked={filters.verdicts.includes("pending")}
                    count={33}
                    onChange={() => toggle("verdicts", "pending")}
                />
            </div>

            {/* Pundit */}
            <div className="mb-6">
                <GroupTitle>Pundit</GroupTitle>
                {[
                    { name: "Adam Schefter", count: 41 },
                    { name: "Shannon Sharpe", count: 29 },
                    { name: "Colin Cowherd", count: 67 },
                    { name: "Skip Bayless", count: 89 },
                    { name: "Peter King", count: 22 },
                ].map(({ name, count }) => (
                    <CheckboxRow
                        key={name}
                        label={name}
                        checked={filters.pundits.includes(name)}
                        count={count}
                        onChange={() => toggle("pundits", name)}
                    />
                ))}
                <a
                    href="#"
                    className="text-[12px] font-semibold mt-1 block"
                    style={{ color: "var(--search-gold)", textDecoration: "none" }}
                >
                    + 138 more pundits
                </a>
            </div>

            {/* Date Range */}
            <div className="mb-6">
                <GroupTitle>Date Range</GroupTitle>
                {[
                    "Last 30 days",
                    "2024–25 Season",
                    "2023–24 Season",
                    "All time",
                ].map((range) => (
                    <CheckboxRow
                        key={range}
                        label={range}
                        checked={filters.dateRanges.includes(range)}
                        onChange={() => toggle("dateRanges", range)}
                    />
                ))}
            </div>

            {/* Confidence */}
            <div className="mb-6">
                <GroupTitle>Confidence</GroupTitle>
                <CheckboxRow
                    label="High (0.8+)"
                    checked={filters.confidence.includes("high")}
                    count={124}
                    onChange={() => toggle("confidence", "high")}
                />
                <CheckboxRow
                    label="Medium (0.5–0.8)"
                    checked={filters.confidence.includes("medium")}
                    count={187}
                    onChange={() => toggle("confidence", "medium")}
                />
                <CheckboxRow
                    label="Low (<0.5)"
                    checked={filters.confidence.includes("low")}
                    count={31}
                    onChange={() => toggle("confidence", "low")}
                />
            </div>

            {/* Claim Type */}
            <div className="mb-6">
                <GroupTitle>Claim Type</GroupTitle>
                {[
                    "Game Outcome",
                    "Player Prop",
                    "Award",
                    "Trade / Move",
                    "Draft",
                ].map((type) => (
                    <CheckboxRow
                        key={type}
                        label={type}
                        checked={filters.claimTypes.includes(type)}
                        onChange={() => toggle("claimTypes", type)}
                    />
                ))}
            </div>
        </aside>
    );
}
