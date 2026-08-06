<!-- Kanon: personal-stack/core/CONVENTIONS.md — nicht hier editieren.
     Kanon-Hash: ff47e9de2c32 · propagiert: 2026-08-06 -->

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
- **Mechanische Gates:** `block-secrets-hook.sh` (PreToolUse Write|Edit, exit 2) + Deny-Set in `~/.claude/settings.json` erzwingen die Prosa-Regeln.
- **`.claudeignore` pro Repo:** Untrusted Fixtures, `vendor/`, `*.har`, Dumps eintragen — was Claude lesen kann, kann Prompt-Injection tragen.
- **Plugin-Supply-Chain:** `autoUpdate: true`, kein SHA-Pinning; Schutz via `block-secrets-hook` + Deny-Set + `/tooling-gate` beim Erst-Install. `disableSkillShellExecution` NICHT aktiv (bricht codex). Detail: Memory `project_plugin_autoupdate_on`.
- **Auto-Mode-Classifier:** `defaultMode: "auto"` bleibt; False-Positives als enge Allow-Regel in `.claude/settings.json` verankern — nie Classifier abschalten. Detail: Memory `project_automode_deploy_allowlist`.
  **Zwei Sorten False-Positive, zwei Antworten** (Details/Evidenz: `docs/specs/2026-08-05-autonome-sessions-und-session-limit.md`): Blockt *ein Befehlsmuster* → enge Allow-Regel, wie oben. Blockt es in *Wellen* spät in einer langen Session → Ursache ist die Session, nicht die Regel; Antwort ist Session-Hygiene + Block-Resilienz, **nicht** eine breitere Allow-Regel oder ein globaler `permissionDecision: "allow"`-Hook.
- **Block-Resilienz:** Ein Classifier-Block beendet keinen autonomen Lauf. Reihenfolge: (1) **nicht** umformulieren und erneut versuchen — wirkungslos; (2) wo möglich inline statt delegieren; (3) unabhängige Aufgaben zu Ende führen; (4) blockierte Aktionen **gebündelt** am Ende melden, nicht einzeln nachfragen.

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
5. *(falls UI-Änderung)* `/audit` + Browser-Test ausgeführt. Bei vorhandener visueller
   Referenz (HTML-Mockup, Design-Sandbox, Screenshot-PNG): Referenz zuerst gelesen (Read,
   nicht nur Pfad-Mention), nach Edit expliziter Side-by-Side-Vergleich. Bei Mobile-
   Performance/Animation: „done" erst nach User-Bestätigung auf Test-Profil.
6. Committed und gepusht.
7. *(bei substanziellen Änderungen)* Vor dem Merge `/codex:review` als Vier-Augen-Prinzip
   — Code-Review + Optimierung durch eine zweite Engine. Echter Widerspruch → klären;
   ergänzende Perspektive → Synthesis. *(Routing: SKILLS §8.)*
8. *(bei kritischen Änderungen — Auth, Datenmigration, RLS-Policies, Payment)* Vor dem
   Merge `/ultrareview` gegen Branch/PR (Cloud-Bug-Hunt-Flotte) — user-getriggert und
   kostenpflichtig, nicht automatisch startbar. *(Research preview, Stand 2026-05.)*

## Globale Konventionen

- Sprache: Kommentare und Commit-Messages DE oder EN (konsistent pro Projekt),
  Code/Variablen EN.
- Keine unnötigen Kommentare — nur wenn das WHY nicht offensichtlich ist.
- Keine vorausschauenden Abstraktionen — nur bauen, was jetzt gebraucht wird (YAGNI).
- Fehlerbehandlung nur an System-Grenzen (User-Input, externe APIs), nicht intern.
- Tests vor Implementation, wo möglich (TDD).
- *(Tailwind-Projekte)* `cn()` für conditional Klassen — nie raw string
  concatenation.
