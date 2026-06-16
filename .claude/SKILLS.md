<!-- Kanon: personal-stack/core/SKILLS.md — nicht hier editieren.
     Kanon-Hash: 83d294d5b188 · propagiert: 2026-06-16 -->

<!-- Kanon: personal-stack/core/SKILLS.md — nicht hier editieren.
     Änderung am Kanon, dann propagieren (scripts/propagate-canon.sh). -->

# Skills — Routing

> Welcher Skill in welcher Situation. Kanon: `personal-stack/core/SKILLS.md`.
> Reist als `.claude/SKILLS.md` in jedes Repo.

## Skill aufnehmen / ersetzen

Neuer Skill installiert → eine Zeile in die passende Phase unten. Skill entfernt →
Zeile löschen. Ersetzt → Zeile umschreiben. Danach `scripts/propagate-canon.sh`.
Unsicher, welcher Skill existiert oder passt → `/find-skills`.

## 1. Planen

| Wann | Skill |
|---|---|
| Neues Feature, UX-Flow, Architektur-Entscheidung — Idee zu Spec | `/superpowers:brainstorming` |
| UX/UI eines Features vor dem Code durchdenken | `/shape` |
| Spec → detaillierter, schrittweiser Implementierungsplan | `/superpowers:writing-plans` |

## 2. Bauen

| Wann | Skill |
|---|---|
| Implementierungsplan abarbeiten — Subagent pro Task (ab ≥4 unabh. Tasks) | `/superpowers:subagent-driven-development` |
| Implementierungsplan abarbeiten — inline mit Checkpoints | `/superpowers:executing-plans` |
| Neue Funktion / Bugfix — Test zuerst | `/superpowers:test-driven-development` |
| Mehrere unabhängige Probleme parallel angehen | `/superpowers:dispatching-parallel-agents` |
| Feature-Arbeit isolieren | `/superpowers:using-git-worktrees` |
| Web-Komponente / Seite bauen | `/frontend-design` |
| Vollständiges Produkt-UI, Dashboard, Design-System wählen | `/ui-ux-pro-max` |
| Kompletter Design-Flow über mehrere Phasen in einem Durchgang | `/impeccable` |
| React-Native-Performance (FPS, TTI, Bundle, Memory) | `/react-native-best-practices` |
| Große Datei / komplette Komponente ohne Truncation generieren | `/full-output-enforcement` |

## 3. Debuggen

| Wann | Skill |
|---|---|
| Unerwartetes Verhalten, Bug — Ursache statt Symptom | `/superpowers:systematic-debugging` |
| Debugging-Deadlock (≥2 Versuche ohne Durchbruch) | `/codex:rescue` (→ Abschnitt 8) |

## 4. Design verfeinern

| Wann | Skill |
|---|---|
| Finaler Qualitäts-Pass, Produktions-Politur | `/polish` |
| Responsive / Mobile-Adaption | `/adapt` |
| Animation, Micro-Interaction, Motion einbauen | `/animate` |
| Unsichtbare Details, UI-Craftsmanship | `/emil-design-eng` |
| Design zu generisch / langweilig — mutiger | `/bolder` |
| Design zu laut / überladen — ruhiger | `/quieter` oder `/distill` |
| Farb-Probleme, Farbsystem | `/colorize` |
| Typography, Lesbarkeit, Text-Hierarchie | `/typeset` |
| Layout, Spacing, visuelle Hierarchie | `/layout` |
| Wow-Faktor, technisch ambitioniert | `/overdrive` |
| Design-Kritik / UX-Evaluation | `/critique` |
| Bestehendes Projekt auf Premium heben | `/redesign-existing-projects` |
| Bestimmte Ästhetik gewünscht | `/high-end-visual-design` · `/minimalist-ui` · `/industrial-brutalist-ui` · `/huashu-design` |

## 5. Prüfen & Abliefern

| Wann | Skill |
|---|---|
| Vor jeder „fertig"-Behauptung — Verifikation mit Belegen | `/superpowers:verification-before-completion` |
| Technischer Qualitäts-Check / a11y / Performance-Report | `/audit` |
| Browser-Testing bei UI-Änderungen — eigener ephemerer Browser (App validieren, Screenshots, Responsive, Login-Flows testen) | `/playwright-skill` |
| Aktion in deinem echten, eingeloggten Chrome — authentifizierte Real-World-Tasks auf Fremdseiten (Coursera, Gmail, …), Scraping hinter Login. **Nur bei explizitem User-Intent** (handelt als du), lokal-only | `browser-harness` (global @-Import + CLI, kein Slash-Command) |
| Code-Änderung für Review vorbereiten | `/superpowers:requesting-code-review` |
| Auf Code-Review-Feedback reagieren | `/superpowers:receiving-code-review` |
| Branch abschließen — Merge / PR / Cleanup | `/superpowers:finishing-a-development-branch` |

## 6. Marketing & Growth

Marketing-Skills (~40, `marketing-skills`-Plugin) auf Kategorie-Ebene. Detail-Skill
via `/find-skills` auflösen.

| Aufgabengebiet | Kategorie |
|---|---|
| Produkt-Launch planen | Launch |
| SEO, Content, programmatic SEO | SEO |
| Paid Ads, Ad-Creatives | Ads |
| Conversion-Optimierung (Signup, Pricing, Paywall, Popup) | CRO |
| Copywriting, Cold Email, Email-Sequenzen | Copy |
| Analytics, A/B-Tests, Customer Research | Analytics |

## 7. Meta / Workspace

| Wann | Skill |
|---|---|
| Neuen Skill schreiben / bestehenden ändern | `/superpowers:writing-skills` |
| Codebase/Doku als Wissensgraph (Obsidian) | `/graphify` |
| Verfügbare Skills finden | `/find-skills` |
| Vergangene Sessions analysieren (Continual-Improvement) | `review-past-performance` (wöchentlich Sonntag 18:00, headless) |
| Reflection-Findings triagieren und einarbeiten | `/reflection-triage` |

## 8. Codex-Sparring

Claude zieht Codex als Sparring-Partner hinzu — macht den Vorschlag, der User
entscheidet, ob er ihn annimmt.

| Auslöser | Command |
|---|---|
| Architekturentscheidung (Design, Schema, API-Kontrakt) | `/codex:adversarial-review` |
| Debugging-Deadlock (≥2 Versuche ohne Durchbruch) | `/codex:rescue` |
| Quick Second Opinion (Unsicherheit, kein Deadlock) | `/codex:review` |

**Trigger-Heuristik:** Nach 2 erfolglosen Fix-Iterationen mit User-Negativ-Feedback
aktiv `/codex:rescue` vorschlagen — nicht warten, bis der User es einfordert.

**Codebase an externe Engine geben:** Muss eine ganze Codebase an eine externe
LLM (Codex, Web-Claude, Paste) — kein Install, ad-hoc:
`npx repomix --style markdown --compress --copy` (secretlint default an, respektiert
`.gitignore`). Für *interne* Recherche bleibt context-mode das Werkzeug.

**Konfliktauflösung:** Echter Widerspruch → Stopp, zuerst klären. Ergänzende
Perspektive → Synthesis beider Positionen vorschlagen.
