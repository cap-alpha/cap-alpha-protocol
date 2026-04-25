/**
 * SP25-3: OG image for /share/player/[slug].
 *
 * Next.js 14 uses ImageResponse (from next/og) to generate a static PNG
 * at build/request time via Satori + Resvg.  No canvas, no puppeteer.
 *
 * Dimensions: 1200×630 (standard OG card).
 */

import { ImageResponse } from "next/og";
import { getRosterData } from "@/app/actions";
import { slugify } from "@/lib/utils";

export const runtime = "nodejs";
export const alt = "Cap Alpha Intel — Player Card";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

interface Props {
  params: { slug: string };
}

export default async function Image({ params }: Props) {
  const playerSlug = decodeURIComponent(params.slug);
  const roster = await getRosterData();
  const player = roster.find((p) => slugify(p.player_name) === playerSlug);

  if (!player) {
    // Fallback OG image for unknown player
    return new ImageResponse(
      (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "#09090b",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span style={{ color: "#71717a", fontSize: 48, fontWeight: 700 }}>
            Player Not Found
          </span>
        </div>
      ),
      { ...size }
    );
  }

  const isRisky =
    (player.dead_cap_millions || 0) > (player.cap_hit_millions || 1) * 0.4;
  const accentHex = isRisky ? "#f43f5e" : "#10b981";
  const bgTop = isRisky ? "#4c0519" : "#022c22";
  const label = isRisky ? "TOXIC" : "ALPHA";
  const capHit = player.cap_hit_millions?.toFixed(1) ?? "0.0";
  const riskScore = player.risk_score?.toFixed(2) ?? "—";
  const fmv = player.fair_market_value?.toFixed(1) ?? "—";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: `linear-gradient(135deg, ${bgTop} 0%, #09090b 50%, #09090b 100%)`,
          display: "flex",
          flexDirection: "column",
          padding: "56px 64px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          {/* Player identity */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <span
              style={{
                color: "#ffffff",
                fontSize: 72,
                fontWeight: 900,
                letterSpacing: "-3px",
                lineHeight: 1,
                textTransform: "uppercase",
              }}
            >
              {player.player_name}
            </span>
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <span
                style={{
                  background: "#27272a",
                  color: "#ffffff",
                  padding: "6px 14px",
                  borderRadius: 6,
                  fontSize: 22,
                  fontWeight: 700,
                  fontFamily: "monospace",
                }}
              >
                {player.position}
              </span>
              <span style={{ color: "#71717a", fontSize: 22, fontWeight: 500 }}>
                •
              </span>
              <span
                style={{
                  color: "#a1a1aa",
                  fontSize: 22,
                  fontWeight: 600,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                }}
              >
                {player.team}
              </span>
            </div>
          </div>

          {/* Market thesis badge */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 8,
              border: `2px solid ${accentHex}44`,
              borderRadius: 16,
              padding: "20px 32px",
            }}
          >
            <span
              style={{
                color: "#71717a",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.2em",
                textTransform: "uppercase",
              }}
            >
              Market Thesis
            </span>
            <span
              style={{
                color: accentHex,
                fontSize: 40,
                fontWeight: 900,
                letterSpacing: "-1px",
              }}
            >
              {label}
            </span>
          </div>
        </div>

        {/* Metrics row */}
        <div
          style={{
            display: "flex",
            gap: 24,
            marginTop: "auto",
            marginBottom: 8,
          }}
        >
          {[
            { label: "Cap Burden", value: `$${capHit}M` },
            { label: "Fair Market Value", value: fmv !== "—" ? `$${fmv}M` : "—" },
            { label: "ML Risk Score", value: riskScore },
            {
              label: "Dead Cap",
              value: `$${player.dead_cap_millions?.toFixed(1) ?? "0.0"}M`,
            },
          ].map((m) => (
            <div
              key={m.label}
              style={{
                flex: 1,
                background: "rgba(0,0,0,0.5)",
                borderRadius: 12,
                padding: "20px 24px",
                border: "1px solid rgba(255,255,255,0.06)",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <span
                style={{
                  color: "#52525b",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                }}
              >
                {m.label}
              </span>
              <span
                style={{
                  color: "#ffffff",
                  fontSize: 34,
                  fontWeight: 700,
                  fontFamily: "monospace",
                }}
              >
                {m.value}
              </span>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: 24,
            paddingTop: 20,
            borderTop: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <span
            style={{
              color: "#52525b",
              fontSize: 14,
              fontWeight: 600,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            NFL Dead Money · Cap Alpha Intel
          </span>
          <span
            style={{
              color: "#52525b",
              fontSize: 14,
              fontFamily: "monospace",
            }}
          >
            cap-alpha.vercel.app
          </span>
        </div>
      </div>
    ),
    { ...size }
  );
}
