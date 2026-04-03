# Monetization Strategy: Pundit Prediction Ledger

**Date**: 2026-04-02
**Status**: Active — canonical monetization plan
**Supersedes**: `zero_to_one_growth_strategy.md`, `roadmap_monetization_tracks.md`, `COMMERCIAL_MILESTONES.md`, `sprint_6_commercial_edge.md`, `sprint_7_realistic_monetization_limits.md`

---

## 1. Product

The **Pundit Prediction Ledger** is a cryptographically verified prediction tracking platform that holds sports media personalities accountable by scoring their public predictions against outcomes.

The free public site is the marketing engine. Paid tiers monetize depth, history, and programmatic access.

**Why this product, why now:** Sports media is saturated with loud, unaccountable prediction-making. No one systematically tracks whether these pundits are right. Bettors lose money tailing bad picks from personalities who face zero consequences for being wrong. This is a data gap that our existing ML pipeline, ingestion infrastructure, and NLP extraction capabilities are uniquely positioned to fill — we already built the hard parts (scraping, resolution scoring, cryptographic verification) for the broader Cap Alpha platform. The Pundit Ledger repackages that infrastructure into a consumer-facing product with a clear, emotionally resonant value proposition: "Was this pundit actually right?"

**Competitive scoring:** We also track the accuracy of other prediction sites and data platforms (PFF, Action Network, ESPN model picks, etc.) alongside individual pundits. This serves two purposes: (1) it positions us as the neutral arbiter — we grade everyone, including the platforms bettors already pay for, and (2) it creates a direct comparison that drives upgrades ("PFF's model scored 620, our model scored 780 — why are you paying them?").

---

## 2. The Pundit Credit Score

The core intellectual property of the platform. Every tracked pundit (and competing prediction platform) receives a **Pundit Credit Score** from 0-1000, modeled on the familiarity of a credit score. The score is a weighted composite of multiple dimensions, with full transparency into the underlying math.

### Composite Score (0-1000)
A single number that rolls up all dimensions into one comparable rank. Accompanied by a generalized **epithet** — a short behavioral label auto-generated from the pundit's scoring profile (e.g., "The Surgeon", "Coin Flip Artist", "Fade Material"). Epithets are derived from scoring patterns, not hardcoded to score ranges, so two pundits with similar composite scores can earn different epithets based on *how* they get there.

Epithet names are intentionally evocative but not legally tied to real people. They can be updated, seasonally rotated, or A/B tested over time as the product evolves.

### Scoring Dimensions

#### Free Tier — The Triangle (3 axes)
Visible to all users. Simple radar/triangle chart, instantly readable at a glance. Designed for screenshots and social sharing.

| Dimension | What It Measures | How It's Computed |
|-----------|-----------------|-------------------|
| **Accuracy** | Raw prediction hit rate | Correct predictions / total predictions, scaled 0-1000 |
| **Magnitude** | How far off the misses are | Weighted penalty for distance between prediction and outcome. A pundit who says "Chiefs by 3" and they win by 1 barely loses points. A pundit who says "Chiefs by 20" and they lose by 14 gets hammered. Small misses are forgiven; whoppers tank the score. |
| **Volume** | Sample size confidence | More predictions = more reliable score. Low denominators (e.g., 4 predictions) receive a confidence penalty that shrinks the score toward the mean until sufficient data exists. This prevents a pundit who went 3/3 from outranking someone who went 250/400. |

**Why these three:** They answer the three questions a bettor instinctively asks — "Is this person right?" (Accuracy), "When they're wrong, how bad is it?" (Magnitude), and "Do they make enough picks for me to trust the number?" (Volume). Everything else is a deeper cut.

#### Pro Tier — The Full Profile (6 axes)
Unlocked for Pro subscribers. Detailed radar chart with per-dimension breakdowns, visible numerators/denominators, and historical trend lines per axis.

| Dimension | What It Measures | How It's Computed |
|-----------|-----------------|-------------------|
| **Accuracy** | Same as free tier | Same as free tier, with per-category breakdown (spreads, totals, moneylines, props) |
| **Magnitude** | Same as free tier | Same, with distribution histogram (how many small misses vs. whoppers) |
| **Volume** | Same as free tier | Same, with prediction frequency over time |
| **Precision** | When they're confident, are they right? | Tracks predictions where the pundit expressed high confidence ("lock of the week", "guaranteed", "hammer this") vs. their hit rate on those picks specifically. High precision = their conviction calls actually hit. |
| **Consistency** | Are they steady or streaky? | Standard deviation of rolling accuracy windows. A pundit who's 70% one month and 30% the next scores lower on consistency than one who's steady at 50%. Bettors need to know if they can rely on the signal week to week. |
| **Boldness** | Do they take contrarian positions? | Measures how often the pundit goes against the consensus line or public betting percentages. High boldness + high accuracy = genuinely valuable signal. High boldness + low accuracy = a "Fade on Sight" profile. Low boldness = "Chalk Parrot" who just picks favorites. |

