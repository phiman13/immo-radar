<!-- Kanon: personal-stack/core/CONVENTIONS.md — nicht hier editieren.
     Kanon-Hash: bd60e3c0e886 · propagiert: 2026-05-29 -->

# Konventionen — kanonischer Kern

> Universeller Disziplin-Kern für alle Projekt-Repos. Reist als
> `.claude/CONVENTIONS.md` mit jedem Klon. Kanon:
> `personal-stack/core/CONVENTIONS.md`.
>
> Aufnahme-Kriterium: nur Inhalt, der (universell oder klar bedingt) UND stabil
> UND kurz ist.

## Security — nicht verhandelbar

- Niemals Secrets hardcoden — API-Keys, Tokens, Passwörter ausschließlich aus
  Umgebungsvariablen.
- `.env` nie committen — immer `.env.example` mit Platzhaltern pflegen.
- Supabase: RLS auf allen Tabellen; `service_role`-Key nie im Client-Code.
- Claude API: Key nur serverseitig, nie in Browser-Code oder Git.

## Commit-Konvention

- Nach jeder logischen Änderung: `git add -A && git commit && git push`.
- Format: `typ(scope): was und warum`.
- Typen: `feat` · `fix` · `docs` · `refactor` · `test` · `chore`.
- Ein Commit = eine logische Änderung — klein und fokussiert.

## Definition of Done

1. Lokal getestet (golden path + edge cases).
2. Cross-App-Impact geprüft.
3. Relevante Doku aktualisiert (`CLAUDE.md`, `DEVELOPMENT.md`, `README` wo nötig).
4. *(falls TypeScript)* TypeCheck grün: `tsc --noEmit`.
5. *(falls UI-Änderung)* `/audit` + Browser-Test ausgeführt. Bei vorhandener
   visueller Referenz (HTML-Mockup, Design-Sandbox, Screenshot-PNG): Referenz
   zuerst gelesen (Read, nicht nur Pfad-Mention), nach Edit expliziter
   Side-by-Side-Vergleich. Bei Mobile-Performance/Animation: „done" erst nach
   User-Bestätigung auf Test-Profil — nicht aus TypeCheck/Simulator ableiten.
   *(Skill-Bezug — A.2 schärft diese Klausel.)*
6. Committed und gepusht.
7. *(bei substanziellen Änderungen)* Vor dem Merge `/codex:review` als
   Vier-Augen-Prinzip — Code-Review + Optimierung durch eine zweite Engine.
   Echter Widerspruch → klären; ergänzende Perspektive → Synthesis.
   *(Routing + weitere Codex-Auslöser: SKILLS §8.)*
8. *(bei kritischen Änderungen — Auth, Datenmigration, RLS-Policies, Payment)*
   Vor dem Merge `/ultrareview` gegen Branch/PR (Cloud-Bug-Hunt-Flotte) — user-
   getriggert und kostenpflichtig, kann nicht automatisch gestartet werden.
   *(Research preview, Stand 2026-05 — Command kann sich ändern.)*

## Globale Konventionen

- Sprache: Kommentare und Commit-Messages DE oder EN (konsistent pro Projekt),
  Code/Variablen EN.
- Keine unnötigen Kommentare — nur wenn das WHY nicht offensichtlich ist.
- Keine vorausschauenden Abstraktionen — nur bauen, was jetzt gebraucht wird (YAGNI).
- Fehlerbehandlung nur an System-Grenzen (User-Input, externe APIs), nicht intern.
- Tests vor Implementation, wo möglich (TDD).
- *(Tailwind-Projekte)* `cn()` für conditional Klassen — nie raw string
  concatenation.
- **Asset-Reuse vor Asset-Nachbau:** Wenn Original-Assets, Tokens, Primitives,
  Sandbox-Komponenten oder Mockups existieren: reusen statt manuell nachbauen
  — gilt auch für UI-Mockups, die echte App-Tokens/Primitives verwenden müssen
  statt generischer HTML-Snippets. SVGs, Font-Offsets, Shadow-Stacks gehen
  beim Nachbau reproduzierbar schief.
- **Stack-weite Rollouts:** Allowlist-, Propagation-, Skill-Install- und
  Doku-Rollouts laufen default auf **alle** Repos aus `core/targets.txt`.
  Einzelne Repos nur mit explizitem User-Hinweis ausschließen.

## Doku-Ablage

- Design-Specs → `docs/specs/`.
- Implementierungspläne → `docs/plans/`.
- Abgelöste Docs → `docs/archive/`.
- Projekt-Backlog & -Status → Linear (nicht als lokale Datei).
- Verzeichnisse lazy anlegen — sie entstehen mit der ersten Datei.
- **File-Move/Decommission — Rückzeiger-Pflicht:** Beim Verschieben, Umbenennen
  oder Stilllegen einer Datei immer alle Rückzeiger prüfen:
  `grep -r 'DATEINAME' . --include='*.md'` auf CLAUDE.md, STATUS.md,
  DEVELOPMENT.md, README.md und Memory-Files. Alle Treffer im selben Commit
  updaten — nie als separater Nachfolge-Commit.
- **Docs-Aktualität:** Dokumentation muss die aktuelle Realität abbilden.
  Trigger: Feature deployed → Doku im selben Commit anpassen; Workflow abgelöst
  → alten Doc archivieren; Roadmap-Item abgeschlossen → zeitnah aus aktivem
  Status entfernen. Eine veraltete Doku ist schlechter als keine Doku — sie
  führt aktiv in die Irre.
