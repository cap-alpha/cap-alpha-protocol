/**
 * Alias route for /ledger/in-play — deep-link URL for social sharing.
 *
 * Renders the same LedgerPage as /ledger but forces the "in-play" top-level view
 * so users who arrive from a shared link land directly on the In Play tab.
 *
 * SEO: no separate canonical — the parent /ledger page is the canonical URL
 * for the In Play surface. This route is for deep-linking only.
 *
 * Issue: #770
 */

import { redirect } from "next/navigation";

export default function InPlayAlias() {
    // Redirect to ledger page with in-play view param.
    // The LedgerPage reads `view` from searchParams to initialize topView.
    redirect("/ledger?view=in-play");
}
