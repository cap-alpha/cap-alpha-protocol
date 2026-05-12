import { unsubscribeUrl, BASE_URL } from './email'

interface EmailProps {
    email: string
    firstName?: string
}

// ---------------------------------------------------------------------------
// Resolution alert email types
// ---------------------------------------------------------------------------

export interface ResolvedPrediction {
    pundit_name: string
    pundit_id: string
    claim_text: string
    outcome: 'CORRECT' | 'INCORRECT'
    resolved_at: string | null
    category: string
    prediction_hash: string
}

export interface ResolutionAlertEmailProps {
    email: string
    firstName?: string
    resolutions: ResolvedPrediction[]
}

// ---------------------------------------------------------------------------
// Weekly digest email types
// ---------------------------------------------------------------------------

export interface DigestPunditEntry {
    pundit_id: string
    pundit_name: string
    accuracy_rate: number | null
    resolved_this_week: ResolvedPrediction[]
    pending_count: number
}

export interface WeeklyDigestEmailProps {
    email: string
    firstName?: string
    pundits: DigestPunditEntry[]
    weekOf: string // e.g. "May 6 – May 12, 2026"
}

const PHYSICAL_ADDRESS = '1111B S Governors Ave STE 6225, Dover, DE 19904'

function baseLayout(content: string, unsubUrl: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cap Alpha</title>
</head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#111111;border-radius:8px;overflow:hidden;border:1px solid #222222;">
          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;border-bottom:1px solid #222222;">
              <a href="${BASE_URL}" style="text-decoration:none;">
                <span style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">Cap Alpha</span>
                <span style="font-size:12px;color:#888888;margin-left:8px;text-transform:uppercase;letter-spacing:1px;">Protocol</span>
              </a>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding:32px 40px;">
              ${content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;border-top:1px solid #222222;background:#0d0d0d;">
              <p style="margin:0 0 8px;font-size:12px;color:#555555;line-height:1.6;">
                Cap Alpha · ${PHYSICAL_ADDRESS}
              </p>
              <p style="margin:0;font-size:12px;color:#555555;">
                <a href="${unsubUrl}" style="color:#888888;text-decoration:underline;">Unsubscribe</a>
                &nbsp;·&nbsp;
                <a href="${BASE_URL}/legal/privacy" style="color:#888888;text-decoration:underline;">Privacy Policy</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`
}

export function renderWelcomeEmail({ email, firstName }: EmailProps): string {
    const greeting = firstName ? `Hi ${firstName},` : 'Welcome,'
    const unsubUrl = unsubscribeUrl(email)
    const content = `
      <h1 style="margin:0 0 16px;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">
        The NFL pundit scorecard you've been waiting for.
      </h1>
      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">${greeting}</p>
      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        You just joined Cap Alpha — the first platform that holds NFL pundits accountable with a
        cryptographic prediction ledger.
      </p>
      <p style="margin:0 0 24px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        Every prediction made on podcasts, columns, and YouTube gets extracted, stored on a
        tamper-evident SHA-256 chain, and scored against real outcomes using Brier scoring.
        No more "I told you so" without the receipts.
      </p>

      <!-- Example scorecard callout -->
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;margin:0 0 24px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 8px;font-size:12px;color:#888888;text-transform:uppercase;letter-spacing:1px;">Example Prediction</p>
            <p style="margin:0 0 4px;font-size:15px;color:#ffffff;font-weight:600;">"Lamar Jackson will throw 40+ TDs in 2024"</p>
            <p style="margin:0 0 12px;font-size:13px;color:#888888;">Made Jan 2024 · 11 months in advance</p>
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#16a34a;border-radius:4px;padding:4px 10px;">
                  <span style="font-size:12px;color:#ffffff;font-weight:600;">✓ CORRECT</span>
                </td>
                <td style="padding-left:12px;">
                  <span style="font-size:13px;color:#aaaaaa;">Timeliness multiplier: 1.8× · Brier: 0.12</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 24px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        We're tracking <strong style="color:#ffffff;">500+ predictions</strong> across
        <strong style="color:#ffffff;">dozens of pundits</strong>. Find out who's actually
        worth listening to.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:#2563eb;border-radius:6px;">
            <a href="${BASE_URL}/ledger" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">
              Explore the Pundit Ledger →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:#666666;line-height:1.6;">
        More coming your way over the next week — including how to get the most out of Cap Alpha
        and when to consider going Pro.
      </p>
    `
    return baseLayout(content, unsubUrl)
}

export function renderDay3Email({ email, firstName }: EmailProps): string {
    const greeting = firstName ? `Hey ${firstName},` : 'Hey,'
    const unsubUrl = unsubscribeUrl(email)
    const content = `
      <h1 style="margin:0 0 16px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
        500+ NFL predictions tracked. Here's what we found.
      </h1>
      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">${greeting}</p>
      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        Three days in — wanted to share a few things we've learned from analyzing pundit accuracy
        across the last three NFL seasons.
      </p>

      <!-- Stats row -->
      <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td width="33%" style="padding:0 8px 0 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;">
              <tr><td style="padding:16px;text-align:center;">
                <p style="margin:0 0 4px;font-size:28px;font-weight:700;color:#2563eb;">38%</p>
                <p style="margin:0;font-size:12px;color:#888888;">avg pundit accuracy</p>
              </td></tr>
            </table>
          </td>
          <td width="33%" style="padding:0 4px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;">
              <tr><td style="padding:16px;text-align:center;">
                <p style="margin:0 0 4px;font-size:28px;font-weight:700;color:#16a34a;">500+</p>
                <p style="margin:0;font-size:12px;color:#888888;">predictions scored</p>
              </td></tr>
            </table>
          </td>
          <td width="33%" style="padding:0 0 0 8px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;">
              <tr><td style="padding:16px;text-align:center;">
                <p style="margin:0 0 4px;font-size:28px;font-weight:700;color:#f59e0b;">3</p>
                <p style="margin:0;font-size:12px;color:#888888;">seasons of data</p>
              </td></tr>
            </table>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        The leaderboard separates signal from noise. Some pundits with massive followings score
        in the bottom quartile. A few under-the-radar analysts consistently beat the field.
      </p>
      <p style="margin:0 0 24px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        The Brier score doesn't care about confidence — it rewards calibration.
        The timeliness multiplier rewards commitment. Together they paint a clear picture.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:#2563eb;border-radius:6px;">
            <a href="${BASE_URL}/ledger" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">
              See the Leaderboard →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:#666666;line-height:1.6;">
        One more email coming in a few days — we'll show you how Pro tier unlocks
        full historical data and API access.
      </p>
    `
    return baseLayout(content, unsubUrl)
}

export function renderDay7Email({ email, firstName }: EmailProps): string {
    const greeting = firstName ? `Hey ${firstName},` : 'Hey,'
    const unsubUrl = unsubscribeUrl(email)
    const content = `
      <h1 style="margin:0 0 16px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
        Ready to go deeper? Introducing Cap Alpha Pro.
      </h1>
      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">${greeting}</p>
      <p style="margin:0 0 16px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        You've had a week with Cap Alpha. Here's what Pro unlocks:
      </p>

      <!-- Feature list -->
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;margin:0 0 24px;">
        <tr><td style="padding:24px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:8px 0;border-bottom:1px solid #222222;">
                <span style="font-size:16px;color:#16a34a;">✓</span>
                <span style="font-size:15px;color:#ffffff;margin-left:12px;">Full prediction history — every pundit, every season</span>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 0;border-bottom:1px solid #222222;">
                <span style="font-size:16px;color:#16a34a;">✓</span>
                <span style="font-size:15px;color:#ffffff;margin-left:12px;">REST API access — build your own dashboards</span>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 0;border-bottom:1px solid #222222;">
                <span style="font-size:16px;color:#16a34a;">✓</span>
                <span style="font-size:15px;color:#ffffff;margin-left:12px;">Dead money projections — see cap impact before the cut</span>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 0;">
                <span style="font-size:16px;color:#16a34a;">✓</span>
                <span style="font-size:15px;color:#ffffff;margin-left:12px;">Weekly digest — top predictions + accuracy updates</span>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>

      <p style="margin:0 0 24px;font-size:16px;color:#aaaaaa;line-height:1.6;">
        Pro is <strong style="color:#ffffff;">$9/month</strong>. Cancel anytime.
        If Cap Alpha saves you from acting on a single bad pundit take, it's already paid for itself.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 16px;">
        <tr>
          <td style="background:#2563eb;border-radius:6px;">
            <a href="${BASE_URL}/pricing" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">
              Upgrade to Pro →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:#666666;line-height:1.6;">
        Happy to stay on the free tier too — the core ledger is always free.
        This is the last onboarding email unless you upgrade.
      </p>
    `
    return baseLayout(content, unsubUrl)
}

// ---------------------------------------------------------------------------
// Resolution alert email — sent when a followed pundit's prediction resolves
// ---------------------------------------------------------------------------

function fmtResolutionDate(ts: string | null): string {
    if (!ts) return ''
    try {
        return new Date(ts).toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric'
        })
    } catch {
        return ''
    }
}

function outcomeBlock(pred: ResolvedPrediction): string {
    const isCorrect = pred.outcome === 'CORRECT'
    const badgeBg = isCorrect ? '#16a34a' : '#b91c1c'
    const badgeText = isCorrect ? '✓ CORRECT' : '✗ INCORRECT'
    const dateStr = fmtResolutionDate(pred.resolved_at)
    const hash = pred.prediction_hash.replace(/^sha256:/, '').slice(0, 8)
    const punditUrl = `${BASE_URL}/ledger/${encodeURIComponent(pred.pundit_id)}`

    return `
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;margin:0 0 12px;border-left:3px solid ${badgeBg};">
        <tr>
          <td style="padding:16px 20px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
              <span style="font-size:12px;color:#888888;">${pred.pundit_name}${dateStr ? ' · ' + dateStr : ''}</span>
              <span style="background:${badgeBg};border-radius:4px;padding:2px 8px;font-size:11px;color:#ffffff;font-weight:700;">${badgeText}</span>
            </div>
            <p style="margin:0 0 10px;font-size:14px;color:#ffffff;font-style:italic;line-height:1.5;">&ldquo;${pred.claim_text}&rdquo;</p>
            <div style="display:flex;gap:12px;align-items:center;">
              <a href="${punditUrl}" style="font-size:12px;color:#2563eb;text-decoration:none;font-weight:600;">View pundit ledger →</a>
              <span style="font-size:10px;color:#555555;font-family:monospace;">${hash}&hellip;</span>
            </div>
          </td>
        </tr>
      </table>`
}

export function renderResolutionAlertEmail({ email, firstName, resolutions }: ResolutionAlertEmailProps): string {
    const greeting = firstName ? `Hi ${firstName},` : 'Hi,'
    const unsubUrl = unsubscribeUrl(email)
    const count = resolutions.length
    const subjectHint = count === 1
        ? `"${resolutions[0].claim_text.slice(0, 60)}${resolutions[0].claim_text.length > 60 ? '…' : ''}"`
        : `${count} predictions`

    const outcomeBlocks = resolutions.map(outcomeBlock).join('')

    const content = `
      <h1 style="margin:0 0 16px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
        ${count === 1 ? 'A' : count} followed prediction${count === 1 ? '' : 's'} resolved overnight
      </h1>
      <p style="margin:0 0 20px;font-size:15px;color:#aaaaaa;line-height:1.6;">${greeting} Here${count === 1 ? "'s what" : "'s what"} happened with ${subjectHint}:</p>

      ${outcomeBlocks}

      <p style="margin:16px 0 0;font-size:13px;color:#666666;line-height:1.6;">
        You receive this because you follow ${count === 1 ? 'this pundit' : 'these pundits'} on Cap Alpha.
        <a href="${BASE_URL}/my/pundits" style="color:#888888;text-decoration:underline;">Manage followed pundits</a>
      </p>
    `
    return baseLayout(content, unsubUrl)
}

// ---------------------------------------------------------------------------
// Weekly digest email — sent every Tuesday at 13:00 UTC
// ---------------------------------------------------------------------------

function digestPunditSection(entry: DigestPunditEntry): string {
    const accuracyPct = entry.accuracy_rate !== null
        ? `${Math.round(entry.accuracy_rate * 100)}%`
        : '—'
    const accColor = entry.accuracy_rate !== null
        ? entry.accuracy_rate >= 0.65 ? '#16a34a' : entry.accuracy_rate >= 0.5 ? '#d4a017' : '#b91c1c'
        : '#888888'
    const punditUrl = `${BASE_URL}/ledger/${encodeURIComponent(entry.pundit_id)}`
    const resolutionRows = entry.resolved_this_week.slice(0, 3).map((r) => {
        const isCorrect = r.outcome === 'CORRECT'
        const icon = isCorrect ? '✓' : '✗'
        const iconColor = isCorrect ? '#16a34a' : '#b91c1c'
        const claimShort = r.claim_text.length > 80 ? r.claim_text.slice(0, 77) + '…' : r.claim_text
        return `
          <tr>
            <td style="padding:6px 0;border-bottom:1px solid #222222;">
              <span style="color:${iconColor};font-weight:700;margin-right:8px;">${icon}</span>
              <span style="font-size:13px;color:#cccccc;font-style:italic;">&ldquo;${claimShort}&rdquo;</span>
            </td>
          </tr>`
    }).join('')

    return `
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;margin:0 0 16px;">
        <tr>
          <td style="padding:16px 20px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <a href="${punditUrl}" style="font-size:16px;font-weight:700;color:#ffffff;text-decoration:none;">${entry.pundit_name}</a>
                  ${entry.pending_count > 0 ? `<span style="font-size:12px;color:#888888;margin-left:8px;">${entry.pending_count} pending</span>` : ''}
                </td>
                <td style="text-align:right;">
                  <span style="font-size:20px;font-weight:700;color:${accColor};font-family:monospace;">${accuracyPct}</span>
                  <span style="font-size:11px;color:#888888;margin-left:4px;">accuracy</span>
                </td>
              </tr>
            </table>
            ${resolutionRows ? `
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;">
              ${resolutionRows}
            </table>` : ''}
            ${entry.resolved_this_week.length === 0 ? '<p style="margin:10px 0 0;font-size:12px;color:#666666;">No resolutions this week — predictions pending.</p>' : ''}
          </td>
        </tr>
      </table>`
}

export function renderWeeklyDigestEmail({ email, firstName, pundits, weekOf }: WeeklyDigestEmailProps): string {
    const greeting = firstName ? `Hi ${firstName},` : 'Hi,'
    const unsubUrl = unsubscribeUrl(email)

    const punditSections = pundits.map(digestPunditSection).join('')

    const totalResolutions = pundits.reduce((sum, p) => sum + p.resolved_this_week.length, 0)
    const totalPending = pundits.reduce((sum, p) => sum + p.pending_count, 0)

    const content = `
      <h1 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
        Your weekly pundit update
      </h1>
      <p style="margin:0 0 4px;font-size:13px;color:#888888;">Week of ${weekOf}</p>
      <p style="margin:0 0 24px;font-size:15px;color:#aaaaaa;line-height:1.6;">${greeting}</p>

      <!-- Summary stats -->
      <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td width="50%" style="padding:0 8px 0 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;">
              <tr><td style="padding:14px;text-align:center;">
                <p style="margin:0 0 4px;font-size:26px;font-weight:700;color:#2563eb;">${totalResolutions}</p>
                <p style="margin:0;font-size:12px;color:#888888;">predictions resolved</p>
              </td></tr>
            </table>
          </td>
          <td width="50%" style="padding:0 0 0 8px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;">
              <tr><td style="padding:14px;text-align:center;">
                <p style="margin:0 0 4px;font-size:26px;font-weight:700;color:#d4a017;">${totalPending}</p>
                <p style="margin:0;font-size:12px;color:#888888;">pending this week</p>
              </td></tr>
            </table>
          </td>
        </tr>
      </table>

      <!-- Pundit sections -->
      <div style="margin-bottom:8px;font-size:11px;font-weight:700;color:#888888;text-transform:uppercase;letter-spacing:1.5px;">Your followed pundits</div>
      ${punditSections}

      <table cellpadding="0" cellspacing="0" style="margin:8px 0 16px;">
        <tr>
          <td style="background:#2563eb;border-radius:6px;">
            <a href="${BASE_URL}/my/pundits" style="display:inline-block;padding:12px 24px;font-size:14px;font-weight:600;color:#ffffff;text-decoration:none;">
              Manage My Pundits →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:12px;color:#666666;line-height:1.6;">
        You receive this weekly digest because you follow pundits on Cap Alpha.
        <a href="${unsubUrl}&type=digest" style="color:#888888;text-decoration:underline;">Unsubscribe from digest</a>
      </p>
    `
    return baseLayout(content, unsubUrl)
}
