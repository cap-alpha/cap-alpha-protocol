import { ImageResponse } from "next/og";
import { NextRequest } from "next/server";
import { getStampConfig, getCacheControl, fmtDate } from "@/lib/og-helpers";

export const runtime = "edge";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PredictionData {
    prediction_hash_short: string;
    extracted_claim: string;
    pundit_name: string;
    resolution_status: string | null;
    ingestion_timestamp: string | null;
    source_published_at?: string | null;
    accuracy_rate?: number | null;
    total_predictions?: number | null;
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function GET(
    req: NextRequest,
    { params }: { params: { id: string } }
) {
    const { id } = params;

    // Fetch prediction from backend
    let prediction: PredictionData | null = null;
    try {
        const res = await fetch(
            `${API_URL}/v1/predictions/${encodeURIComponent(id)}`,
            { headers: { Accept: "application/json" } }
        );
        if (res.ok) {
            const data = await res.json();
            prediction = data.prediction ?? data ?? null;
        }
    } catch {
        // fall through to placeholder
    }

    // If prediction not found, render a placeholder card
    const claim = prediction?.extracted_claim ?? "Prediction not found";
    const punditName = prediction?.pundit_name ?? "Unknown Pundit";
    const status = prediction?.resolution_status ?? null;
    const madeDate = fmtDate(prediction?.source_published_at ?? prediction?.ingestion_timestamp);
    const accuracyPct =
        prediction?.accuracy_rate != null
            ? `${Math.round(prediction.accuracy_rate * 100)}%`
            : null;
    const totalPredictions = prediction?.total_predictions ?? null;

    const stamp = getStampConfig(status);
    const cacheControl = getCacheControl(status);

    // Load fonts (Inter Bold + Playfair Display)
    let interBoldData: ArrayBuffer | null = null;
    let playfairData: ArrayBuffer | null = null;
    try {
        const [interRes, playfairRes] = await Promise.all([
            fetch(
                "https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuFuYAZ9hiJ-Ek-_EeA.woff2"
            ),
            fetch(
                "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFiD-vYSZviVYUb_rj3ij__anPXBYf9lW4e5j5hNKc.woff2"
            ),
        ]);
        if (interRes.ok) interBoldData = await interRes.arrayBuffer();
        if (playfairRes.ok) playfairData = await playfairRes.arrayBuffer();
    } catch {
        // fonts unavailable — ImageResponse will fall back to system fonts
    }

    const fonts: ConstructorParameters<typeof ImageResponse>[1]["fonts"] = [];
    if (interBoldData) {
        fonts.push({ name: "Inter", data: interBoldData, weight: 700 });
    }
    if (playfairData) {
        fonts.push({ name: "Playfair Display", data: playfairData, weight: 400 });
    }

    const image = new ImageResponse(
        (
            <div
                style={{
                    display: "flex",
                    flexDirection: "column",
                    width: "1200px",
                    height: "630px",
                    background: "#09090b",
                    fontFamily: "'Inter', sans-serif",
                    padding: "0",
                    overflow: "hidden",
                }}
            >
                {/* Top bar */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        background: "#064e3b",
                        padding: "20px 48px",
                        borderBottom: "1px solid #10b981",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                        {/* Shield icon approximation */}
                        <div
                            style={{
                                width: "28px",
                                height: "28px",
                                background: "#10b981",
                                borderRadius: "50%",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontSize: "14px",
                                color: "#064e3b",
                                fontWeight: 700,
                            }}
                        >
                            ◈
                        </div>
                        <span
                            style={{
                                fontSize: "18px",
                                fontWeight: 700,
                                color: "#10b981",
                                letterSpacing: "0.15em",
                                textTransform: "uppercase",
                            }}
                        >
                            CAP ALPHA PROTOCOL
                        </span>
                    </div>

                    {/* Stamp — rotated */}
                    <div
                        style={{
                            transform: "rotate(-8deg)",
                            border: `3px solid ${stamp.borderColor}`,
                            borderRadius: "6px",
                            padding: "8px 20px",
                            background: stamp.bgColor,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                        }}
                    >
                        <span
                            style={{
                                fontSize: "20px",
                                fontWeight: 700,
                                color: stamp.color,
                                letterSpacing: "0.12em",
                                textTransform: "uppercase",
                            }}
                        >
                            {stamp.text}
                        </span>
                    </div>
                </div>

                {/* Main content area */}
                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        flex: 1,
                        padding: "48px 56px 40px",
                        justifyContent: "space-between",
                    }}
                >
                    {/* Prediction claim — large serif */}
                    <div
                        style={{
                            fontSize: "42px",
                            fontFamily: "'Playfair Display', serif",
                            color: "#f4f4f5",
                            lineHeight: 1.25,
                            maxWidth: "1060px",
                            display: "-webkit-box",
                            WebkitBoxOrient: "vertical",
                            WebkitLineClamp: 3,
                            overflow: "hidden",
                        }}
                    >
                        &ldquo;{claim}&rdquo;
                    </div>

                    {/* Bottom info rows */}
                    <div
                        style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: "16px",
                        }}
                    >
                        {/* Pundit + date row */}
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "32px",
                                borderTop: "1px solid #27272a",
                                paddingTop: "20px",
                            }}
                        >
                            <span
                                style={{
                                    fontSize: "26px",
                                    fontWeight: 700,
                                    color: "#f4f4f5",
                                    fontFamily: "'Inter', sans-serif",
                                }}
                            >
                                {punditName}
                            </span>
                            <span
                                style={{
                                    fontSize: "18px",
                                    color: "#71717a",
                                    fontFamily: "monospace",
                                }}
                            >
                                Made: {madeDate}
                            </span>
                        </div>

                        {/* Accuracy footer */}
                        {(accuracyPct || totalPredictions) && (
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "32px",
                                    padding: "14px 20px",
                                    background: "#18181b",
                                    borderRadius: "8px",
                                    border: "1px solid #27272a",
                                }}
                            >
                                <span
                                    style={{
                                        fontSize: "13px",
                                        fontWeight: 700,
                                        color: "#52525b",
                                        letterSpacing: "0.1em",
                                        textTransform: "uppercase",
                                        fontFamily: "monospace",
                                    }}
                                >
                                    PUNDIT STATS
                                </span>
                                {accuracyPct && (
                                    <span
                                        style={{
                                            fontSize: "18px",
                                            fontFamily: "monospace",
                                            color: "#10b981",
                                        }}
                                    >
                                        Accuracy: {accuracyPct}
                                    </span>
                                )}
                                {totalPredictions && (
                                    <span
                                        style={{
                                            fontSize: "18px",
                                            fontFamily: "monospace",
                                            color: "#a1a1aa",
                                        }}
                                    >
                                        Predictions: {totalPredictions}
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        ),
        {
            width: 1200,
            height: 630,
            fonts,
        }
    );

    // Override cache-control header
    image.headers.set("Cache-Control", cacheControl);
    return image;
}
