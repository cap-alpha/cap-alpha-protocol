import React from 'react';
import Link from 'next/link';
import { DebugReset } from './debug-reset';

const Footer = () => {
    return (
        <footer className="w-full border-t border-slate-800 bg-slate-950 mt-auto">
            {/* Responsible Gambling Banner */}
            <div className="w-full bg-amber-950/60 border-b border-amber-900/40 px-4 py-3">
                <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-2 text-center">
                    <p className="text-amber-200 text-xs sm:text-sm font-medium leading-snug">
                        <span className="font-bold">If you or someone you know has a gambling problem, call </span>
                        <a href="tel:18004262537" className="font-bold underline hover:text-amber-100 transition-colors">1-800-GAMBLER</a>
                        <span className="text-amber-300/80"> (1-800-426-2537)</span>
                        <span className="mx-2 hidden sm:inline">·</span>
                        <br className="sm:hidden" />
                        <span className="text-amber-300/80">Must be 21+ to participate in sports betting. Void where prohibited.</span>
                    </p>
                    <Link
                        href="/legal/responsible-gambling"
                        className="shrink-0 text-xs text-amber-400 underline hover:text-amber-200 transition-colors"
                    >
                        Resources
                    </Link>
                </div>
            </div>

            <div className="py-8 px-4">
                <div className="max-w-7xl mx-auto flex flex-col items-center justify-center space-y-4">
                    <p className="text-slate-400 text-sm text-center max-w-2xl leading-relaxed">
                        <span className="font-bold text-slate-300">NOTICE:</span> For simulation and entertainment purposes only.
                        The data and predictions provided by Cap Alpha are probabilistic simulations and should not be
                        construed as financial, legal, or professional sports management advice.
                    </p>
                    <p className="text-slate-500 text-xs text-center max-w-2xl leading-relaxed">
                        Some links on this site are affiliate links. Cap Alpha may earn a commission when you sign up through
                        these links, at no additional cost to you.{' '}
                        <Link href="/legal/disclosure" className="underline hover:text-emerald-500 transition-colors">
                            Affiliate Disclosure
                        </Link>
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-4 text-slate-500 text-xs">
                        <Link href="/legal/terms" className="hover:text-slate-300 transition-colors">Terms</Link>
                        <Link href="/legal/privacy" className="hover:text-slate-300 transition-colors">Privacy</Link>
                        <Link href="/legal/acceptable-use" className="hover:text-slate-300 transition-colors">Acceptable Use</Link>
                        <Link href="/legal/responsible-gambling" className="hover:text-amber-400 transition-colors text-amber-600">Responsible Gambling</Link>
                        <Link href="/legal/disclosure" className="hover:text-slate-300 transition-colors">Affiliate Disclosure</Link>
                    </div>
                    <div className="flex items-center space-x-2 text-slate-500 text-xs">
                        <span>&copy; {new Date().getFullYear()} Andrew Smith</span>
                        <span className="h-1 w-1 bg-slate-700 rounded-full"></span>
                        <span>All Rights Reserved</span>
                        <span className="h-1 w-1 bg-slate-700 rounded-full"></span>
                        <a
                            href={`https://github.com/ucalegon206/cap-alpha-protocol/commit/${process.env.NEXT_PUBLIC_COMMIT_SHA}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-slate-600 hover:text-emerald-500 transition-colors"
                        >
                            v{process.env.NEXT_PUBLIC_COMMIT_SHA?.substring(0, 7) || 'local'}
                        </a>
                        <span className="h-1 w-1 bg-slate-700 rounded-full mx-2 hidden sm:inline-block"></span>
                        <DebugReset />
                    </div>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
