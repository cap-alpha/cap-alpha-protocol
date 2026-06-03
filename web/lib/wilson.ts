/**
 * Wilson score lower bound — leaderboard sort key (Issue #1032).
 *
 * Pundit with 1/1 (100%, n=1) should rank far below 9/10 (90%, n=10).
 * Raw accuracy_rate alone cannot distinguish these; Wilson LB at 95% CI can.
 *
 * Formula:
 *   p  = correct / n
 *   z  = 1.96  (95% confidence)
 *   lb = ((p + z²/2n) - z·sqrt((p(1-p) + z²/4n) / n)) / (1 + z²/n)
 *
 * Wilson LB is the sort key only — accuracy_rate is the user-facing column.
 */

const Z95 = 1.96;

/**
 * Returns the Wilson score lower bound at 95% confidence.
 *
 * @param correct - Number of correct outcomes.
 * @param n       - Total graded predictions (VOID excluded).
 * @returns Wilson LB in [0, 1].  Returns 0 when n === 0.
 */
export function wilsonLowerBound(correct: number, n: number): number {
    if (n === 0) return 0;
    const p = correct / n;
    const z2 = Z95 * Z95;
    const centre = p + z2 / (2 * n);
    const margin = Z95 * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n);
    const denominator = 1 + z2 / n;
    return (centre - margin) / denominator;
}
