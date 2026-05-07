/**
 * Affiliate link configuration for all supported platforms.
 *
 * PENDING APPROVAL: All hrefs are set to '#affiliate-pending'.
 * The <AffiliateCta /> component renders nothing when href is '#affiliate-pending',
 * so no broken links ship to users until Rakuten Advertising approves each program.
 *
 * When approval arrives, swap one line per platform:
 *   draftkings: { href: 'https://draftkings.go2cloud.org/aff_c?offer_id=...', ... }
 */

export type AffiliatePlatformKey = 'draftkings' | 'fanduel' | 'prizepicks' | 'underdog';
export type AffiliateContextKey = 'ledger' | 'pundit-card' | 'footer';

export interface AffiliateEntry {
  href: string;
  name: string;
  cta: Record<AffiliateContextKey, string>;
}

export const AFFILIATE_LINKS: Record<AffiliatePlatformKey, AffiliateEntry> = {
  draftkings: {
    href: '#affiliate-pending', // swap with Rakuten tracking URL on approval
    name: 'DraftKings',
    cta: {
      ledger: 'Bet on these predictions at DraftKings',
      'pundit-card': "Follow this pundit's picks at DraftKings",
      footer: 'Play DraftKings',
    },
  },
  fanduel: {
    href: '#affiliate-pending', // swap with Rakuten tracking URL on approval
    name: 'FanDuel',
    cta: {
      ledger: 'Turn predictions into winnings at FanDuel',
      'pundit-card': 'Back this pundit at FanDuel',
      footer: 'Play FanDuel',
    },
  },
  prizepicks: {
    href: '#affiliate-pending', // swap with Rakuten tracking URL on approval
    name: 'PrizePicks',
    cta: {
      ledger: 'Pick over/unders based on this data at PrizePicks',
      'pundit-card': "Build a lineup from this pundit's picks at PrizePicks",
      footer: 'Play PrizePicks',
    },
  },
  underdog: {
    href: '#affiliate-pending', // swap with Rakuten tracking URL on approval
    name: 'Underdog Fantasy',
    cta: {
      ledger: 'Put your picks to work at Underdog Fantasy',
      'pundit-card': 'Draft against this pundit at Underdog Fantasy',
      footer: 'Play Underdog Fantasy',
    },
  },
} as const;
