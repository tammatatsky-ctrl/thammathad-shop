---
name: color-system-design
description: >-
  Comprehensive color theory, perceptual color spaces (OKLCH, Display P3),
  semantic token architecture, contrast accessibility (WCAG 2.2 / APCA),
  dark mode optical physics, and data visualization palette design.
  Eliminates ungrounded AI color tropes and ensures rigorous visual hierarchy.
---

# Color System Design: Architecture & Principles for Coding Agents

## Purpose
Color in digital interfaces is functional infrastructure, not cosmetic decoration. When AI coding agents select colors without rigorous principles, they default to arbitrary hex values, ungrounded purple-to-cyan ambient gradients, unreadable low-contrast grays, or muddy, eye-straining dark modes. This skill provides an empirical, perceptual color framework governing color selection, token architecture, contrast accessibility, dark mode physics, and data visualization.

---

## 1. Perceptual Color Science & Modern Color Spaces

### 1.1 Why sRGB and HSL Fail in Modern UI
* **Non-Uniform Perceptual Lightness**: In HSL, pure Yellow (`hsl(60, 100%, 50%)`) and pure Blue (`hsl(240, 100%, 50%)`) both share `50%` Lightness, yet the human eye perceives yellow as radically brighter than blue. Generating accessible shade steps using HSL math creates broken contrast ratios.
* **Hue Shifts During Desaturation**: Adjusting saturation or lightness in RGB/HSL shifts the perceived tint (e.g., desaturating orange turns into muddy brown).
* **Narrow Gamut**: Standard sRGB misses up to 30% of the vibrant, punchy colors reproducible on modern OLED and wide-gamut (Display P3) screens.

### 1.2 The Modern Standard: OKLCH
Modern design systems use **OKLCH** (`oklch(L C H [/ A])`):
* **L (Perceived Lightness, 0% to 100% or 0 to 1)**: Directly matches human visual perception. An `L` of 0.65 has the exact same perceived brightness regardless of whether the hue is blue, amber, or green.
* **C (Chroma, 0 to ~0.37+)**: Represents color purity/saturation. Neutral grays have `C: 0.00` to `0.02`; vibrant accents have `C: 0.15` to `0.25`.
* **H (Hue, 0 to 360 deg)**: The color wheel angle (0 = Pink/Red, 90 = Yellow, 145 = Green, 250 = Blue, 300 = Purple).
* **Wide Gamut Native**: Automatically accesses Display P3 colors without clipping, with graceful fallback to sRGB.

---

## 2. The 3-Tier Token Architecture

Never hardcode arbitrary hex values inside component templates or CSS rules. Enforce a strict 3-tier token hierarchy:

```
[ Tier 1: Primitive Tokens ]   (Raw Palette Ramps: blue-50, blue-500, gray-900)
             │
             ▼
[ Tier 2: Semantic Tokens ]    (Functional Intent: surface-base, text-primary, action-hover)
             │                 * Swapped seamlessly between Light and Dark themes *
             ▼
[ Tier 3: Component Tokens ]   (Scoped Contracts: btn-primary-bg, table-header-bg)
```

### 2.1 Tier 1: Primitive / Global Tokens
Raw mathematical color scales spanning 10 or 11 tonal steps (50, 100, 200, ... 900, 950):
* **Neutral / Grays**: Slight cool or warm undertone (`C: 0.01` to `0.02`). Pure desaturated gray (`C: 0`) looks lifeless; inject a tiny hint of the brand hue.
* **Accent Hues**: 1 primary brand hue, 1-2 secondary supporting hues.
* **Semantic Families**: Success (Emerald/Green), Warning (Amber), Danger (Crimson/Red), Info (Cyan/Sky).

### 2.2 Tier 2: Semantic / Intent Tokens
Tokens representing UI roles. **Components only consume Tier 2 or Tier 3 tokens**:
* **Surfaces**: `--surface-canvas`, `--surface-card`, `--surface-raised`, `--surface-overlay`.
* **Content/Text**: `--text-primary`, `--text-secondary`, `--text-muted`, `--text-inverse`.
* **Borders/Dividers**: `--border-subtle`, `--border-default`, `--border-strong`.
* **Interactive Actions**: `--action-primary`, `--action-primary-hover`, `--action-primary-active`.
* **Status Feedback**: `--feedback-success-surface`, `--feedback-success-text`, `--feedback-danger-surface`, etc.

### 2.3 Tier 3: Component-Scoped Tokens
Used when a component requires strict encapsulation or overrides:
* `--btn-primary-bg: var(--action-primary);`
* `--btn-primary-text: var(--text-inverse);`

---

## 3. Spatial Color Distribution: The 60-30-10 Rule

An interface must not be an equal contest between multiple colors. Enforce visual equilibrium using the **60-30-10 Rule**:

