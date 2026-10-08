---
name: anti-slop-design
description: >-
  Design system and cognitive framework for coding agents to engineer distinctive,
  bespoke frontend web interfaces. Eliminates generic 'AI slop' aesthetics (such as
  predictable purple gradients, ubiquitous 3-card grids, Inter font defaults, and
  template monoculture) by enforcing domain grounding, opinionated design archetypes,
  token-driven constraints, and rigorous interaction craft.
---

# Anti-Slop Design System: Architecture for Coding Agents

## Purpose
When AI coding agents are asked to design web interfaces, they default to the statistical mean of their training data: dark modes with purple/cyan radial glow, generic Inter fonts, 3-card grids, and formulaic marketing copy. This document serves as an immutable negative constraint and construction framework to force coding agents into producing human-crafted, distinctive, and domain-grounded frontend interfaces.

---

## 1. Negative Constraints: The Anti-Slop Blacklist

Any interface matching 3 or more of these tells fails verification and must be refactored:

### 1.1 Aesthetic Traps & Monocultures
* **The "v0 / Vibe-SaaS" Monoculture**: Pitch-black or deep navy background (`#090d16`), radial purple-to-cyan ambient glow (`radial-gradient`), glossy glass cards with `backdrop-blur` and `border-white/10`, and pill buttons with rainbow iridescent borders.
* **The "Anthropic Warm Cream"**: Warm paper cream background (`#F4F1EA`), historic serif headings, terracotta/burnt orange accent (`#D97757`), 1px hairline borders, zero border-radius.
* **The "Neon Cyber Hacker"**: Pitch black (`#000000`), neon terminal green (`#00FF66`) or high-visibility orange, monospace everywhere, terminal decoration badges.
* **The "Linear / Vercel Copycat"**: Monochromatic dark gray, 1px border (`#27272a`), pulsing green status dots on pills, Inter everywhere, cards with mouse flashlight illumination regardless of whether it fits the product domain.

### 1.2 Typographic & Copywriting Tells
* **Blind Font Defaults**: Defaulting to `Inter`, `Roboto`, or generic `system-ui` without evaluating the brand domain.
* **Single Accented Word Cliché**: Long headline with exactly one word wrapped in an italic gradient span (e.g., `Craft the <span class="gradient">future</span> of logistics`).
* **Formulaic Copywriting**:
  - *"Supercharge your workflow"*
  - *"The modern all-in-one platform for [X]"*
  - *"Elevate your experience"*
  - *"Seamless, intuitive, powerful"*
* **All-Caps Micro-Eyebrows**: Spraying `text-xs uppercase tracking-widest text-muted` above every single heading.
* **Fake Sequential Numbering**: Slapping `01 / 02 / 03` labels on cards when the content is not a strict chronological or procedural step.

### 1.3 Spatial & Structural Monotony
* **The Ubiquitous 3-Card Grid**: Dividing every section into 3 equal-width columns (`col-md-4` or `grid-cols-3`), each with an icon in a circle, a 2-line title, and a 3-line description.
* **The Metric Triptych**: 3 huge standalone numbers centered across the page (`99.9% Uptime`, `10M+ Users`, `4.9★ Rating`).
* **Strict Center-Alignment Syndrome**: Centering every badge, headline, paragraph, and dual button container across the entire page.
* **Floating Angled Mockups**: Isometric 15-degree tilted dashboard screenshots with blurred drop shadows.

### 1.4 Interaction Blindness
* **Missing Keyboard Focus**: Using `outline: none` without providing an explicit `:focus-visible` ring.
* **Missing Physical Press**: Buttons lacking `:active` depression (`transform: translateY(1px)`).
* **Floaty Card Hover**: Every card doing `transform: translateY(-4px)` with a heavy drop shadow.

---

## 2. The 5-Step Agent Construction Workflow