**Why these additional three:** They separate pundits who are genuinely skilled from those who are lucky or obvious. A pundit with 65% accuracy who only picks -300 favorites is less useful than one with 58% accuracy who consistently identifies value on underdogs. Precision, Consistency, and Boldness reveal *how* a pundit wins or loses, which is what serious bettors need to build a strategy around.

### Transparency Requirements
All scores show their underlying math:
- **Numerators and denominators** — "43/112 correct" not just "38%"
- **Low-denominator warnings** — if a dimension has insufficient data, the score is visually flagged and the weight in the composite is reduced
- **Recency weighting** — more recent predictions carry more weight in the composite, but historical scores are preserved for trend analysis

### Competitor Platform Scoring
In addition to individual pundits, the system scores competing prediction platforms (PFF, ESPN, Action Network model picks, etc.) using the same framework. This creates a direct apples-to-apples comparison between human pundits, algorithmic models, and our own model — and positions us as the neutral scorekeeper for the entire prediction ecosystem.

---

## 3. Audience

| Priority | Segment | What They Want | How They Find Us |
|----------|---------|----------------|------------------|
| **Primary** | Serious bettors | Know which pundits to trust before tailing picks | Organic social, Reddit, betting forums |
| **Secondary** | App builders / betting tools | Integrate pundit accuracy data into their products | API docs, developer communities, partnerships |
| **Tertiary** | Content creators / newsletters | Auto-generate "this pundit is 62% accurate" snippets | Embeddable widgets, social sharing |
| **Aspirational** | Sportsbooks, media companies, NFL front offices | Licensed data feeds, custom integrations | Manual outbound sales once credibility is proven |

**Why bettors first:** Bettors are the fastest path to revenue because they have direct financial incentive to care about pundit accuracy — bad picks cost them real money. They're already spending on data subscriptions (Action Network, PFF, The Athletic), so the purchase behavior exists. They congregate in discoverable online communities (Reddit, Discord, X), making acquisition cheaper than cold-outbounding to front offices. And they generate word-of-mouth: a bettor who avoids a bad play because of our data tells other bettors.