| Ratio | UI Role | Elements | Purpose |
|---|---|---|---|
| **60%** | **Dominant (Canvas / Surface)** | Backgrounds, whitespace, large page areas | Provides optical rest, reduces visual fatigue, sets atmospheric tone |
| **30%** | **Structural (Secondary / Surfaces)** | Sidebars, navigation bars, cards, borders, secondary buttons | Creates layout rhythm, groups content logically, guides scanning |
| **10%** | **Accent / Focal (Primary Action)** | Primary CTA buttons, active state pills, progress bars, notification pings | Directs immediate human attention (Fitts's / Hick's Law) |

> **Rule of Thumb**: If more than 10-15% of the total viewport pixels are filled with high-chroma accent color, the interface is visually noisy and lacks clear hierarchy.

---

## 4. Contrast, Readability & Accessibility (A11y)

### 4.1 WCAG 2.2 Baseline Specifications
* **Normal Text (< 18pt or < 14pt bold)**: Minimum **4.5:1** contrast ratio against its background (Level AA). Target **7:1** for primary reading copy (Level AAA).
* **Large Text (>= 18pt or >= 14pt bold)**: Minimum **3.0:1** contrast ratio (Level AA).
* **UI Components & Graphical Objects**: Minimum **3.0:1** contrast ratio for essential icons, form input borders, checkboxes, and focus indicators against adjacent surfaces.

### 4.2 APCA (Accessible Perceptual Contrast Algorithm) Nuances
APCA (candidate for WCAG 3) accounts for human spatial frequency:
* **Polarity Sensitivity**: Light text on dark backgrounds requires higher calculated luminance contrast than dark text on light backgrounds due to optical irradiation.
* **Font Weight Weighting**: Thin fonts (`font-weight: 300`) require substantially higher contrast than bold fonts (`font-weight: 700`) to achieve equivalent legibility.

### 4.3 The Dual-Encoding Mandate
**Never convey critical state, validation, or meaning using color alone.**
Always combine color with a secondary visual channel:
1. **Color + Text Label**: Instead of a red border alone, show red border + error message text below.
2. **Color + Icon**: Success badge must include a checkmark icon (`bi-check-circle`), not just green background.
3. **Color + Shape/Style**: Underline active links or render distinct dashed/solid lines in charts.

### 4.4 Color Vision Deficiency (CVD) Defenses
Approximately 8% of men and 0.5% of women experience Color Vision Deficiency:
* **Red-Green Blindness (Deuteranopia & Protanopia)**: The most prevalent. Never pair red and green as the sole distinguishing factors (e.g., green "Approve" and red "Reject" buttons must have distinct positions, icons, or text).
* **Blue-Yellow Blindness (Tritanopia)**: Avoid relying on blue vs. green distinctions.
* **Monochromacy**: Ensure all key interfaces remain 100% understandable when converted to pure grayscale.

---

## 5. Light & Dark Mode Optical Physics

Dark mode is **not** a direct negative inversion of light mode (`#ffffff` <-> `#000000`). Direct inversion produces harsh, vibrating, and muddy interfaces.

### 5.1 Avoid Pure Pitch Black (`#000000`)
* On OLED screens, `#000000` causes pixel turn-off smearing during scrolling.
* Pure black creates an unnatural, harsh contrast step against pure white text.
* **Prescription**: Base dark canvas on deeply tinted dark tones (`oklch(0.14 0.015 250)` or `#0b0f19` / `#121620`), matching the brand's hue family.

### 5.2 The 87% Anti-Halation Rule
* **Halation**: Rendering pure white text (`#ffffff`, 100% luminance) on dark backgrounds causes the light to scatter inside the human eye, creating an uncomfortable blur/glow around letters.
* **Prescription**: Cap primary text in dark mode at **87% to 90% opacity/luminance** (e.g., `#e2e8f0` or `rgba(255, 255, 255, 0.88)`). Secondary text should be 60-65% (`#94a3b8`), and muted text 40-45% (`#64748b`).

### 5.3 Elevation Modeling: Lightness vs. Shadow
* **In Light Mode**: Elevation is communicated primarily through **drop shadows** (`box-shadow: 0 8px 24px rgba(0,0,0,0.08)`).
* **In Dark Mode**: Drop shadows are optically invisible. Elevation is communicated by **increasing surface lightness** and subtle 1px top highlight borders (`rgba(255,255,255,0.08)`):
  - Canvas (Base Level 0): `oklch(0.13 0.01 250)`
  - Card (Elevation 1): `oklch(0.17 0.012 250)`
  - Raised Modal / Drawer (Elevation 2): `oklch(0.22 0.015 250)`

### 5.4 Chroma Dampening
* Saturated colors that look balanced on white surfaces will **vibrate aggressively** against dark backgrounds.
* **Prescription**: Dampen Chroma (`C`) by 15% to 25% when mapping brand accents and status colors to dark mode surfaces, while raising Lightness slightly to preserve readability.

---

## 6. Interactive State Systems & Token Transitions

Every interactive element must provide unmistakable, progressive feedback across all states:

