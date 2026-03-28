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
      // ImageResponse JSX element
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#09090b', // zinc-950
          color: '#ffffff',
          borderRadius: '4px',
          fontFamily: 'sans-serif',
          fontSize: 18,
          fontWeight: 900,
        }}
      >
        CA
      </div>
    ),
    // ImageResponse options
    { ...size }
  );
}
