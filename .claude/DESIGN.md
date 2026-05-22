<!-- Brand-Tokens immo-radar. Universelle Design-Disziplin: .claude/CONVENTIONS.md.
     Kein Kanon — projekt-eigen, hand-gepflegt. -->

# Design — Brand immo-radar

### Übersicht

Privates Immobilien-Scouting-Tool (Tutzing, 5 km Radius). Funktionales Dashboard-Design: warme Natur-Grün-Töne als Akzent, dezente natürliche Hintergründe. Leaflet-Karte als zentrales UI-Element. AI-Scoring via Claude Haiku.

### Farben — Basis

| Token | CSS-Variable | Tailwind-Klasse | Wert (oklch) | Verwendung |
|---|---|---|---|---|
| Background | `--bg` | `bg-bg` | `oklch(97% 0.006 120)` | Seitenhintergrund — warmes Weiß/Grün-Tint |
| Foreground | `--fg` | `text-fg` | `oklch(18% 0.010 240)` | Primärtext |
| Accent | `--accent` | `bg-accent` / `text-accent` | `oklch(45% 0.130 150)` | Grün — Hauptakzent, Links, Buttons |
| Accent Muted | `--accent-muted` | `bg-accent-muted` | `oklch(90% 0.040 150)` | Akzent-Hintergrund, Hover |
| Border | `--border` | `border-border` | `oklch(87% 0.010 120)` | Borders |
| Muted | `--muted` | `text-muted` | `oklch(60% 0.008 240)` | Sekundärtext, Labels |

### Status-Farben

| Status | Token | Wert | Semantik |
|---|---|---|---|
| Neu | `--status-new` | `oklch(58% 0.160 145)` | Neu eingegangen — Grün |
| Vielleicht | `--status-maybe` | `oklch(72% 0.150 75)` | Interessant, noch offen — Gelb |
| Abgelehnt | `--status-rejected` | `oklch(52% 0.180 25)` | Nicht interessant — Rot |
| Gesehen | `--status-seen` | `oklch(60% 0.008 240)` | Bereits gesichtet — Grau |

### Score-Farben (AI-Scoring)

| Score | Token | Wert | Schwellwert |
|---|---|---|---|
| Hoch | `--score-high` | `oklch(55% 0.160 145)` | Grün — gutes Match |
| Mittel | `--score-mid` | `oklch(70% 0.150 75)` | Gelb — mittleres Match |
| Niedrig | `--score-low` | `oklch(55% 0.160 25)` | Rot — schlechtes Match |

### Typografie

| Rolle | Font | Verwendung |
|---|---|---|
| Display / Headings | **Bricolage Grotesque** (Google) | h1, h2, h3 |
| Body | **Schibsted Grotesk** (Google) | Fließtext, UI-Elemente |
| Numerics / Preise | **Azeret Mono** (Google) | Preise, Scores, numerische Werte — `font-variant-numeric: tabular-nums` |

### Known Gaps

- Kein Dark Mode definiert.
- `--status-*` und `--score-*` Tokens sind nur in `index.css` definiert — **nicht** im `tailwind.config.ts`. Tailwind-Klassen für Status/Score existieren nicht; direkte CSS-Variable-Nutzung erforderlich.
- Kein explizites Spacing-Token-System.
- Leaflet-Karte (`leaflet/dist/leaflet.css`) ist außerhalb des Token-Systems — Leaflet-Stile nicht mit Brand-Tokens überschreiben ohne gründliches Testing.
