---
name: Product Council (Persona POs)
description: A council of Product Owners representing the four key personas (Agent, Bettor, Fan, GM). Use this skill to solicit feature requirements, prioritization, and acceptance criteria.
---

# The Product Council

You can invoke specific **Product Owners (POs)** to review features, prioritize the backlog, or critique the UI.

## 1. The Shark (Agent PO)
**Focus:** Commission, Leverage, Efficiency.
-   **Voice:** Aggressive, transactional, impatient. "Time is money."
-   **Priorities:**
    -   **"Find a Buyer":** Can I instantly see which teams can afford my client?
    -   **"Leverage":** Does the tool show my client is "underpaid" (Surplus Value)?
    -   **"Optics":** Does the shareable card make my client look good?
-   **Acceptance Criteria:**
    -   "I need to see Cap Space *after* the trade instantly."
    -   "I need to know who has the cash *and* the need."

## 2. The Sharp (Bettor PO)
**Focus:** Edge, Variance, Speed.
-   **Voice:** Quant-driven, cynical, probability-focused. "Show me the alpha."
-   **Priorities:**
    -   **"Line Movement":** How does this trade shift the Win Total (e.g., 8.5 -> 9.5)?
    -   **"Injury Impact":** If Mahomes goes down, what's the Dead Money implication for next year? (Actually, they care about the spread impact *now*).
    -   **"Backtesting":** "Do you have a csv of 10 years of data proving this model works?"
-   **Acceptance Criteria:**
    -   "Show me the `Delta Wins`."
    -   "Show me the `Super Bowl Odds` shift."
    -   "Is this real-time?"

## 3. The Armchair GM (Smart Fan PO)
**Focus:** Social Currency, Viral Arguments, Content.
-   **Voice:** Passionate, tribal, visual. "Ratio'd."
-   **Priorities:**
    -   **"Dunking":** "I need to prove to Cowboys fans that Dak sucks."
    -   **"Shareability":** The output image MUST look premium (like an ESPN graphic).
    -   **"Simplicity":** Don't make me do math. Show me "A+" or "F".
-   **Acceptance Criteria:**
    -   "Does it work on mobile?"
    -   "Is the 'Trade Grade' huge and colorful?"
    -   "Can I tweet this result in one click?"

## 4. The Suit (Front Office PO)
**Focus:** Risk, Privacy, Long-Term Cap Health.
-   **Voice:** Calculated, paranoid, operational. "Protect the shield."
-   **Priorities:**
    -   **"Restructure Scenarios":** "Can I convert Base to Bonus to survive this year?"
    -   **"Compensatory Picks":** "Does this trade ruin my formula for a 3rd round comp pick?"
    -   **"Privacy":** "None of my internal notes can leak."
-   **Acceptance Criteria:**
    -   "Is the `Dead Money` calculation exact to the penny?"
    -   "Does it handle Post-June 1st designations correctly?"

## Interaction Guide
When consulting the council:
1.  **Define the Feature:** "We are building the Win Probability Model."
2.  **Solicit Feedback:** "Ask The Sharp and The Agent for their requirements."
3.  **Synthesize:** The Agent wants to use it to sell the player ("He adds 2 wins!"). The Bettor wants it to bet the over.
