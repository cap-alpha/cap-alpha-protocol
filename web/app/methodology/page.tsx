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
    Newspaper,
    ListFilter,
    Database,
    Cpu,
    ExternalLink,
    BookOpen,
    Calculator,
    Ban,
    GitBranch,
    Github,
} from "lucide-react";

export const metadata: Metadata = {
    title: "Methodology | Pundit Ledger",
    description:
        "How Cap Alpha independently audits sports media pundits — claim type taxonomy, scoring formula, VOID criteria, and dispute process.",
};

// FAQ JSON-LD — surfaces the public adjudication taxonomy + scoring rules to
// search engines so the definitions show up in rich results. Issue #830.
const FAQ_JSONLD = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
        {
            "@type": "Question",
            name: "What is the difference between a prediction and a report?",
            acceptedAnswer: {
                "@type": "Answer",
                text:
                    "A prediction is an analyst asserting a future outcome will occur (e.g., 'The Chiefs will win the Super Bowl') — it resolves CORRECT or INCORRECT when the event happens. A report relays information from a source about current state (e.g., 'The Eagles are looking to trade for a WR') — if the underlying circumstances change before resolution (the deal falls through, the player was never actually available), the claim resolves VOID rather than INCORRECT. We score predictions, not reports.",
            },
        },
        {
            "@type": "Question",
            name: "What kinds of claims are excluded from scoring?",
            acceptedAnswer: {
                "@type": "Answer",
                text:
                    "Subjective opinions (e.g., 'Mahomes is the best QB ever'), rhetorical questions, jokes, analogies, hedges so vague they cannot be falsified, and any claim with no objective resolution criterion. These are filtered at extraction and never enter the prediction ledger.",
            },
        },
        {
            "@type": "Question",
            name: "When does a prediction resolve as VOID?",
            acceptedAnswer: {
                "@type": "Answer",
                text:
                    "VOID applies when (1) the event the prediction was about was cancelled or never occurred (game cancelled, draft pick skipped); (2) a report was accurate at the time but circumstances changed (trade fell through, injury healed before the game); (3) a conditional claim's premise never resolved (the 'if X' condition never happened); or (4) resolution criteria are ambiguous and no authoritative ground truth exists. VOID claims are excluded from accuracy, Brier, and weighted-score aggregates.",
            },
        },
        {
            "@type": "Question",
            name: "How is a pundit's accuracy score calculated?",
            acceptedAnswer: {
                "@type": "Answer",
                text:
                    "Each resolved prediction receives a binary_correct value (1 for CORRECT, 0 for INCORRECT, 0.5 for PARTIAL). The pundit's headline accuracy is the simple mean of binary_correct across all non-VOID, non-PENDING resolutions. A confidence-weighted score and a Brier score are also computed on predictions where the pundit expressed a probability — these reward calibration, not just hit rate.",
            },
        },
        {
            "@type": "Question",
            name: "What is a Brier score?",
            acceptedAnswer: {
                "@type": "Answer",
                text:
                    "The Brier score measures how well a pundit's stated confidence matches reality. For a single probability prediction p with outcome o (1 if correct, 0 if not), the Brier score is (p − o)². The pundit's overall Brier score is the mean across all probabilistic predictions. Lower is better — 0.0 is perfect, 0.25 is uninformative (chance), and 1.0 is maximally wrong with maximum confidence.",
            },
        },
        {
            "@type": "Question",
            name: "How can I dispute a rating?",
            acceptedAnswer: {
                "@type": "Answer",
                text:
                    "Open a public dispute by filing a GitHub issue at github.com/ucalegon206/cap-alpha-protocol/issues with the prediction URL, the resolution shown (CORRECT/INCORRECT/VOID), the resolution you believe is correct, and a citation to an authoritative source. Alternatively email corrections@cap-alpha.co. Confirmed scoring errors result in a correction entry — the original prediction remains visible with the updated resolution and a public note explaining the change. The ledger is immutable; nothing is ever silently overwritten.",
            },
        },
    ],
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
            <h2 className="font-display text-3xl sm:text-4xl font-black tracking-tight text-white">
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
            {/* FAQ structured data — surfaces taxonomy + scoring rules to search engines (#830) */}
            <script
                type="application/ld+json"
                // eslint-disable-next-line react/no-danger
                dangerouslySetInnerHTML={{ __html: JSON.stringify(FAQ_JSONLD) }}
            />
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
                    <h1 className="font-display text-4xl sm:text-5xl font-black tracking-tight leading-[1.1]">
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

            {/* Claim Type Taxonomy — the public adjudication contract (#830) */}
            <section
                id="claim-taxonomy"
                className="w-full px-6 py-20 border-t border-zinc-900"
            >
                <div className="max-w-5xl mx-auto">
                    <SectionHeader
                        label="Taxonomy"
                        title="The Claim Type Taxonomy"
                        subtitle="The Woj/Schefter distinction matters. A failed prediction is a bad call. A report whose underlying deal fell through is not the same thing, and we score it differently. This is the contract."
                    />

                    {/* The headline table — public, plain-language */}
                    <div className="overflow-x-auto rounded-2xl border border-zinc-800 bg-zinc-900/40">
                        <table className="w-full text-sm">
                            <thead className="bg-zinc-900/80 text-zinc-300">
                                <tr className="text-left">
                                    <th className="px-4 py-3 font-semibold">Type</th>
                                    <th className="px-4 py-3 font-semibold">Definition</th>
                                    <th className="px-4 py-3 font-semibold">Example</th>
                                    <th className="px-4 py-3 font-semibold">How we score it</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-800/80 text-zinc-300">
                                <tr>
                                    <td className="px-4 py-4 align-top">
                                        <span className="font-semibold text-emerald-400">
                                            Prediction
                                        </span>
                                        <div className="text-xs font-mono text-zinc-500 mt-1">
                                            speech_act_type: assertion
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Analyst asserts a future outcome will occur.
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400 italic">
                                        &ldquo;The Eagles will win the Super Bowl.&rdquo;
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        CORRECT or INCORRECT at resolution. Scored.
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-4 py-4 align-top">
                                        <span className="font-semibold text-yellow-400">
                                            Report
                                        </span>
                                        <div className="text-xs font-mono text-zinc-500 mt-1">
                                            speech_act_type: recall
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Analyst relays insider information about
                                        the current state of affairs.
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400 italic">
                                        &ldquo;The Eagles are looking to trade for a
                                        WR per sources.&rdquo;
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        CORRECT if independently confirmed. VOID if
                                        the underlying deal/situation falls through.
                                        We score predictions, not reports.
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-4 py-4 align-top">
                                        <span className="font-semibold text-zinc-300">
                                            Conditional
                                        </span>
                                        <div className="text-xs font-mono text-zinc-500 mt-1">
                                            speech_act_type: conditional
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Outcome depends on a contingent event.
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400 italic">
                                        &ldquo;If they draft a left tackle, the line
                                        will be top-10.&rdquo;
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Scored only when the condition resolves
                                        cleanly. VOID if the &ldquo;if&rdquo;
                                        premise never occurs.
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-4 py-4 align-top">
                                        <span className="font-semibold text-zinc-500">
                                            Opinion / Take
                                        </span>
                                        <div className="text-xs font-mono text-zinc-500 mt-1">
                                            speech_act_type: opinion
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Subjective qualitative assessment with no
                                        falsifiable outcome.
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400 italic">
                                        &ldquo;Mahomes is the best QB ever.&rdquo;
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Not scored. Filtered at extraction; never
                                        enters the prediction ledger.
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-4 py-4 align-top">
                                        <span className="font-semibold text-zinc-500">
                                            Commentary / Analogy / Joke / Rhetorical
                                        </span>
                                        <div className="text-xs font-mono text-zinc-500 mt-1">
                                            speech_act_type: commentary,
                                            analogy, joke, rhetorical_question, hedge
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Analysis, comparison, humor, hedged uncertainty,
                                        or rhetorical framing — no testable outcome.
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400 italic">
                                        &ldquo;They&apos;re playing like it&apos;s
                                        1985.&rdquo;
                                    </td>
                                    <td className="px-4 py-4 align-top text-zinc-400">
                                        Not scored. Filtered at extraction.
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    {/* Schema mapping — meets acceptance criterion: public taxonomy maps 1:1 to schema */}
                    <div className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
                        <div className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest text-zinc-400">
                            <GitBranch className="w-4 h-4" />
                            Schema Mapping
                        </div>
                        <p className="text-sm text-zinc-400 leading-relaxed">
                            The public types above map 1:1 to the internal
                            <span className="font-mono text-emerald-400">
                                {" "}speech_act_type{" "}
                            </span>
                            field documented in
                            <span className="font-mono text-zinc-300">
                                {" "}pipeline/src/domain_protocol.py
                            </span>
                            . Only claims with
                            <span className="font-mono text-emerald-400">
                                {" "}speech_act_type{" "}
                            </span>
                            of
                            <span className="font-mono"> assertion</span>,
                            <span className="font-mono"> conditional</span>, or
                            <span className="font-mono"> recall</span> are
                            promoted to the scoreable prediction ledger.
                            Everything else is filtered upstream.
                        </p>
                    </div>
                </div>
            </section>

            {/* Scoring Formula — explicit, audit-friendly math (#830) */}
            <section
                id="scoring-formula"
                className="w-full px-6 py-20 border-t border-zinc-900"
            >
                <div className="max-w-3xl mx-auto">
                    <SectionHeader
                        label="Scoring"
                        title="How a Prediction Is Scored"
                        subtitle="Every resolved prediction is reduced to three numbers. The math is public so anyone can replicate it."
                    />

                    <div className="space-y-6">
                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-3">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    binary_correct
                                </h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                The raw outcome bit, in <span className="font-mono">{`{0, 0.5, 1}`}</span>:
                            </p>
                            <ul className="text-sm text-zinc-400 space-y-1 ml-1">
                                <li>
                                    <span className="font-mono text-emerald-400">1.0</span>{" "}
                                    — CORRECT (claim came true)
                                </li>
                                <li>
                                    <span className="font-mono text-yellow-400">0.5</span>{" "}
                                    — PARTIAL (e.g., predicted score within 3, partial credit)
                                </li>
                                <li>
                                    <span className="font-mono text-red-400">0.0</span>{" "}
                                    — INCORRECT (claim was wrong)
                                </li>
                            </ul>
                            <p className="text-sm text-zinc-500 mt-2 leading-relaxed">
                                VOID and PENDING outcomes are <em>excluded</em> — they do
                                not appear in the denominator of any aggregate.
                            </p>
                            <div className="rounded-lg border border-zinc-800 bg-black/40 p-3 font-mono text-xs text-zinc-300">
                                accuracy = mean(binary_correct) over resolved, non-VOID predictions
                            </div>
                        </div>

                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-3">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <Calculator className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    weighted_score
                                </h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Confidence-adjusted accuracy. A pundit who says
                                &ldquo;lock of the week&rdquo; (confidence 0.95) and
                                misses pays a bigger penalty than one who hedges at 0.55
                                and misses. The formula:
                            </p>
                            <div className="rounded-lg border border-zinc-800 bg-black/40 p-3 font-mono text-xs text-zinc-300">
                                weighted_score = mean(binary_correct × confidence)
                                <br />
                                {"    "}where confidence ∈ [0.5, 1.0]
                            </div>
                            <p className="text-sm text-zinc-500 leading-relaxed">
                                Confidence is extracted from the language of the
                                claim (&ldquo;guaranteed&rdquo;, &ldquo;might&rdquo;,
                                &ldquo;hammer this&rdquo;) when a pundit doesn&apos;t
                                state a probability directly. Predictions where
                                confidence can&apos;t be inferred default to 0.5 and
                                contribute neutrally.
                            </p>
                        </div>

                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-3">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <BarChart3 className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    Brier score
                                </h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                The gold standard for measuring calibration. For each
                                probabilistic prediction with stated probability{" "}
                                <span className="font-mono">p</span> and outcome{" "}
                                <span className="font-mono">o ∈ {`{0, 1}`}</span>:
                            </p>
                            <div className="rounded-lg border border-zinc-800 bg-black/40 p-3 font-mono text-xs text-zinc-300">
                                brier_i = (p_i − o_i)²
                                <br />
                                brier_overall = mean(brier_i)
                            </div>
                            <ul className="text-sm text-zinc-400 space-y-1 mt-2">
                                <li>
                                    <span className="font-mono text-emerald-400">0.00</span>{" "}
                                    — perfect calibration
                                </li>
                                <li>
                                    <span className="font-mono text-yellow-400">0.25</span>{" "}
                                    — uninformative (random guessing at 50%)
                                </li>
                                <li>
                                    <span className="font-mono text-red-400">1.00</span>{" "}
                                    — maximally wrong with maximum confidence
                                </li>
                            </ul>
                            <p className="text-sm text-zinc-500 leading-relaxed">
                                Lower is better. The Brier score rewards pundits who
                                say &ldquo;60% confident&rdquo; and are right 60% of
                                the time — not the ones who say &ldquo;lock&rdquo;
                                on everything and hit 52%.
                            </p>
                        </div>

                        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6">
                            <div className="flex items-start gap-3">
                                <BookOpen className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
                                <div className="space-y-2 text-sm text-zinc-300">
                                    <p className="font-semibold text-zinc-200">
                                        Why three numbers, not one?
                                    </p>
                                    <p className="text-zinc-400 leading-relaxed">
                                        A pundit can have high <span className="font-mono">accuracy</span>{" "}
                                        and a bad <span className="font-mono">Brier score</span> — they hit
                                        often but always at low confidence. Or vice versa: a contrarian who
                                        calls underdogs with 70% confidence and hits 30% of the time looks
                                        good on accuracy variance but Brier exposes the calibration gap.
                                        Each number catches a different failure mode.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* VOID Criteria — explicit examples (#830 acceptance criterion: ≥ 4 concrete examples) */}
            <section
                id="void-criteria"
                className="w-full px-6 py-20 border-t border-zinc-900"
            >
                <div className="max-w-3xl mx-auto">
                    <SectionHeader
                        label="VOID"
                        title="When a Prediction Becomes VOID"
                        subtitle="VOID is not the same as wrong. VOID means the claim cannot be fairly judged — and we exclude it from every aggregate rather than silently counting it against the pundit."
                    />

                    <div className="space-y-6">
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
                            <div className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest text-zinc-400">
                                <Ban className="w-4 h-4" />
                                The four VOID conditions
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                A prediction resolves VOID when{" "}
                                <span className="text-zinc-200 font-medium">
                                    any one
                                </span>{" "}
                                of the following applies:
                            </p>
                            <ol className="text-sm text-zinc-300 space-y-2 list-decimal list-inside marker:text-emerald-400">
                                <li>
                                    The underlying event the claim depends on{" "}
                                    <span className="text-zinc-400">
                                        was cancelled or never occurred
                                    </span>
                                    .
                                </li>
                                <li>
                                    A report was accurate at the time but{" "}
                                    <span className="text-zinc-400">
                                        circumstances changed before resolution
                                    </span>{" "}
                                    (trade fell through, injury healed,
                                    player traded).
                                </li>
                                <li>
                                    A conditional claim&apos;s premise (the
                                    &ldquo;if X&rdquo;){" "}
                                    <span className="text-zinc-400">
                                        never resolved
                                    </span>
                                    .
                                </li>
                                <li>
                                    Resolution criteria are{" "}
                                    <span className="text-zinc-400">
                                        ambiguous and no authoritative ground
                                        truth exists
                                    </span>
                                    . An explanation is attached to every
                                    ambiguity-based VOID.
                                </li>
                            </ol>
                        </div>

                        {/* Four concrete examples — meets the issue's "≥4 concrete examples" acceptance criterion */}
                        <div className="space-y-4">
                            <h3 className="text-lg font-bold text-white">
                                Worked examples
                            </h3>

                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-2">
                                <p className="text-xs font-mono uppercase tracking-widest text-yellow-400">
                                    Example 1 — Report, deal fell through
                                </p>
                                <p className="text-sm italic text-zinc-300">
                                    &ldquo;The Eagles are finalizing a trade for
                                    DK Metcalf, per sources.&rdquo; — no trade
                                    materializes before the deadline.
                                </p>
                                <p className="text-sm text-zinc-400">
                                    <span className="font-semibold text-zinc-200">
                                        Resolution:
                                    </span>{" "}
                                    VOID. The pundit may have accurately
                                    reported the state of negotiations; the
                                    deal&apos;s collapse is not a failed
                                    prediction. We do not score reports.
                                </p>
                            </div>

                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-2">
                                <p className="text-xs font-mono uppercase tracking-widest text-yellow-400">
                                    Example 2 — Cancelled event
                                </p>
                                <p className="text-sm italic text-zinc-300">
                                    &ldquo;Vikings -2.5 on Sunday&rdquo; — the
                                    game is postponed and never rescheduled in
                                    the same season.
                                </p>
                                <p className="text-sm text-zinc-400">
                                    <span className="font-semibold text-zinc-200">
                                        Resolution:
                                    </span>{" "}
                                    VOID. The event the claim was about no
                                    longer exists. Counting this against the
                                    pundit would be unfair.
                                </p>
                            </div>

                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-2">
                                <p className="text-xs font-mono uppercase tracking-widest text-yellow-400">
                                    Example 3 — Conditional premise never met
                                </p>
                                <p className="text-sm italic text-zinc-300">
                                    &ldquo;If Mahomes plays, Chiefs win by
                                    10+.&rdquo; — Mahomes is inactive on game
                                    day.
                                </p>
                                <p className="text-sm text-zinc-400">
                                    <span className="font-semibold text-zinc-200">
                                        Resolution:
                                    </span>{" "}
                                    VOID. The conditional was never triggered.
                                    A pundit cannot be scored on a claim whose
                                    premise didn&apos;t happen.
                                </p>
                            </div>

                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-2">
                                <p className="text-xs font-mono uppercase tracking-widest text-yellow-400">
                                    Example 4 — Ambiguous resolution criteria
                                </p>
                                <p className="text-sm italic text-zinc-300">
                                    &ldquo;The Bears will have a top-tier
                                    defense this year.&rdquo; — &ldquo;top-tier&rdquo;
                                    isn&apos;t defined; the team finishes 12th
                                    by DVOA and 6th by yards allowed.
                                </p>
                                <p className="text-sm text-zinc-400">
                                    <span className="font-semibold text-zinc-200">
                                        Resolution:
                                    </span>{" "}
                                    VOID with explanation. If we had a clear
                                    quantitative threshold from the pundit (top
                                    10 in DVOA, top 5 in points allowed) we
                                    would score it. Without one, scoring is
                                    arbitrary and we say so publicly.
                                </p>
                            </div>
                        </div>

                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-2">
                            <div className="flex items-start gap-3">
                                <AlertTriangle className="w-5 h-5 text-yellow-400 mt-0.5 shrink-0" />
                                <div className="space-y-2 text-sm">
                                    <p className="font-semibold text-zinc-200">
                                        VOID is auditable, not a get-out-of-jail card.
                                    </p>
                                    <p className="text-zinc-400 leading-relaxed">
                                        Every VOID resolution is logged with a
                                        reason code and remains visible on the
                                        prediction&apos;s page. If a pundit
                                        accumulates an unusual rate of VOIDs,
                                        that pattern is itself visible — and
                                        suggestive — in the public record.
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
                            <Link
                                href="/verify"
                                className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                Verify the ledger
                                <ArrowRight className="w-3 h-3" />
                            </Link>
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
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-3">
                            <div className="flex items-center gap-2">
                                <Github className="w-4 h-4 text-emerald-400" />
                                <h4 className="font-semibold text-zinc-200">
                                    Dispute publicly on GitHub
                                </h4>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                We track adjudication disputes as public issues so
                                the discussion and outcome are part of the record.
                                File a dispute with the prediction URL, the current
                                resolution, the resolution you believe is correct,
                                and a link to authoritative source data.
                            </p>
                            <a
                                href="https://github.com/ucalegon206/cap-alpha-protocol/issues/new?labels=dispute&title=Dispute%3A%20%5Bprediction-id%5D"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1.5 text-sm text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                Open a dispute issue
                                <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                        </div>
                        <p className="text-sm text-zinc-500">
                            Or email{" "}
                            <a
                                href="mailto:corrections@cap-alpha.co"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                corrections@cap-alpha.co
                            </a>
                            . Methodology questions:{" "}
                            <a
                                href="mailto:support@cap-alpha.co"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                support@cap-alpha.co
                            </a>
                            .
                        </p>
                    </div>
                </div>
            </section>

            {/* Editorial Standards */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto">
                    <SectionHeader
                        label="Editorial Standards"
                        title="Editorial Standards"
                        subtitle="Our commitment to independence, transparency, and consistent editorial practice."
                    />

                    <div className="space-y-8">
                        {/* 1. Editorial Independence */}
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <Newspaper className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    Editorial Independence
                                </h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Cap Alpha is not affiliated with any pundit, media
                                organization, sports team, league, or sportsbook. Pundits
                                are selected based on volume of public predictions. Scoring
                                is automated and applies uniformly —{" "}
                                <span className="text-zinc-200 font-medium">
                                    no pundit can pay to be excluded, promoted, or re-scored.
                                </span>
                            </p>
                        </div>

                        {/* 2. Claim Selection Policy */}
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <ListFilter className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    Claim Selection Policy
                                </h3>
                            </div>
                            <div className="space-y-3 text-sm">
                                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-2">
                                    <p className="font-semibold text-emerald-400 text-xs font-mono uppercase tracking-widest">
                                        Categories Tracked
                                    </p>
                                    <p className="text-zinc-300">
                                        Game outcome, player performance, trade, draft pick,
                                        injury, contract
                                    </p>
                                </div>
                                <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 space-y-2">
                                    <p className="font-semibold text-red-400 text-xs font-mono uppercase tracking-widest">
                                        Excluded
                                    </p>
                                    <p className="text-zinc-400">
                                        Entertainment predictions, non-sports content, and
                                        ambiguous claims that cannot be objectively resolved
                                    </p>
                                </div>
                                <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-4 space-y-2">
                                    <p className="font-semibold text-zinc-300 text-xs font-mono uppercase tracking-widest">
                                        Quality Threshold
                                    </p>
                                    <p className="text-zinc-400">
                                        A minimum testability threshold (testability score ≥ 0.6)
                                        is required for a claim to enter the ledger
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* 3. Resolution Sources */}
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <Database className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    Resolution Sources
                                </h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Outcomes are determined from authoritative public sources:
                            </p>
                            <div className="space-y-2 text-sm">
                                <div className="flex items-start gap-2">
                                    <span className="mt-1.5 w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                                    <p className="text-zinc-400">
                                        <span className="font-semibold text-zinc-200">
                                            Sports Reference / PFR
                                        </span>{" "}
                                        — game outcomes and box scores
                                    </p>
                                </div>
                                <div className="flex items-start gap-2">
                                    <span className="mt-1.5 w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                                    <p className="text-zinc-400">
                                        <span className="font-semibold text-zinc-200">
                                            Spotrac and Over the Cap
                                        </span>{" "}
                                        — contracts and transactions
                                    </p>
                                </div>
                                <div className="flex items-start gap-2">
                                    <span className="mt-1.5 w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                                    <p className="text-zinc-400">
                                        <span className="font-semibold text-zinc-200">
                                            Official league transaction wire
                                        </span>{" "}
                                        — roster moves
                                    </p>
                                </div>
                            </div>
                            <p className="text-sm text-zinc-500">
                                Edge cases resolved by manual review are logged and
                                attributed.
                            </p>
                        </div>

                        {/* 4. Extraction Transparency */}
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                                    <Cpu className="w-5 h-5 text-emerald-400" />
                                </div>
                                <h3 className="text-lg font-bold text-white">
                                    Extraction Transparency
                                </h3>
                            </div>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Predictions are extracted using LLM assistance. The model
                                version and prompt version are logged with each prediction.
                                The raw verbatim quote is always stored alongside the
                                extracted structured claim.{" "}
                                <span className="text-zinc-200 font-medium">
                                    Both are publicly visible on every prediction card.
                                </span>
                            </p>
                            <Link
                                href="/legal/disclosure"
                                className="inline-flex items-center gap-1.5 text-sm text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                View full disclosure
                                <ExternalLink className="w-3.5 h-3.5" />
                            </Link>
                        </div>
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

        </div>
    );
}