```
[User Request]
       │
       ▼
[Step 0: Domain Grounding] ────────► Identify physical materials and operator context
       │
       ▼
[Step 1: Commit to 1 Archetype] ───► Choose exactly 1 visual archetype (no mixing)
       │
       ▼
[Step 2: Token Contract] ──────────► Define CSS custom properties for surfaces & hierarchy
       │
       ▼
[Step 3: Asymmetric Layout] ───────► Break monotonous 3-column grids; establish visual rhythm
       │
       ▼
[Step 4: Physical Interaction] ────► Add active depress, focus rings, loading & empty states
       │
       ▼
[Step 5: Pre-Flight Audit] ────────► Scan and eliminate all AI tells before code delivery
```

### Step 0: Domain Grounding
Before writing markup or CSS, answer two questions:
1. **What is the physical worldview of this domain?**
   - *Hardware/Engineering*: Barcodes, container labels, high contrast, technical specs, weight ratings, calibrated gauges.
   - *Artisanal/Tea/Perfumery*: Mulberry paper, terracotta, natural grain, generous negative space, quiet typography.
2. **Under what operational constraints does the user interact?**
   - Field manager on a tablet in daylight (needs high contrast and large touch targets).
   - Back-office clerk comparing 100 rows per hour (needs dense tables and monospace numerals).

### Step 1: Commit to Exactly One Opinionated Visual Archetype
Pick one archetype and enforce it consistently throughout the entire interface:

1. **Swiss / Technical Utilitarian**:
   - Palette: Slate dark (`#0b0f19`, `#1e293b`) or crisp neutral paper, with exactly 1 functional accent (International Klein Blue `#002fa7` or Signal Amber `#f59e0b`).
   - Typography: Monospace for data/numbers (`JetBrains Mono`, `SF Mono`), crisp geometric sans for headings (`Prompt`, `Plus Jakarta Sans`).
   - Geometry: Crisp 2px-6px radii, visible 1px structural gridlines, zero decorative glow.
2. **Warm Crafted Editorial**:
   - Palette: Cotton paper/linen (`#f9f8f6`, `#f2ede4`), rich ink (`#1c1917`), olive green (`#444a38`) or terracotta accent.
   - Typography: Elegant high-contrast serif for headings (`Playfair Display`, `Newsreader`), humanist sans for body.
   - Layout: Asymmetric column splits (e.g., 8:4), generous margins, editorial type treatments.
3. **Architectural Monochrome**:
   - Palette: 95% black, white, and neutral gray. Depth created through opacity layering (`rgba(255,255,255,0.06)`), **strictly zero rainbow gradients**.
   - Typography: Clean neo-grotesque sans, tightened heading tracking (`letter-spacing: -0.02em`).
   - Layout: Structural negative space and strict typographic scale over decorative boxes.
4. **Tactile Industrial (Neo-Craft)**:
   - Palette: Concrete gray, industrial signal accents (Safety Orange `#ff5500`, Caution Yellow `#ffd000`).
   - Details: 1.5–2px solid borders, subtle bevel/inset buttons, dot-matrix badges, mechanical toggle affordances.

---

## 3. Machine-Readable Token Contract (CSS Variables)

Always establish explicit tokens before writing component styles:

```css
:root {
  /* Surface Depths */
  --surface-canvas:  #0b0f19;
  --surface-raised:  #141b2d;
  --surface-overlay: #1c263d;
  --surface-sunken:  #070a12;

  /* Typographic Hierarchy */
  --text-primary:   #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted:     #64748b;

  /* Single Semantic Accent (Never use multiple clashing neons) */
  --accent-primary: #0071e3;
  --accent-hover:   #0077ed;
  --accent-focus:   rgba(0, 113, 227, 0.4);

  /* Geometry & Physics */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 14px;
  --ease-spring: cubic-bezier(0.16, 1, 0.3, 1);
}
```

---

## 4. Pre-Flight Anti-Slop Audit Checklist

Execute this verification scan prior to delivering any frontend code:
- [ ] **No purple-cyan radial glows**: Removed all `radial-gradient` purple ambient backdrops.
- [ ] **No formulaic copy**: Replaced empty slogans with concrete domain specifications.
- [ ] **No fake numbers**: Removed decorative `01/02/03` badges on non-procedural items.
- [ ] **No 3-card monotony**: Replaced identical 3-column card layouts with asymmetric rhythm.
- [ ] **State completeness verified**: Every interactive element includes `:hover`, `:active`, and `:focus-visible`.
