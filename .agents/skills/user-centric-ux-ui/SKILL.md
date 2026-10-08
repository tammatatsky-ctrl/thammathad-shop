---
name: user-centric-ux-ui
description: >-
  Comprehensive UX/UI design framework and empirical principles for coding agents to design
  human-centric, high-utility, and ergonomic web applications. Synthesizes fundamental cognitive
  psychology laws (Fitts, Hick, Miller, Tesler, Postel, Doherty), real-world operational workflows
  (action availability, context preservation, single-page scanning, high data density), form usability,
  and accessible interaction craft.
---

# User-Centric UX/UI Framework: Principles for Human-Centered Engineering

## Purpose
This skill establishes empirical, research-backed UX/UI design principles for coding agents building real-world software, administrative consoles, and web applications. It counters "aesthetic over-simplification"—the practice of hiding critical buttons, fragmenting single workflows into multi-step wizards, and adding excessive padding that starves users of information density.

---

## 1. The 4 Empirical Enterprise UX Pillars

### Pillar 1: Action Availability over Menu Burial ("Many Buttons on One Screen")
* **The Flaw**: Hiding frequent actions inside kebab menus (`...`) or nested dropdowns to achieve a clean screenshot, forcing daily operators to click 3-4 times per repetitive task.
* **UX Foundations**:
  - **Recognition over Recall (Nielsen Heuristic #6)**: Seeing an action affordance immediately triggers recognition; hunting inside hidden menus demands memory retrieval.
  - **Fitts's Law**: Direct toolbar access minimizes target acquisition time.
* **Engineering Standards**:
  1. **Visual Weight Distribution**:
     - *Primary Action* (max 1 per zone): Solid accent color (e.g., `[Save]`).
     - *Secondary/Utility Actions*: Neutral outline or light button (e.g., `[Edit]`, `[Clone]`, `[Print]`, `[Refresh]`).
     - *Destructive Actions*: Isolated to the far right or styled with danger states on hover (e.g., `[Delete]`).
  2. **Button Grouping / Toolbars**: Unify related actions into a single segmented toolbar rather than scattering individual buttons.

---

### Pillar 2: Context Preservation ("Never Abandon In-Progress Work")
* **The Flaw**: Forcing full-page redirects when a user needs secondary data (e.g., checking stock or customer history while creating an invoice), destroying uncommitted form states and causing mental resets.
* **UX Foundations**:
  - **Miller's Law & Working Memory**: Humans hold limited items in working memory. Page switches induce context loss and anxiety over lost input.
  - **Non-Destructive Workflows**: The user's primary workspace must remain visible and uncorrupted.
* **Engineering Standards**:
  1. **Side Sheets / Slide-Over Drawers (Preferred over Nested Modals)**:
     - Open secondary inspection or sub-forms in a side panel (400px–600px). The primary form remains visible behind it.
  2. **Draft Persistence**: Auto-save form progress into `sessionStorage` to guard against accidental dismissals.
  3. **Guarded Backdrop Clicks**: Never close a modal or drawer on backdrop click if the form contains dirty/unsaved inputs.

---

### Pillar 3: Single-Page Scannable Flows ("Scrolling Beats Paging")
* **The Flaw**: Splitting a short 15-field form into a 4-step wizard, requiring repeated Next/Back clicks and preventing easy review.
* **UX Foundations**:
  - **"Scrolling Beats Paging" (Jakob Nielsen, NN/g)**: The physical interaction cost of scrolling is near zero compared to clicking, waiting for page loads, and re-orienting.
  - **Mental Workload Assessment**: Seeing the entire form allows users to accurately gauge the required effort upfront.
* **Engineering Standards**:
  1. **Visual Chunking**: Group related fields into distinct visual cards or sections (e.g., `[Recipient Info]` ➔ `[Delivery Address]` ➔ `[Payment Method]`).
  2. **Sticky Actions**: On long forms, anchor the primary CTA or summary bar to the viewport bottom or sidebar so users can submit from anywhere.

---

### Pillar 4: High-Density Data Tables ("Information Ready for Decision")
* **The Flaw**: Over-padded table rows showing only 4 records per screen, stripping crucial columns and forcing endless pagination.
* **UX Foundations**:
  - **Tesler's Law (Conservation of Complexity)**: Operational data is intrinsically complex. Suppressing columns forces users into extra drill-downs.
  - **Row-by-Row Comparative Analysis**: Human decision-making relies on rapid vertical scanning across parallel records.
* **Engineering Standards**:
  1. **Compact Row Height**: Maintain 36px to 48px row heights to surface 15–25 records per viewport.
  2. **Sticky Table Header**: Keep `<thead>` fixed during vertical scroll.
  3. **Monospaced Tabular Figures**: Use monospaced fonts (`JetBrains Mono`, `SF Mono`, or `font-variant-numeric: tabular-nums`) right-aligned for all monetary, numeric, and code fields (`#ORD-1002`, `EMP-001`, `฿ 12,450.00`).
  4. **Zebra Striping & Hover States**: Subtle alternating row background or high-visibility hover highlight to guide the eye across wide tables.
  5. **Inline Row Actions**: Expose common per-row actions (e.g., `[Verify Slip]`, `[Print]`) directly in the row.

---

## 2. Core Cognitive Laws of UX in Code

| Law | Engineering Definition | Implementation Rule |
|---|---|---|
| **Jakob's Law** | Users expect your site to work like all other sites they know. | Do not invent non-standard navigation. Logo top-left, search prominent, cart top-right. |
| **Fitts's Law** | Target acquisition time is a function of distance and size. | Minimum clickable target is 44×44px. Critical actions belong near primary focal areas. |
| **Hick's Law** | Decision time increases with number and complexity of choices. | Limit top-level navigation choices. Provide recommended defaults on complex options. |
| **Postel's Law** | Be liberal in what you accept, conservative in what you send. | Accept phone numbers with dashes, spaces, or international prefixes; normalize backend. |
| **Doherty Threshold** | Productivity soars when computer and user interact at <400ms. | Show skeleton screens or optimistic UI immediately upon click; never leave an unresponsive screen. |
| **Tesler's Law** | System complexity cannot be eliminated, only shifted. | Automate cascade dependencies (e.g., auto-filling district and zip code upon province selection). |
| **Von Restorff Effect** | Distinct items among homogeneous items are remembered best. | Apply primary accent styling to exactly 1 high-priority button or recommended pricing tier. |

---

## 3. Form Engineering & Forgiving Input

1. **Top-Aligned Labels**: Always position labels directly above inputs. Eye-tracking research confirms this yields the fastest visual fixation and completion speed.
2. **Never Use Placeholder as Label**: Placeholders vanish upon keystroke, destroying context and error recovery.
3. **Inline Validation: "Reward Early, Punish Late"**:
   - *Punish Late*: Do not flag an input as invalid while the user is actively typing. Validate on `blur` or after a 500ms debounce.
   - *Reward Early*: As soon as a user corrects a previously errored field, immediately display success styling (e.g., green checkmark).
4. **Actionable Error Messages**: State specifically how to resolve the error (e.g., `"Enter a 10-digit Thai phone number starting with 0, e.g. 081-234-5678"` instead of `"Invalid format"`).

---

## 4. State Completeness Contract

Every interactive component must implement all 7 states:
1. **Default**: Clear contrast exceeding WCAG AA (4.5:1 for body text, 3:1 for UI controls).
2. **Hover**: Subtle luminance shift and `cursor: pointer`.
3. **Active/Press**: Physical depression (`transform: translateY(1px) scale(0.99)`).
4. **Focus-Visible**: Distinct 2px outline ring separated by a 2px offset (never `outline: none`).
5. **Loading**: Progress spinner or shimmer skeleton with click handlers disabled.
6. **Disabled**: Reduced opacity (0.45) with `cursor: not-allowed`.
7. **Empty**: Contextual illustration/icon, clear explanation, and a recovery CTA button.

---

## 5. Agent Pre-Flight UX Audit Checklist

Prior to delivering frontend code, verify:
- [ ] **Frequent actions visible**: Key operational buttons are in immediate view, not hidden in sub-menus.
- [ ] **Context preserved**: Secondary inspections use side sheets, drawers, or inline expansions rather than destructive page redirects.
- [ ] **Form usability verified**: Single-column vertical flow, top-aligned labels, no placeholder-only inputs, forgiving formatting.
- [ ] **Table density optimized**: Sticky header, right-aligned tabular figures with monospace fonts, row hover affordance.
- [ ] **Physical interactions bound**: Active press depression and `:focus-visible` rings present on all interactive controls.
- [ ] **Zero unhandled states**: Loading skeletons, empty states, and actionable error messages exist for all dynamic containers.