- **Kritische Workflow-Docs** (Pflicht-Lesung jede Session): per `@`-Include in
  `CLAUDE.md` einbinden — nicht nur per Prosa-Referenz. Nur dann ist die
  Pflicht-Lesung zuverlässig garantiert.

## Telegram-Notifications *(Projekte mit Telegram-Anbindung)*

Kritische Produktions-Fehler und Start/Ende von Long-running-Operations melden;
Format kurz, faktisch, mit Kontext (welches Projekt, was ist passiert).

## Arbeitsweise

- **Briefing-first:** Vor kreativer Arbeit (Feature, Komponente,
  Verhaltensänderung) erst Intent, Anforderungen und Design klären — nicht direkt
  in Code springen.
- **Kontext-Hygiene:** Kontext zwischen Features verdichten, zwischen
  unzusammenhängenden Aufgaben frisch starten; die Kontext-Last beobachten.
- **User-Decision-Pattern:** Entscheidungen, deren Antwort den weiteren Weg
  ändert und die nicht aus dem Repo verifizierbar sind, dem User vorlegen — nicht
  raten. Sonst konventionelle Defaults wählen und weitermachen.
- **Session-Kickoff:** Bei nicht-trivialen Aufgaben: Scope + Approach kurz
  skizzieren (bei impliziter Breite — Cross-Repo-Cleanup, mehrere
  zusammenhängende Flows/Features — bewusst weit scopen und Scope-Grenzen
  explizit nennen, statt eng zu defaulten und auf User-Korrektur zu warten),
  alle bekannten Entscheidungs-Forks gebündelt vorlegen, riskante Aktionen
  (push, deploy, destructive ops) vorab nennen. Danach autonom bis zum nächsten
  echten Blocker — nicht zwischendrin nach Bestätigung fragen, wenn die Antwort
  schon im Kickoff geklärt war.
- **Plugin-/Skill-Discovery:** Nach Plugin-Install oder Skill-Änderung erst
  `/reload-plugins` (oder neue Session) + Verfügbarkeitsprüfung, bevor der
  nachfolgende Command-Flow startet.
- **`subagent-driven-development`-Schwelle:** Erst ab ≥ 4 wirklich unabhängigen
  Tasks verwenden — bei weniger Tasks direkt ausführen. Unabhängig = kein
  shared State, kein Edit der gleichen Datei.
- **Subagent-Kontext = frisch (Default):** Subagents starten ohne Session-
  Kontext — Instruktion gezielt konstruieren (schützt Kontext-Hygiene).
  `CLAUDE_CODE_FORK_SUBAGENT=1` (voller Kontext-Erbe) nur bewusst case-by-case,
  nie global aktivieren.
- **Autonome Zielverfolgung (`/goal`):** Für substanzielle Arbeit mit
  *maschinen-verifizierbarem* End-State (`tsc --noEmit` clean, Build exit 0,
  Lint/Tests grün) eine `/goal`-Bedingung + Turn-/Zeit-Limit setzen, statt jeden
  Turn manuell anzustoßen. Bedingung nur, was aus dem Transcript beweisbar ist
  — der Evaluator führt selbst nichts aus. **Nie** als Done-Gate für Mobile-
  Performance/Animation (dort gilt die User-Bestätigung aus DoD §5).
  *(Research preview, Stand 2026-05 — Command kann sich ändern.)*
- **Selbstverbessernde Mechanismen:** Müssen automatisch triggern (cron/launchd/
  SessionStart-Hook) — nie auf User-Erinnerung setzen.

## Design-Disziplin *(Frontend-Repos)*

> Universelle Frontend-Disziplin. Projekt-spezifische Brand-Tokens stehen in
> `.claude/DESIGN.md` des jeweiligen Repos. Skill-Routing für Design steht in
> `.claude/SKILLS.md`.

### Aesthetic-Prinzipien (kein AI-Slop)

- Typografie: charakterstarke, unerwartete Fonts. Nicht Inter, Arial, Roboto,
  system-ui, Space Grotesk.
- Farbe: dominante Farbe + scharfer Akzent, CSS-Variablen für Konsistenz. Keine
  timiden Paletten, keine lila Gradienten auf Weiß.
- Hintergründe: Atmosphäre schaffen — CSS-Gradienten, geometrische Patterns.
  Kein Solid-Color-Default.
- Motion: CSS-Keyframes bevorzugen, Motion-Library für React. Ein orchestrierter
  Page-Load mit staggered reveals schlägt verstreute Micro-Interactions.
- Abwechslung: zwischen Light/Dark wechseln, überraschende Kombinationen.

### Animation-Regeln

- `whileInView` immer mit `once: true` — kein Re-Trigger beim Rückscrollen.
- CSS-only bevorzugen; JS-Animationen nur wenn CSS nicht ausreicht.
- `prefers-reduced-motion` respektieren.

### Accessibility-Baseline (WCAG AA)

- Kontrastverhältnis ≥ 4.5:1 für Text.
- Keyboard-Navigation + sichtbare Focus-States auf allen interaktiven Elementen.
- Semantisches HTML, ARIA-Labels wo nötig.

### Mobile-first

Breakpoints immer von klein nach groß definieren.
