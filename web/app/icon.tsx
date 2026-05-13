import { ImageResponse } from 'next/og';

// Route segment config
export const runtime = 'edge';

// Image metadata
export const size = {
  width: 32,
  height: 32,
};
export const contentType = 'image/png';

// Image generation
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#000000',
          borderRadius: '6px',
        }}
      >
        {/* Stylized "P" lettermark in brand emerald (#10b981) — legible at 32px */}
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
        >
          {/* Vertical stem */}
          <rect x="3" y="2" width="3" height="16" rx="1" fill="#10b981" />
          {/* Bowl top */}
          <rect x="6" y="2" width="7" height="3" rx="1" fill="#10b981" />
          {/* Bowl bottom */}
          <rect x="6" y="8" width="7" height="3" rx="1" fill="#10b981" />
          {/* Bowl right side */}
          <rect x="13" y="5" width="3" height="6" rx="1" fill="#10b981" />
          {/* Accent dot — echoes the ledger "sealed" concept */}
          <rect x="13" y="15" width="4" height="4" rx="2" fill="#10b981" />
        </svg>
      </div>
    ),
    { ...size }
  );
}