- **Asset-Reuse vor Asset-Nachbau:** Original-Assets, Tokens, Primitives, Mockups immer reusen statt nachbauen — auch UI-Mockups müssen echte Tokens nutzen, keine generischen Snippets. SVGs, Font-Offsets, Shadow-Stacks gehen beim Nachbau reproduzierbar schief.
- **Stack-weite Rollouts:** Allowlist-, Propagation-, Skill-Install- und
  Doku-Rollouts laufen default auf **alle** Repos aus `core/targets.txt`.
  Einzelne Repos nur mit explizitem User-Hinweis ausschließen.

## Doku-Ablage

- Design-Specs → `docs/specs/`.
- Implementierungspläne → `docs/plans/`.
- Abgelöste Docs → `docs/archive/`.
- Verzeichnisse lazy anlegen — sie entstehen mit der ersten Datei.
- **File-Move/Decommission — Rückzeiger-Pflicht:** Beim Verschieben, Umbenennen oder
  Stilllegen einer Datei immer alle Rückzeiger prüfen (`grep -r 'DATEINAME' . --include='*.md'`
  auf CLAUDE.md, STATUS.md, DEVELOPMENT.md, README.md, Memory-Files) — alle Treffer im
  selben Commit updaten, nie als separater Nachfolge-Commit.
- **Docs-Aktualität:** Dokumentation muss die aktuelle Realität abbilden. Trigger: Feature
  deployed → Doku im selben Commit anpassen; Workflow abgelöst → Doc archivieren;
  Roadmap-Item abgeschlossen → zeitnah aus aktivem Status entfernen. Veraltete Doku ist
  schlechter als keine — sie führt aktiv in die Irre.
- **Kritische Workflow-Docs** (Pflicht-Lesung jede Session): per `@`-Include in `CLAUDE.md`
  einbinden — nicht nur per Prosa-Referenz, sonst ist die Pflicht-Lesung nicht garantiert.

## Doku-Rollen — single fact, single place

> Ein Fakt lebt an **genau einem Ort**; überall sonst steht nur ein Verweis.
> Das verhindert das inhaltliche Wegdriften lokaler Doku vom Backlog und macht
> jeden frischen Chat schnell orientiert. Drei Rollen, je genau eine pro Repo:

- **Linear = SSoT für alle offenen Items.** Kein offenes To-do/Backlog-Item wird in lokalen
  `.md`-Dateien getrackt. Lokale Backlog-Dateien sind als Arbeitsfläche verboten; Legacy-
  Dateien (`BACKLOG.md`) auf bloßen Pointer + ID-Map einfrieren oder löschen. *Repo ohne
  Linear-Projekt:* Projekt anlegen ODER Repo als „ruht" markieren — nie Backlog-Wildwuchs.
- **`docs/STATUS.md` = der EINE lokale Stand-Snapshot.** Kuratierter aktueller Stand +
  nächster Schritt + Branch-Map + Linear-Pointer; narrativ, **kein** Item-Tracking.
  Detailhistorie → `STATUS-ARCHIVE.md`. Kanonischer Pfad, keine Wahlfreiheit.
- **`CLAUDE.md` = der EINE Onboarding-Eingangspunkt.** Bindet `@docs/STATUS.md` per Include
  ein und enthält mindestens: (1) 1-Absatz-Pitch, (2) Tech-Stack + Verzeichnis-Tour je 1
  Zeile, (3) Start-/Test-/Deploy-Befehle, (4) Linear-Pointer. Selbst **keine** Backlog-Items.
  *Monorepo:* root-`CLAUDE.md` = Orientierung, package-level = nur lokale Konventionen.
- **Onboarding-Reality-Check:** Zu Sessionbeginn `git log --oneline -10` lesen — Doku
  verkleinert den Suchraum, ersetzt aber nie die Code-Exploration.
- **Konflikt-Auflösung:** Widersprechen sich git / Linear / `docs/STATUS.md`, gilt git für
  Fakten, Linear für gewollte Arbeit — im Zweifel User fragen, nicht raten.
