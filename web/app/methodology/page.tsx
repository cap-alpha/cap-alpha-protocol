import Link from "next/link";
import { Metadata } from "next";
import {
    Target,
    Scale,
    BarChart3,
    Crosshair,
    Activity,
    Flame,
    ShieldCheck,
    Lock,
    Flag,
    ArrowRight,
    AlertTriangle,
    Eye,
    Brain,
    Compass,
    MessageSquareWarning,
    CheckCircle2,
    XCircle,
} from "lucide-react";

export const metadata: Metadata = {
    title: "Methodology | Pundit Ledger",
    description:
        "How we score pundits — the truthiness framework behind the Pundit Credit Score.",
};

// --- Reusable section components ---

function SectionHeader({
    label,
    title,
    subtitle,
}: {
    label?: string;
    title: string;
    subtitle?: string;
}) {
    return (
        <div className="text-center space-y-3 mb-12">
            {label && (
                <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                    {label}
                </span>
            )}
            <h2 className="text-3xl sm:text-4xl font-black tracking-tight text-white">
                {title}
            </h2>
            {subtitle && (
                <p className="text-lg text-zinc-400 max-w-2xl mx-auto leading-relaxed">
                    {subtitle}
                </p>
            )}
        </div>
    );
}

function AxisCard({
    title,
    description,
    levels,
}: {
    title: string;
    description: string;
    levels: { name: string; desc: string; color: string }[];
}) {
    return (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 sm:p-8 space-y-5">
            <div>
                <h3 className="text-xl font-bold text-white mb-1">{title}</h3>
                <p className="text-sm text-zinc-400">{description}</p>
            </div>
            <div className="space-y-3">
                {levels.map((level) => (
                    <div
                        key={level.name}
                        className="flex items-start gap-3 text-sm"
                    >
                        <span
                            className={`mt-1 w-2 h-2 rounded-full shrink-0 ${level.color}`}
                        />
                        <div>
                            <span className="font-semibold text-zinc-200">
                                {level.name}
                            </span>
                            <span className="text-zinc-500"> — </span>
                            <span className="text-zinc-400">{level.desc}</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function DimensionCard({
    icon: Icon,
    name,
    question,
    description,
    detects,
    tier,
}: {
    icon: React.ElementType;
    name: string;
    question: string;
    description: string;
    detects: string;
    tier: "free" | "pro";
}) {
    return (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-3 relative">
            {tier === "pro" && (
                <div className="absolute top-4 right-4 text-[10px] font-mono uppercase tracking-widest text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                    Pro
                </div>
            )}
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <Icon className="w-5 h-5 text-emerald-400" />
            </div>
            <h3 className="text-lg font-bold text-white">{name}</h3>
            <p className="text-sm font-medium text-emerald-400 italic">
                &ldquo;{question}&rdquo;
            </p>
            <p className="text-sm text-zinc-400 leading-relaxed">
                {description}
            </p>
            <p className="text-xs text-zinc-500">
                <span className="font-semibold text-zinc-400">Detects:</span>{" "}
                {detects}
            </p>
        </div>
    );
}

// --- Page ---

export default function MethodologyPage() {
    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* Hero */}
            <section className="relative flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>
                <div className="relative z-10 max-w-3xl mx-auto space-y-6">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <Eye className="w-3.5 h-3.5" />
                        Methodology
                    </span>
                    <h1 className="text-4xl sm:text-5xl font-black tracking-tight leading-[1.1]">
                        How We Score{" "}
                        <span className="text-emerald-400">Pundits</span>
                    </h1>
                    <p className="text-xl text-zinc-400 max-w-xl mx-auto leading-relaxed">
                        We don&apos;t just track whether pundits are right.
                        We track <em>how</em> and <em>why</em> they&apos;re wrong.
                    </p>
                </div>
            </section>

            {/* The Problem */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto space-y-6">
                    <h2 className="text-2xl font-bold text-white">
                        The Accountability Gap
                    </h2>
                    <div className="space-y-4 text-zinc-400 leading-relaxed">
                        <p>
                            Sports media runs on predictions. Every week, pundits make
                            dozens of public calls — spread picks, player props, bold
                            season takes. When they hit, they celebrate loudly. When they
                            miss, the tape quietly rolls on.
                        </p>
                        <p>
                            No one systematically tracks whether these people are actually
                            right. Bettors lose real money tailing personalities who have
                            never had their record audited. Fans form opinions based on
                            pundits who sound confident but have no track record to back
                            it up.
                        </p>
                        <p className="text-zinc-300 font-medium">
                            The Pundit Prediction Ledger closes that gap. But to do it
                            right, we need to understand not just{" "}
                            <em>whether</em> pundits are wrong, but the different{" "}
                            <em>ways</em> they can be wrong — and what those patterns
                            reveal.
                        </p>
                    </div>
                </div>
            </section>

            {/* Axes of Truthiness */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-5xl mx-auto">
                    <SectionHeader
                        label="Framework"
                        title="The Axes of Truthiness"
                        subtitle="Before we get to numbers, we need to understand the different ways a prediction can fail — and what each failure reveals about the person making it."
                    />

                    <div className="grid md:grid-cols-2 gap-6">
                        {/* Axis 1: Degrees of Falsehood */}
                        <AxisCard
                            title="Degrees of Falsehood"
                            description="Not all wrong predictions are created equal. There's a spectrum from genuine error to deliberate deception."
                            levels={[
                                {
                                    name: "Honest error",
                                    desc: "Genuinely believed it, had a reasonable basis, was wrong. \"I thought the O-line would hold up — I didn't expect 3 injuries.\"",
                                    color: "bg-emerald-400",
                                },
                                {
                                    name: "Lazy wrongness",
                                    desc: "Didn't do the homework, just vibed. \"I like the over here\" — no analysis, no reasoning.",
                                    color: "bg-yellow-400",
                                },
                                {
                                    name: "Bullshitting",
                                    desc: "Doesn't know or care if it's true — says what sounds good. Indifferent to truth, not opposed to it.",
                                    color: "bg-orange-400",
                                },
                                {
                                    name: "Motivated reasoning",
                                    desc: "Has a bias — network narrative, fandom, paid relationship — that distorts the analysis without the audience knowing.",
                                    color: "bg-red-400",
                                },
                                {
                                    name: "Deliberate deception",
                                    desc: "Knows it's wrong, says it anyway for engagement or money. \"Lock of the century\" on a pick they don't believe in.",
                                    color: "bg-red-600",
                                },
                            ]}
                        />

                        {/* Axis 2: Epistemic Basis */}
                        <AxisCard
                            title="Epistemic Basis"
                            description="What is the prediction actually built on? The foundation matters as much as the outcome."
                            levels={[
                                {
                                    name: "Data-grounded",
                                    desc: "Cites specific stats, film study, injury reports. The prediction has a traceable analytical basis.",
                                    color: "bg-emerald-400",
                                },
                                {
                                    name: "Experience-based",
                                    desc: "\"I've covered this team for 20 years, I know their tendencies.\" Valid but unverifiable.",
                                    color: "bg-emerald-300",
                                },
                                {
                                    name: "Gut intuition",
                                    desc: "\"I just feel it.\" Might be pattern recognition — or might be nothing.",
                                    color: "bg-yellow-400",
                                },
                                {
                                    name: "Narrative-driven",
                                    desc: "\"This is a revenge game.\" The prediction serves a storyline, not an analysis.",
                                    color: "bg-orange-400",
                                },
                                {
                                    name: "Contrarian for clicks",
                                    desc: "Hot take with no basis other than being provocative. The prediction is content, not conviction.",
                                    color: "bg-red-400",
                                },
                            ]}
                        />

                        {/* Axis 3: Calibration */}
                        <AxisCard
                            title="Calibration"
                            description="Does their confidence match their accuracy? The gap between how sure they sound and how often they're right is the bullshit detector."
                            levels={[
                                {
                                    name: "Well-calibrated",
                                    desc: "Says \"70% confident\" and is right about 70% of the time. Their confidence is informative.",
                                    color: "bg-emerald-400",
                                },
                                {
                                    name: "Overconfident",
                                    desc: "Everything's a lock, but the hit rate is 52%. Their confidence is noise.",
                                    color: "bg-orange-400",
                                },
                                {
                                    name: "Strategic hedger",
                                    desc: "Never commits firmly enough to be proven wrong. \"I could see the Chiefs winning\" is unfalsifiable by design.",
                                    color: "bg-yellow-400",
                                },
                                {
                                    name: "Erratic",
                                    desc: "All-in one week, wishy-washy the next. No consistent signal for anyone to act on.",
                                    color: "bg-red-400",
                                },
                            ]}
                        />

                        {/* Axis 4: Accountability */}
                        <AxisCard
                            title="Accountability"
                            description="What happens after a pundit is proven wrong? This is the only axis that measures character, not competence."
                            levels={[
                                {
                                    name: "Owns it",
                                    desc: "\"I was wrong, here's what I missed.\" Rare and valuable — shows the analysis is genuine.",
                                    color: "bg-emerald-400",
                                },
                                {
                                    name: "Silent burial",
                                    desc: "Never mentions it again. Moves on to the next take and hopes you forgot.",
                                    color: "bg-yellow-400",
                                },
                                {
                                    name: "Revisionism",
                                    desc: "\"What I actually said was...\" Reframes the prediction after the fact to look less wrong.",
                                    color: "bg-orange-400",
                                },
                                {
                                    name: "Doubling down",
                                    desc: "\"I'm still right, the outcome was fluky.\" Refuses to update even when the evidence is clear.",
                                    color: "bg-red-400",
                                },
                                {
                                    name: "Deflection",
                                    desc: "\"Nobody could've predicted that.\" Externalizes all blame to preserve the illusion of competence.",
                                    color: "bg-red-600",
                                },
                            ]}
                        />
                    </div>
                </div>
            </section>

            {/* Scoring Dimensions */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-5xl mx-auto">
                    <SectionHeader
                        label="The Scores"
                        title="How Our Dimensions Map to Truthiness"
                        subtitle="Each scoring dimension acts as a detector for specific patterns of pundit unreliability."
                    />

                    {/* Free Tier */}
                    <div className="mb-8">
                        <div className="flex items-center gap-3 mb-6">
                            <span className="text-sm font-mono uppercase tracking-widest text-zinc-500">
                                Free Tier
                            </span>
                            <span className="text-xs text-zinc-600">
                                — The Triangle
                            </span>
                        </div>
                        <div className="grid sm:grid-cols-3 gap-6">
                            <DimensionCard
                                icon={Target}
                                name="Accuracy"
                                question="Are they right?"
                                description="The most basic truth test. Correct predictions divided by total predictions. Catches honest errors and deliberate bad picks alike — anyone can get lucky, but accuracy over hundreds of predictions reveals the signal."
                                detects="Honest error, lazy wrongness, deliberate deception"
                                tier="free"
                            />
                            <DimensionCard
                                icon={Scale}
                                name="Magnitude"
                                question="When they're wrong, how wrong?"
                                description="Separates informed misses from wild guesses. A pundit who says 'Chiefs by 3' when they win by 1 is very different from one who says 'Chiefs by 20' when they lose by 14. Small misses are forgiven; whoppers tank the score."
                                detects="Lazy wrongness, gut-based predictions, overconfidence"
                                tier="free"
                            />
                            <DimensionCard
                                icon={BarChart3}
                                name="Volume"
                                question="Do they make enough testable claims to judge?"
                                description="Filters out strategic hedgers who avoid commitment. If a pundit only makes 4 testable predictions per season, their score is unreliable. Low sample sizes receive a confidence penalty that shrinks the score toward the mean."
                                detects="Strategic hedging, vague takes, low commitment"
                                tier="free"
                            />
                        </div>
                    </div>

                    {/* Pro Tier */}
                    <div className="mb-8">
                        <div className="flex items-center gap-3 mb-6">
                            <span className="text-sm font-mono uppercase tracking-widest text-emerald-400">
                                Pro Tier
                            </span>
                            <span className="text-xs text-zinc-600">
                                — The Full Profile
                            </span>
                        </div>
                        <div className="grid sm:grid-cols-3 gap-6">
                            <DimensionCard
                                icon={Crosshair}
                                name="Precision"
                                question="When they say 'lock,' do they mean it?"
                                description="The bullshitting detector. Tracks predictions where the pundit expressed high confidence — 'lock of the week,' 'guaranteed,' 'hammer this' — versus their actual hit rate on those picks. High precision means their conviction calls hit. Low precision means they're performing confidence, not demonstrating it."
                                detects="Bullshitting, confidence inflation, overconfidence"
                                tier="pro"
                            />
                            <DimensionCard
                                icon={Activity}
                                name="Consistency"
                                question="Are they steady or streaky?"
                                description="Separates skill from luck. A pundit who's 70% one month and 30% the next is less useful than one steady at 50%. Measures the standard deviation of rolling accuracy windows — bettors need to know if the signal is reliable week to week."
                                detects="Streakiness, survivorship bias, small-window luck"
                                tier="pro"
                            />
                            <DimensionCard
                                icon={Flame}
                                name="Boldness"
                                question="Do they actually say anything?"
                                description="Measures how often a pundit goes against the consensus line or public betting percentages. High boldness plus high accuracy equals genuinely valuable signal. High boldness plus low accuracy means fade material. Low boldness means a chalk parrot who just picks favorites."
                                detects="Chalk parroting, narrative-driven picks, contrarian performance"
                                tier="pro"
                            />
                        </div>
                    </div>

                    {/* Coming Soon: Accountability */}
                    <div className="rounded-2xl border border-dashed border-zinc-700 bg-zinc-900/30 p-8 text-center space-y-3">
                        <div className="w-12 h-12 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center mx-auto">
                            <MessageSquareWarning className="w-6 h-6 text-zinc-400" />
                        </div>
                        <h3 className="text-lg font-bold text-white">
                            Coming Soon: Accountability
                        </h3>
                        <p className="text-sm text-zinc-400 max-w-lg mx-auto leading-relaxed">
                            The 7th dimension. We&apos;re building the ability to scan whether a
                            pundit references past misses in subsequent content — do they
                            own their mistakes, bury them, revise history, or double down?
                            The only dimension that measures <em>character</em>, not just
                            competence.
                        </p>
                    </div>
                </div>
            </section>

            {/* Prediction Eligibility */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto">
                    <SectionHeader
                        label="Eligibility"
                        title="What Counts as a Prediction"
                        subtitle="Not every statement is a scoreable prediction. We apply strict eligibility criteria — and the criteria themselves are part of the methodology."
                    />

                    <div className="space-y-8">
                        <div className="space-y-4">
                            <h3 className="text-lg font-bold text-white">
                                A scoreable prediction must be:
                            </h3>
                            <div className="space-y-3">
                                <div className="flex items-start gap-3">
                                    <Target className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
                                    <div>
                                        <span className="font-semibold text-zinc-200">
                                            Resolvable
                                        </span>
                                        <span className="text-zinc-400">
                                            {" "}— A clear right/wrong outcome must exist.
                                        </span>
                                    </div>
                                </div>
                                <div className="flex items-start gap-3">
                                    <Compass className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
                                    <div>
                                        <span className="font-semibold text-zinc-200">
                                            Actionable
                                        </span>
                                        <span className="text-zinc-400">
                                            {" "}— A bettor could place a wager based on it.
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Valid Examples */}
                        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6 space-y-3">
                            <div className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest text-emerald-400">
                                <CheckCircle2 className="w-4 h-4" />
                                Valid Predictions
                            </div>
                            <ul className="space-y-2 text-sm text-zinc-300">
                                <li>&ldquo;Chiefs -3&rdquo;</li>
                                <li>&ldquo;Over 47.5&rdquo;</li>
                                <li>&ldquo;Eagles win the Super Bowl&rdquo;</li>
                                <li>
                                    &ldquo;Mahomes over 285.5 passing yards&rdquo;
                                </li>
                                <li>
                                    &ldquo;They&apos;ll trade for a WR before the
                                    deadline&rdquo;
                                </li>
                            </ul>
                        </div>

                        {/* Invalid Examples */}
                        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6 space-y-3">
                            <div className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest text-red-400">
                                <XCircle className="w-4 h-4" />
                                Not Scoreable
                            </div>
                            <ul className="space-y-2 text-sm text-zinc-400">
                                <li>&ldquo;I like the Chiefs this week&rdquo;</li>
                                <li>
                                    &ldquo;I think the offense will be better&rdquo;
                                </li>
                                <li>&ldquo;This team has momentum&rdquo;</li>
                                <li>
                                    &ldquo;He&apos;s going to have a big game&rdquo;
                                </li>
                            </ul>
                        </div>

                        {/* Why */}
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                            <div className="flex items-start gap-3">
                                <AlertTriangle className="w-5 h-5 text-yellow-400 mt-0.5 shrink-0" />
                                <div className="space-y-2">
                                    <h4 className="font-semibold text-zinc-200">
                                        Why we filter
                                    </h4>
                                    <p className="text-sm text-zinc-400 leading-relaxed">
                                        Vague predictions are the pundit&apos;s escape hatch.
                                        By requiring testable claims, we remove the ability to
                                        retroactively claim &ldquo;that&apos;s what I
                                        meant.&rdquo; This is by design —{" "}
                                        <span className="text-zinc-200 font-medium">
                                            if you can&apos;t be proven wrong, you shouldn&apos;t
                                            get credit for being right.
                                        </span>
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Immutable Ledger */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto">
                    <SectionHeader
                        label="Integrity"
                        title="The Immutable Ledger"
                        subtitle="Every prediction is cryptographically sealed at the moment of ingestion."
                    />

                    <div className="grid sm:grid-cols-3 gap-6">
                        <div className="space-y-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <Lock className="w-5 h-5 text-emerald-400" />
                            </div>
                            <h3 className="font-semibold text-white">
                                Hash-chained records
                            </h3>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Each prediction receives a SHA-256 hash that includes the
                                previous record&apos;s hash — forming an unbroken chain.
                                Altering any record would break every hash that follows.
                            </p>
                        </div>
                        <div className="space-y-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                            </div>
                            <h3 className="font-semibold text-white">
                                Append-only storage
                            </h3>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                The prediction ledger is write-once. No one — not even
                                us — can edit or delete a prediction after it&apos;s been
                                recorded. The infrastructure enforces this at every layer.
                            </p>
                        </div>
                        <div className="space-y-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <Eye className="w-5 h-5 text-emerald-400" />
                            </div>
                            <h3 className="font-semibold text-white">
                                Public verification
                            </h3>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Chain integrity can be independently verified via our API.
                                If the data has been tampered with, anyone can detect it.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Dispute Process */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto">
                    <SectionHeader
                        label="Disputes"
                        title="Flagging a Scoring Error"
                        subtitle="We score every prediction the same way. If we got one wrong, we want to know."
                    />

                    <div className="space-y-6">
                        <div className="grid sm:grid-cols-2 gap-6">
                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-2">
                                <div className="flex items-center gap-2">
                                    <Flag className="w-4 h-4 text-emerald-400" />
                                    <h4 className="font-semibold text-zinc-200">
                                        Flag any prediction
                                    </h4>
                                </div>
                                <p className="text-sm text-zinc-400">
                                    Use the flag button on any prediction page. Tell us what
                                    you think we got wrong and include a source.
                                </p>
                            </div>
                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-2">
                                <div className="flex items-center gap-2">
                                    <Brain className="w-4 h-4 text-emerald-400" />
                                    <h4 className="font-semibold text-zinc-200">
                                        5-day review
                                    </h4>
                                </div>
                                <p className="text-sm text-zinc-400">
                                    Flags are reviewed within 5 business days. Confirmed
                                    errors are corrected and logged publicly in the
                                    prediction&apos;s history.
                                </p>
                            </div>
                        </div>
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                <span className="font-semibold text-zinc-200">
                                    Important:
                                </span>{" "}
                                Pundits cannot unilaterally remove predictions from their
                                record. The ledger is immutable. A confirmed scoring error
                                results in a correction entry — the original prediction
                                remains visible with an updated resolution.
                            </p>
                        </div>
                        <p className="text-sm text-zinc-500">
                            Questions about methodology?{" "}
                            <a
                                href="mailto:support@cap-alpha.co"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                support@cap-alpha.co
                            </a>
                        </p>
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto text-center space-y-4">
                    <h2 className="text-2xl font-bold text-white">
                        See it in action
                    </h2>
                    <p className="text-zinc-400">
                        Check the leaderboard to see how your favorite pundits
                        actually perform.
                    </p>
                    <Link
                        href="/ledger"
                        className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-emerald-500 text-black text-sm font-semibold hover:bg-emerald-400 transition-colors"
                    >
                        View Leaderboard <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-zinc-900 px-6 py-8 mt-auto">
                <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-600">
                    <span className="font-black text-sm text-emerald-500 tracking-tight uppercase">
                        Pundit Ledger
                    </span>
                    <div className="flex items-center gap-6">
                        <Link
                            href="/ledger"
                            className="hover:text-zinc-400 transition-colors"
                        >
                            Leaderboard
                        </Link>
                        <Link
                            href="/methodology"
                            className="text-zinc-400"
                        >
                            Methodology
                        </Link>
                        <Link
                            href="/legal/terms"
                            className="hover:text-zinc-400 transition-colors"
                        >
                            Terms
                        </Link>
                        <Link
                            href="/legal/privacy"
                            className="hover:text-zinc-400 transition-colors"
                        >
                            Privacy
                        </Link>
                    </div>
                    <span>
                        &copy; {new Date().getFullYear()} Pundit Ledger. All
                        predictions verified.
                    </span>
                </div>
            </footer>
        </div>
    );
}
