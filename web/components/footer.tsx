// Footer with correction policy link — issue #482
import React from 'react';
import Link from 'next/link';
import { DebugReset } from './debug-reset';

const Footer = () => {
    return (
        <footer className="w-full border-t border-white/10 bg-navy mt-auto">
            {/* Responsible Gambling Banner */}
            <div className="w-full bg-pending/15 border-b border-pending/30 px-4 py-3">
                <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-2 text-center">
                    <p className="text-white/90 text-xs sm:text-sm font-medium leading-snug">
                        <span className="font-bold">If you or someone you know has a gambling problem, call </span>
                        <a href="tel:18004262537" className="font-bold underline hover:text-gold-light transition-colors min-h-[44px] inline-flex items-center">1-800-GAMBLER</a>
                        <span className="text-white/70"> (1-800-426-2537)</span>
                        <span className="mx-2 hidden sm:inline">·</span>
                        <br className="sm:hidden" />
                        <span className="text-white/70">Must be 21+ to participate in sports betting. Void where prohibited.</span>
                    </p>
                    <Link
                        href="/legal/responsible-gambling"
                        className="shrink-0 text-xs text-gold-light underline hover:text-white transition-colors min-h-[44px] inline-flex items-center"
                    >
                        Resources
                    </Link>
                </div>
            </div>

            <div className="py-8 px-4">
                <div className="max-w-7xl mx-auto flex flex-col items-center justify-center space-y-4">
                    <p className="text-white/60 text-sm text-center max-w-2xl leading-relaxed">
                        <span className="font-bold text-white/80">NOTICE:</span> For simulation and entertainment purposes only.
                        The data and predictions provided by Cap Alpha are probabilistic simulations and should not be
                        construed as financial, legal, or professional sports management advice.
                    </p>
                    <p className="text-white/60 text-xs text-center max-w-2xl leading-relaxed">
                        Some links on this site are affiliate links. Cap Alpha may earn a commission when you sign up through
                        these links, at no additional cost to you.{' '}
                        <Link href="/legal/disclosure" className="underline hover:text-gold-light transition-colors min-h-[44px] inline-flex items-center">
                            Affiliate Disclosure
                        </Link>
                    </p>
                    {/* Trust & product links — de-emphasize developer/operational links */}
                    <div className="flex flex-wrap items-center justify-center gap-4 text-white/80 text-xs mb-2">
                        <Link href="/methodology" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors font-medium">Methodology</Link>
                        <Link href="/quality" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors font-medium">Data Quality</Link>
                        <Link href="/verify" className="min-h-[44px] inline-flex items-center hover:text-gold-light transition-colors font-medium">Verify Ledger</Link>
                    </div>
                    <div className="flex flex-wrap items-center justify-center gap-4 text-white/60 text-xs">
                        <Link href="/methodology" className="min-h-[44px] inline-flex items-center hover:text-gold-light transition-colors">Methodology</Link>
                        <Link href="/legal/terms" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Terms</Link>
                        <Link href="/legal/privacy" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Privacy</Link>
                        <Link href="/legal/acceptable-use" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Acceptable Use</Link>
                        <Link href="/legal/responsible-gambling" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors text-gold-light">Responsible Gambling</Link>
                        <Link href="/legal/disclosure" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Affiliate Disclosure</Link>
                        <Link href="/legal/corrections" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Corrections</Link>
                        <Link href="/status" className="min-h-[44px] inline-flex items-center hover:text-white/80 transition-colors">Status</Link>
                    </div>
                    <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-white/60 text-xs">
                        <span>&copy; {new Date().getFullYear()} Andrew Smith</span>
                        <span className="h-1 w-1 bg-white/20 rounded-full" aria-hidden="true"></span>
                        <span>All Rights Reserved</span>
                        <span className="h-1 w-1 bg-white/20 rounded-full" aria-hidden="true"></span>
                        <a
                            href={`https://github.com/cap-alpha/cap-alpha-protocol/commit/${process.env.NEXT_PUBLIC_COMMIT_SHA}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-white/60 hover:text-gold-light transition-colors min-h-[44px] inline-flex items-center"
                        >
                            v{process.env.NEXT_PUBLIC_COMMIT_SHA?.substring(0, 7) || 'local'}
                            <span className="sr-only"> — View source commit on GitHub</span>
                        </a>
                        <DebugReset />
                    </div>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