- **Anti-Drift-Trigger:** Feature fertig → „nächster Schritt" in `docs/STATUS.md` im selben
  Commit aktualisieren; offene Items ausschließlich in Linear.
- **Anti-Überfrachtung:** Orientierung gehört in `CLAUDE.md` + `docs/STATUS.md` — keine
  neuen Pflicht-Dokumente, netto wächst die Doku-Fläche nicht. Gate: `scripts/check-doc-roles.sh`
  warnt (blockt nicht) bei fehlendem Include oder offenen Items in `BACKLOG.md`.

## Telegram-Notifications *(Projekte mit Telegram-Anbindung)*

Kritische Produktions-Fehler und Start/Ende von Long-running-Operations melden;
Format kurz, faktisch, mit Kontext (welches Projekt, was ist passiert).

## Arbeitsweise

- **Briefing-first:** Vor kreativer Arbeit (Feature, Komponente,
  Verhaltensänderung) erst Intent, Anforderungen und Design klären — nicht direkt
  in Code springen.
- **Kontext-Hygiene:** Kontext zwischen Features verdichten, zwischen
  unzusammenhängenden Aufgaben frisch starten; die Kontext-Last beobachten.
- **Session-Hygiene bei langen autonomen Läufen:** Mehrphasige Läufe
  (`subagent-driven-development`, `/goal`, Migrationen) in **Etappen mit je frischer
  Session** fahren, Etappengrenze = Phasengrenze des Plans — nicht eine Session über
  viele Stunden. Grund: Classifier-Block-Häufung korreliert mit Session-Laufzeit/
  Dispatch-Zahl, nicht Inhalt (`docs/specs/2026-08-05-autonome-sessions-und-session-limit.md`).
- **Modell-Routing:** Interaktiver Default ist **Sonnet** (hart in `~/.claude/settings.json`),
  mit **Opus als `advisorModel`** — an Entscheidungspunkten konsultiert (Approach-Wahl,
  wiederkehrende Fehler, Completion-Check), statt durchgehend zu laufen. `/model opus`
  bewusst für Aufgaben, die durchgehend Opus brauchen (subtile Multi-File-Architektur) —
  Wahl nach Komplexität, nicht Pauschal-Default. Bei **Subagents/Headless-Jobs**: `model`-Param
  hart auf **Sonnet** (Batch-Jobs auf **Haiku**), Review-/Architektur-/Merge-Gate-Subagents
  auf **Opus** — explizit gesetzt. **Kritische Arbeit** (Auth, Datenmigration, RLS-Policies,
  Payment, irreversible Änderungen) **nicht ohne Opus-Plan/-Review finalisiert**.
- **User-Decision-Pattern:** Entscheidungen, deren Antwort den weiteren Weg
  ändert und die nicht aus dem Repo verifizierbar sind, dem User vorlegen — nicht
  raten. Sonst konventionelle Defaults wählen und weitermachen.
- **Session-Kickoff:** Bei nicht-trivialen Aufgaben: Scope + Approach skizzieren (bei impliziter Breite bewusst weit scopen, Scope-Grenzen explizit nennen), alle Entscheidungs-Forks + riskante Aktionen gebündelt vorlegen. Danach autonom bis zum nächsten echten Blocker — nicht zwischendrin fragen, wenn der Kickoff es geklärt hat.
- **Plugin-/Skill-Discovery:** Nach Plugin-Install oder Skill-Änderung erst
  `/reload-plugins` (oder neue Session) + Verfügbarkeitsprüfung, bevor der
  nachfolgende Command-Flow startet.
- **`subagent-driven-development`-Schwelle:** Erst ab ≥ 4 wirklich unabhängigen
  Tasks verwenden — bei weniger Tasks direkt ausführen. Unabhängig = kein
  shared State, kein Edit der gleichen Datei. **Geteilte Dateien nie parallel:**
  Barrel-Exports / Router / `index`-Dateien einem einzigen Integrations-Agent
  zuweisen, der am Ende verdrahtet — die übrigen schreiben self-contained Module.