**Why not B2B first:** The previous strategy documents explored selling directly to NFL front offices at $20M/team/year. While the analytical foundation is sound (Sprint 6/7 proved the model's predictive value), B2B enterprise sales to NFL teams have prohibitively long cycles, require personal relationships we don't have, and demand a level of trust that only comes from an established public track record. The B2C play builds that track record. Enterprise becomes viable *after* we have public credibility, not before.

**Why app builders as secondary:** Betting apps and tools represent the highest-margin opportunity per customer. A single integration paying $99-499/mo is worth 10-50 individual Pro subscribers. But they won't integrate data from a platform nobody uses — they need to see the free site gain traction first. This is why they're secondary, not primary: they follow the B2C traction, they don't create it.

---

## 4. Tier Structure

### Free — $0/mo
The showcase. Drives organic traffic and social sharing.

- Top ~10-25 well-known pundits (Stephen A., Skip, McAfee, Schefter, etc.)
- Current season predictions and resolutions only
- Our model's predictions shown alongside for comparison
- No API access, no export
- Rate limited browsing (standard web)

**Why this boundary:** The free tier exists to be the marketing engine, not the product. By limiting to big-name pundits and current season, we create an inherently shareable, viral-ready experience ("Skip Bayless is only 38% accurate") that draws organic traffic. The big names are recognizable enough to drive clicks from social posts. Restricting to current season creates a natural upgrade moment — the user sees a pundit's score, wants to know "were they always this bad?", and hits the paywall. This is a proven content-gating pattern used by The Athletic and PFF.

### Pro — $10-20/mo
The volume play. Hundreds of individual subscribers at low friction.

- Full roster of all tracked pundits
- Complete historical data (all seasons)
- Per-prediction breakdowns, confidence intervals, category splits
- CSV export
- Brier score deep-dives, head-to-head comparisons
- Priority access to new features

**Why this price point:** The $10-20 range sits in the "impulse purchase" zone for the target audience. Serious bettors already pay for data — Action Network Pro ($9.99/mo), PFF Premium ($9.99/mo), The Athletic ($8.99/mo). Pricing at parity means we're not asking for new budget behavior; we're competing for an existing line item. Going higher ($30-50) would narrow the funnel to only professional bettors and lengthen the decision cycle. Going lower ($5) signals "toy" rather than "tool." The $10-20 range optimizes for the stated priority: least friction to getting money in the bank.

### API — $99-499/mo
The margin play. Builders integrating data into their own products.

- Full programmatic REST API access
- All pundit data, all history, structured JSON
- Real-time webhooks (prediction resolution, score changes)
- Bulk data endpoints
- Higher rate limits (tiered by plan level)
- API key self-service via dashboard

**Why this price point and why API is separate from Pro:** A betting app integrating our pundit accuracy scores into their product gets value that is 10-100x what an individual bettor gets — they're reselling our data to their users, saving months of engineering, and differentiating their product. Pricing this at $10/mo alongside individuals would be leaving enormous value on the table. The $99-499 range is competitive with comparable sports data APIs (SportsDataIO charges $100-500/mo for structured feeds). The tiered range allows us to capture indie builders ($99) and growth-stage apps ($499) without forcing enterprise-level negotiations. Self-service API key management is critical here — the buyer should be able to start integrating within minutes, not after a sales call.

### Enterprise — $2,000+/mo
Manual sales. High-value data licensing deals.

- Raw database feeds / full data dumps
- SLA guarantees (uptime, latency, support response)
- Custom queries and integrations
- Webhook integrations to internal systems
- Dedicated support contact
- Custom pundit tracking (add specific personalities on request)
- This is where the old "bespoke audit" and "front office" play lives — sold manually once the platform has credibility

**Why keep this tier:** The Sprint 6/7 analysis proved the underlying model has genuine predictive value for NFL front offices and agencies. That B2B opportunity isn't dead — it's just premature without a public track record. Enterprise becomes the long-game payoff: once the free site has thousands of users and the data's credibility is established publicly, inbound enterprise interest follows naturally. A single enterprise deal at $2K+/mo is worth 200+ Pro subscribers. This tier also absorbs the "bespoke audit" consulting model from the old strategy as a fallback — if self-serve revenue stalls, we can manually sell custom reports backed by the Ledger's credibility.

---

## 5. Launch Sequence

### Phase 1: Free Public Site (Current Priority)
Ship the free leaderboard with big-name pundits and current season data. This is the marketing engine — every shareable screenshot of "Skip Bayless is 38% accurate" drives organic growth.

**Dependencies (done or in progress):**
- [x] Media ingestion pipeline (GH-#78)
- [x] Prediction resolution engine (GH-#112)
- [x] Scorecard API endpoints (GH-#113)
- [ ] NLP assertion extraction (GH-#79)
- [ ] Landing page & email waitlist (GH-#116)

### Phase 2: Stripe & Pro Tier
Wire in payments. The goal is first dollar of revenue from a stranger.

**Dependencies:**
- [ ] Stripe integration (part of GH-#115)
- [ ] Pro feature gating (full history, full roster, export)
- [ ] User accounts / auth (Clerk)

### Phase 3: API Tier
Self-service API key management and tiered access.

**Dependencies:**
- [ ] API key generation & management (GH-#115)
- [ ] Rate limiting middleware per tier
- [ ] Usage tracking & dashboard
- [ ] OpenAPI/Swagger docs (GH-#108, #109)

### Phase 4: Enterprise
Manual outbound once Phases 1-3 prove the data's value.

- Identify 5-10 potential enterprise targets (betting apps, media companies)
- Build custom data export pipeline
- Legal/licensing agreement template

---

## 6. Unit Economics (Targets)

| Metric | 3-Month Target | 6-Month Target | 12-Month Target |
|--------|---------------|----------------|-----------------|
| Free users (MAU) | 500 | 2,000 | 10,000 |
| Pro subscribers | 10 | 50 | 200 |
| API subscribers | 0 | 2 | 10 |
| Enterprise deals | 0 | 0 | 1 |
| MRR | $100-200 | $1,000-2,000 | $5,000-10,000 |

**Cost to serve (estimated):**
- BigQuery: ~$50-100/mo at moderate query volume
- Vercel/hosting: Free tier → $20/mo at scale
- Stripe fees: 2.9% + $0.30 per transaction
- Data vendor (SportsDataIO): ~$50/mo current plan

**Break-even**: ~15-20 Pro subscribers covers infrastructure costs.

---

## 7. Contingency Plans

### If API revenue is slow to materialize (< $500 API MRR after 60 days of Phase 3)
**Pivot to web-first premium content model:**
- Move historical depth behind the Pro paywall on the web (not just API)
- Publish weekly "Sharp vs. Loud" reports (premium newsletter format)
- Expand social marketing specifically targeting betting communities (Reddit, X betting accounts, Discord servers)
- Add features based on user requests to increase stickiness

### If Pro subscriptions underperform (< 20 subs after 90 days)
**Reduce friction further:**
- Drop Pro to $5/mo or offer annual at $49/yr
- Expand the free tier slightly to grow the funnel
- Add affiliate/referral links to sportsbooks from pundit profiles (revenue without requiring subscriptions)
- Explore sponsored pundit profiles (pundits/networks pay for premium placement or verification badges)

### If the entire B2C play stalls
**Fall back to B2B consulting model:**
- Use the Ledger's data as credibility proof for bespoke "Franchise Liquidity Audit" reports ($1,500-2,500 each)
- Target sports media outlets who want accountability data for their own editorial
- Expert network consulting (Guidepoint, GLG) leveraging the platform as portfolio proof

---

## 8. Customer Acquisition

### Primary channels (B2C)
- **Reddit**: r/sportsbook, r/nfl, r/fantasyfootball — share specific pundit accuracy screenshots
- **X/Twitter**: Tag pundits directly with their accuracy scores (inherently viral)
- **Betting forums/Discords**: Demonstrate value with free data
- **SEO**: "Is [Pundit Name] accurate?" queries

### Secondary channels (B2B)
- **Developer communities**: API docs, "build with our data" content
- **Direct outreach**: Cold email to betting app founders with sample data
- **Partnerships**: Offer free API access to small betting tools in exchange for attribution

### What's deprecated
The guerrilla launch plan targeting NFL GMs and hiring managers is no longer the primary GTM. That audience maps to Enterprise tier and will be pursued manually later, not through lumpy mail and LinkedIn sniper ads.

---

## 9. Key Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| B2B vs B2C first | B2C | Faster feedback loop, lower sales cycle, proves product-market fit. B2B enterprise sales to NFL teams require relationships and trust we haven't earned yet. B2C builds the public track record that makes B2B viable later. |
| Open core vs closed | Open core | Free site is the marketing engine; monetize API and depth. The viral loop depends on free users sharing pundit scores on social media — gating the basic product kills that loop before it starts. |
| Pricing model | Tiered flat rate | Predictable revenue, low cognitive load for buyers. Metered pricing (per-request) creates anxiety and unpredictable bills. Flat tiers let users know exactly what they're paying. |
| Pro price point | $10-20/mo | Competitive with Action Network ($9.99), PFF ($9.99), The Athletic ($8.99). Optimizes for adoption speed — sits in the "impulse purchase" zone for bettors who already pay for data subscriptions. |
| API price point | $99-499/mo | High enough to capture B2B value (a betting app reselling our data gets 10-100x ROI), low enough for indie builders to start without a sales call. Competitive with SportsDataIO ($100-500/mo). |
| First paying customer | Individual bettor (Pro tier) | Lowest friction path to first dollar. No sales cycle, no enterprise procurement, no legal review. Self-serve signup and pay. |
| Historical data as paywall | Yes — free = current season only | Clean, defensible line. Creates a natural upgrade moment: user sees a score, wants to know the trend, hits the wall. Proven content-gating pattern (The Athletic, PFF). |
| Scoring system | Multi-dimensional Pundit Credit Score (0-1000) | A single accuracy percentage is boring and incomplete. The credit score metaphor is instantly understood by Americans, creates emotional resonance (everyone knows what a 400 vs. 800 means), and the multi-axis breakdown (free: 3 axes, Pro: 6 axes) is a natural paywall upgrade. |
| Competitor platform scoring | Track other sites (PFF, ESPN, Action Network) alongside pundits | Positions us as the neutral arbiter of the entire prediction ecosystem. Creates direct "why pay them when we scored higher?" comparisons that drive conversions. Also generates press: "PFF's model ranked 14th behind three random podcasters." |
| Epithet naming | Archetype-based, not real-pundit-named | Original plan to name tiers after real pundits (e.g., "The Bayless") was viral but legally risky. Archetype epithets ("The Surgeon", "Fade Material") are safer, still fun, and can be rotated/A/B tested over time. |
| Score + epithet on free tier | Yes — visible to all | The composite score and epithet are the single most shareable elements. Gating them behind Pro would cripple the viral loop. The detailed 6-axis breakdown is the Pro upgrade, not the headline number. |
