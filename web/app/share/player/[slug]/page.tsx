/**
 * SP25-3: Auto-generated Personality Magnet shareable card page.
 *
 * Route: /share/player/[slug]
 * Purpose: Renders a full-bleed, navbar-free personality magnet infographic
 * for a player.  Designed to be linked from social media, embedded in articles,
 * or exported as an image.  The Open Graph image (opengraph-image.tsx) ensures
 * a rich preview card when the URL is pasted into Twitter/LinkedIn.
 */

import { notFound } from "next/navigation";
import { getRosterData } from "@/app/actions";
import { slugify } from "@/lib/utils";
import { PersonalityMagnetCard } from "@/components/personality-magnet-card";
import type { Metadata } from "next";

export const revalidate = 3600;

interface Props {
  params: { slug: string };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const playerSlug = decodeURIComponent(params.slug);
  const roster = await getRosterData();
  const player = roster.find((p) => slugify(p.player_name) === playerSlug);

  if (!player) {
    return { title: "Player Not Found" };
  }

  const title = `${player.player_name} — Cap Alpha Intel`;
  const description = `${player.player_name} (${player.position}, ${player.team}) · $${player.cap_hit_millions?.toFixed(1)}M cap hit · ML risk score ${player.risk_score?.toFixed(2) ?? "N/A"} · Powered by NFL Dead Money`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "article",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export async function generateStaticParams() {
  // Pre-render the top 50 players by cap hit at build time
  const roster = await getRosterData();
  return roster.slice(0, 50).map((p) => ({ slug: slugify(p.player_name) }));
}

export default async function SharePlayerPage({ params }: Props) {
  const playerSlug = decodeURIComponent(params.slug);
  const roster = await getRosterData();
  const player = roster.find((p) => slugify(p.player_name) === playerSlug);

  if (!player) {
    notFound();
  }

  return (
    <main className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-4 md:p-8">
      {/* Card constrained to a max width for readability in feed/embed context */}
      <div className="w-full max-w-2xl">
        <PersonalityMagnetCard player={player} />
      </div>

      {/* Back-link — shown below the card so it doesn't clutter the shareable area */}
      <p className="mt-6 text-xs text-zinc-600 font-mono">
        <a
          href={`/player/${playerSlug}`}
          className="hover:text-zinc-400 transition-colors"
        >
          View full profile →
        </a>
      </p>
    </main>
  );
}