- **Migration/Refactor-Constraints:** Bei Migrationen/größeren Refactors zuerst Bestand
  analysieren + Plan schreiben (audit-first), dann harte Invarianten im Prompt:
  „bestehendes Verhalten nicht ändern" / „types-only pass"; alte Dateien bis zur
  Verifikation behalten (kein half-broken state), phasenweise mit Verifikation dazwischen.
- **Subagent-Kontext = frisch (Default):** Subagents starten ohne Session-
  Kontext — Instruktion gezielt konstruieren (schützt Kontext-Hygiene).
  `CLAUDE_CODE_FORK_SUBAGENT=1` (voller Kontext-Erbe) nur bewusst case-by-case,
  nie global aktivieren.
- **Autonome Zielverfolgung (`/goal`) — proaktiv anbieten:** Sobald eine Aufgabe ein
  maschinen-prüfbares Abschluss-Prädikat hat (`tsc --noEmit`=0, Test-Suite grün nach
  Refactor, Lighthouse-Score ≥ Schwelle via `/audit`), **`/goal` vorschlagen, bevor
  turn-based losgelegt wird** — nicht warten, bis der User es nennt (SessionStart-Hook
  erinnert daran, s. Betrieb). Disziplin: genau ein Prädikat + Turn-/Zeit-Limit — nie
  Qualitäts-Auflagen bündeln (sonst unerfüllbar → `/goal clear`). **Nie** als Done-Gate
  für Mobile-Performance/Animation (→ DoD §5). *(Research preview, Stand 2026-05.)*
- **Loop-Mechanik je Task:** Vier Stufen — turn-based (Prompt + Verification-Skills),
  goal-based (`/goal`), time-based (`/loop` lokal / `/schedule` Cloud), proactive
  (`/schedule` + dynamic workflows + auto mode). **`/loop`** (session-scoped) für
  Babysitting *während* aktiver Arbeit (PR/CI, Deploy-Health, Codex-Round-Trips) —
  **kein** Ersatz für launchd/cron. **launchd/cron bleibt Default;** `/schedule` nur,
  wenn der Job Claude-Reasoning **und** cloud-erreichbare Inputs braucht — nicht lokale
  Working-Copies/unpushte Commits/`~/.claude`-Logs; Deterministisches bleibt Skript.
  *(Research preview, Stand 2026-07.)*
- **Selbstverbessernde Mechanismen:** Müssen automatisch triggern (cron/launchd/
  SessionStart-Hook) — nie auf User-Erinnerung setzen.
- **Stack-Self-Modify:** Edits an CONVENTIONS, SKILLS und settings in personal-stack sind trusted — git ist das natürliche Protokoll, kein separates Audit-Gate erforderlich.

## Design-Disziplin *(Frontend-Repos)*

> Universelle Frontend-Disziplin. Projekt-spezifische Brand-Tokens: `.claude/DESIGN.md`
> des jeweiligen Repos. Skill-Routing für Design: `.claude/SKILLS.md`.

### Aesthetic-Prinzipien (kein AI-Slop)

- Typografie: charakterstarke, unerwartete Fonts. Nicht Inter, Arial, Roboto, system-ui, Space Grotesk.
- Farbe: dominante Farbe + scharfer Akzent, CSS-Variablen für Konsistenz. Keine timiden Paletten, keine lila Gradienten auf Weiß.
- Hintergründe: Atmosphäre schaffen — CSS-Gradienten, geometrische Patterns. Kein Solid-Color-Default.
- Motion: CSS-Keyframes bevorzugen, Motion-Library für React. Ein orchestrierter Page-Load mit staggered reveals schlägt verstreute Micro-Interactions.
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