```
[ Rest / Default ]
       │
       ▼ (Hover: Lightness adjustment ±6%, cursor pointer)
[ Hover ]
       │
       ▼ (Active/Press: Scale 0.98-0.99, Lightness adjustment -4%)
[ Pressed / Active ]
       │
       ▼ (Focus: 2px sharp outline ring with 2px offset)
[ Focus-Visible ]
       │
       ▼ (Disabled: 38% opacity or desaturated neutral, cursor not-allowed)
[ Disabled ]
```

### State Token Contract Pattern:
```css
/* Interactive Button Example */
.btn-action {
  background-color: var(--action-primary);       /* OKLCH base */
  color: var(--text-inverse);
  transition: background-color 0.2s var(--ease-apple), transform 0.15s ease;
}

.btn-action:hover {
  background-color: var(--action-primary-hover); /* Lightness ± 5% */
  transform: translateY(-1px);
}

.btn-action:active {
  background-color: var(--action-primary-active);/* Lightness - 4% */
  transform: translateY(1px) scale(0.99);        /* Physical press */
}

.btn-action:focus-visible {
  outline: 2px solid var(--action-focus-ring);
  outline-offset: 2px;
}

.btn-action:disabled {
  opacity: 0.45;
  pointer-events: none;
  filter: grayscale(0.4);
}
```

---

## 7. Functional Semantic Quad: Systemic Roles

Colors must have strict semantic consistency across the entire product. Never swap status colors for aesthetic whims:

| Semantic Role | Typical Hue Angle (OKLCH) | Intended Psychological Signal | UI Use Cases |
|---|---|---|---|
| **Success** | `H: 140 - 155` (Emerald / Mint) | Affirmation, completion, paid, safe | Payment verified, in-stock badge, order delivered, toggle on |
| **Warning** | `H: 70 - 85` (Amber / Marigold) | Attention required, non-fatal delay | Low stock warning, pending payment, awaiting staff review |
| **Danger** | `H: 25 - 35` (Crimson / Coral) | Error, destructive action, loss, out | Delete confirmation, out-of-stock, transaction rejected |
| **Info** | `H: 220 - 245` (Cobalt / Azure) | Contextual guidance, neutral metadata | System notice, department tag, version note, help tip |

### Semantic Component Triad:
Every semantic status must be built with 3 coordinated token tiers:
1. **Background Surface**: High lightness in light mode (`L: 0.95`, `C: 0.04`), low lightness in dark mode (`L: 0.22`, `C: 0.05`).
2. **Text / Foreground**: High contrast dark tone in light mode (`L: 0.35`, `C: 0.14`), bright tone in dark mode (`L: 0.85`, `C: 0.10`).
3. **Border / Accent**: Medium lightness (`L: 0.60`, `C: 0.12`) defining the bounding geometry.

---

## 8. Data Visualization Color Principles

Data graphics require distinct color logic separate from brand marketing:

### 8.1 Categorical (Qualitative) Palettes
* Used for unordered groups (departments, categories, product types).
* **Cap at 6 to 8 Hues**: Humans cannot reliably distinguish more than 8 colors simultaneously in a chart. For >8 categories, bundle remainder into "Others" or use secondary identifiers.
* **Equal Perceptual Weight**: Every hue in the palette must share similar OKLCH Lightness (`L ≈ 0.65`) and Chroma (`C ≈ 0.14`) so no category falsely appears more "important" than others.

### 8.2 Sequential Palettes
* Used for ordered numerical metrics (revenue, temperature, density, counts).
* Single-hue or narrow multi-hue gradient transitioning **monotonically in Lightness** from light to dark (or dark to light).
* Ensures chart remains 100% interpretable when printed in black and white or viewed by CVD users.

### 8.3 Diverging Palettes
* Used for metrics with a meaningful midpoint or zero (profit vs. loss, above vs. below average).
* Two distinct hues (e.g., Cold Slate/Blue vs. Warm Terracotta/Amber) meeting at a **desaturated neutral gray midpoint**.
* Avoid pure Red-to-Green divergence; prefer Blue-to-Orange or Teal-to-Brown for universal CVD accessibility.

---

## 9. Anti-Slop Color Directives

When building interfaces, coding agents must rigorously enforce these negative rules:

1. **NO Neon Purple/Cyan Radial "AI Glow"**: Do not place `radial-gradient(ellipse, #7c3aed, #06b6d4)` behind content. Lighting must simulate real-world studio optics, physical glass specular, or material reflection.
2. **NO Rainbow Badge Clutter**: Do not give every table row or badge a random bright pastel background (`bg-pink-100`, `bg-purple-100`, `bg-teal-100`) to create artificial visual excitement. Badges must be neutral or tied to functional semantic status.
3. **NO Saturated Muddy Dark Modes**: Do not generate dark modes by setting background to `#1a1a2e` with high-saturation purple/blue borders. Use controlled OKLCH surfaces with `C <= 0.02`.
4. **NO Low-Contrast Gray Text on Dark**: Do not render `#555555` or `#666666` text on `#1e1e1e` backgrounds. Always verify APCA / WCAG 4.5:1 minimum contrast.
5. **NO Unlinked Color Signifiers**: Never use a status color without its corresponding text or icon pairing (enforce the Dual-Encoding mandate).
