import React from 'react';
import Link from 'next/link';
import { DebugReset } from './debug-reset';

const Footer = () => {
    return (
        <footer className="w-full py-8 px-4 border-t border-slate-800 bg-slate-950 mt-auto">
            <div className="max-w-7xl mx-auto flex flex-col items-center justify-center space-y-4">
                <p className="text-slate-400 text-sm text-center max-w-2xl leading-relaxed">
                    <span className="font-bold text-slate-300">NOTICE:</span> For simulation and entertainment purposes only.
                    The data and predictions provided by the Cap Alpha Protocol are probabilistic simulations and should not be
                    construed as financial, legal, or professional sports management advice.
                </p>
                <div className="flex items-center gap-4 text-slate-500 text-xs">
                    <Link href="/legal/terms" className="hover:text-slate-300 transition-colors">Terms</Link>
                    <Link href="/legal/privacy" className="hover:text-slate-300 transition-colors">Privacy</Link>
                    <Link href="/legal/acceptable-use" className="hover:text-slate-300 transition-colors">Acceptable Use</Link>
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
        </footer>
    );
};

export default Footer;
