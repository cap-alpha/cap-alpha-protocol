import Link from "next/link";

export interface PunditResult {
    id: string;
    slug: string;
    name: string;
    outlet: string;
    accuracy: number;        // 0-1
    totalClaims: number;
    correctClaims: number;
    incorrectClaims: number;
}

function getInitials(name: string): string {
    return name
        .split(" ")
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() ?? "")
        .join("");
}

function AccuracyColor(accuracy: number): string {
    if (accuracy >= 0.6) return "var(--search-pos)";
    if (accuracy >= 0.45) return "var(--search-warn)";
    return "var(--search-neg)";
}

export function SearchPunditCard({ pundit }: { pundit: PunditResult }) {
    const pct = Math.round(pundit.accuracy * 100);
    const accColor = AccuracyColor(pundit.accuracy);
    const initials = getInitials(pundit.name);

    return (
        <Link
            href={`/ledger/${encodeURIComponent(pundit.slug)}`}
            className="flex items-center justify-between mb-3 px-5 py-4 no-underline transition-colors"
            style={{
                background: "#fff",
                border: "1px solid var(--search-border)",
                color: "inherit",
                display: "flex",
            }}
        >
            {/* Left: avatar + name */}
            <div className="flex items-center gap-3.5">
                <div
                    className="w-11 h-11 rounded-full flex items-center justify-center text-base font-black border-2 shrink-0"
                    style={{
                        background:
                            "linear-gradient(135deg, var(--search-navy-lt), var(--search-navy))",
                        borderColor: "var(--search-gold)",
                        fontFamily: "'Playfair Display', serif",
                        color: "var(--search-gold-lt)",
                    }}
                    aria-hidden="true"
                >
                    {initials}
                </div>
                <div>
                    <p
                        className="text-[17px] font-bold leading-tight"
                        style={{
                            fontFamily: "'Playfair Display', serif",
                            color: "var(--search-navy)",
                        }}
                    >
                        {pundit.name}
                    </p>
                    <p className="text-[12px]" style={{ color: "var(--search-lt)" }}>
                        {pundit.outlet}
                    </p>
                </div>
            </div>

            {/* Right: stats */}
            <div className="flex gap-6 items-center">
                <div className="text-right">
                    <p
                        className="text-lg font-semibold tabular-nums"
                        style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            color: accColor,
                        }}
                    >
                        {pct}%
                    </p>
                    <p
                        className="text-[10px] uppercase tracking-[1px] mt-0.5"
                        style={{ color: "var(--search-lt)" }}
                    >
                        Accuracy
                    </p>
                </div>
                <div className="text-right">
                    <p
                        className="text-lg font-semibold tabular-nums"
                        style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            color: "var(--search-navy)",
                        }}
                    >
                        {pundit.totalClaims}
                    </p>
                    <p
                        className="text-[10px] uppercase tracking-[1px] mt-0.5"
                        style={{ color: "var(--search-lt)" }}
                    >
                        Claims
                    </p>
                </div>
                <div className="text-right">
                    <p
                        className="text-lg font-semibold tabular-nums"
                        style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            color: "var(--search-pos)",
                        }}
                    >
                        {pundit.correctClaims}
                    </p>
                    <p
                        className="text-[10px] uppercase tracking-[1px] mt-0.5"
                        style={{ color: "var(--search-lt)" }}
                    >
                        Correct
                    </p>
                </div>
            </div>
        </Link>
    );
}
