import { ImageResponse } from 'next/og';

// Route segment config
export const runtime = 'edge';

// Image metadata
export const alt = 'Pundit Ledger — The most accurate sports pundits, ranked.';
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = 'image/png';

// OG image generation
export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#000000',
          position: 'relative',
          fontFamily: 'sans-serif',
        }}
      >
        {/* Emerald glow radial — centered */}
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '700px',
            height: '400px',
            background:
              'radial-gradient(ellipse at center, rgba(16,185,129,0.18) 0%, rgba(16,185,129,0.06) 45%, transparent 70%)',
            borderRadius: '50%',
          }}
        />

        {/* Wordmark row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '32px',
          }}
        >
          {/* P lettermark */}
          <svg width="40" height="40" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="2" width="3" height="16" rx="1" fill="#10b981" />
            <rect x="6" y="2" width="7" height="3" rx="1" fill="#10b981" />
            <rect x="6" y="8" width="7" height="3" rx="1" fill="#10b981" />
            <rect x="13" y="5" width="3" height="6" rx="1" fill="#10b981" />
            <rect x="13" y="15" width="4" height="4" rx="2" fill="#10b981" />
          </svg>
          <span
            style={{
              color: '#10b981',
              fontSize: '22px',
              fontWeight: 900,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}
          >
            Pundit Ledger
          </span>
        </div>

        {/* Headline */}
        <div
          style={{
            color: '#ffffff',
            fontSize: '64px',
            fontWeight: 900,
            lineHeight: 1.1,
            textAlign: 'center',
            maxWidth: '900px',
            marginBottom: '24px',
            letterSpacing: '-0.02em',
          }}
        >
          The most accurate sports pundits, ranked.
        </div>

        {/* Subhead */}
        <div
          style={{
            color: '#a1a1aa',
            fontSize: '28px',
            fontWeight: 400,
            textAlign: 'center',
            maxWidth: '700px',
            lineHeight: 1.4,
            marginBottom: '48px',
          }}
        >
          Every prediction tracked, scored, and sealed.
        </div>

        {/* Emerald divider */}
        <div
          style={{
            width: '60px',
            height: '2px',
            background: '#10b981',
            marginBottom: '24px',
          }}
        />

        {/* Footer domain */}
        <div
          style={{
            color: '#52525b',
            fontSize: '18px',
            fontWeight: 500,
            letterSpacing: '0.05em',
          }}
        >
          cap-alpha.co
        </div>
      </div>
    ),
    { ...size }
  );
}
