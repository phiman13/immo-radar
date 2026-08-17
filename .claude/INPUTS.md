<!-- Ledger: personal-stack/docs/INPUTS.md — nicht hier editieren.
     Neue Verdikte dort eintragen, dann propagate-canon.sh.
     Kanon-Hash: 2d9bbab2d3bd · propagiert: 2026-08-17 -->

# INPUTS — bewertete externe Ressourcen

> **Die eine Liste dessen, was von außen in den Stack darf.** Freigegebene Sammlungen,
> abgelehnte Kandidaten mit Grund, und was in einem Projekt bereits gescheitert ist.
>
> **Der Kanon verweist hierher, statt Quellen selbst aufzuzählen.** Eine neue Sammlung wird
> hier eingetragen und gilt sofort in allen Repos — ohne Kanon-Edit, ohne Propagation.

## Wie diese Datei benutzt wird

| Wann | Was |
|---|---|
| **Vor dem Bau einer generischen UI-Komponente** | §1 prüfen — gibt es sie fertig? |
| **Vor dem Bau eines Workflows / bei Fähigkeits-Lücke** | `/find-skills` bzw. `skills.sh` — Fundstücke landen in §2 |
| **Vor jeder Library-Empfehlung an ein Projekt** | §3 prüfen **und** `git log` des Zielprojekts |
| **Neue Ressource gefunden** | Agenten-Erweiterung → `/tooling-gate`; Katalog → direkt in §1 eintragen |

**Abgelehntes bleibt stehen.** Der Wert dieser Datei liegt zur Hälfte darin, dass nichts
zweimal bewertet wird.

**Zwei Risikoklassen, bewusst getrennt:** §1 sind Ressourcen, die *Code in ein Projekt*
bringen (normale Dependency-Sorgfalt). §2 sind Erweiterungen, die *mit Philipps Credentials
laufen* — die gehen durch `/tooling-gate`.

---

## §1 Projekt-Ressourcen — Komponenten, Libraries, Kataloge

### Freigegeben

| Ressource | Was | Für welche Stacks | Anbindung |
|---|---|---|---|
| [bklit](https://bklit.com) `@bklit` | Charts & Dataviz, Vercel-OSS-Programm | Web / shadcn | `components.json`: `"@bklit": "https://ui.bklit.com/r/{name}.json"` → `npx shadcn add @bklit/area-chart` |
| [kokonutui](https://kokonutui.com) `@kokonutui` | Buttons, Cards, Backgrounds, AI-Komponenten | Web / shadcn | Registry-Namespace, wie oben |
| [skiper-ui](https://skiper-ui.com) `@skiper-ui` | „un-common" Komponenten | Web / shadcn | Registry-Namespace. ⚠️ **Free verlangt Attribution im Produkt** — vor Einsatz bewusst entscheiden |
| [motion.dev](https://motion.dev) | Animations-Engine + [Beispielsammlung](https://motion.dev/examples) | Web / React | npm-Paket. Keine Anbindung nötig |
| [anime.js](https://animejs.com) | Animations-Engine | Web / Vanilla | npm-Paket. **Alternative zu motion — nie beide in einem Bundle** |
| [shadcn Registry-Index](https://ui.shadcn.com/r/registries.json) | Verzeichnis von ~277 Komponenten-Registries | Web / shadcn | Wird von `npx shadcn add`/`search` **automatisch** konsultiert |
| [animata](https://animata.design/components) ([Repo](https://github.com/codse/animata)) | Handgemachte Interaktions-Animationen und Effekte | Web / React + Tailwind + Framer Motion | 2.776★, MIT. **Keine Registry** — Copy-Paste wie shadcn, Abhängigkeiten des Snippets selbst nachinstallieren. Nicht für `recipe-app` (React Native) |
| [Codrops Creative Hub](https://tympanus.net/codrops/hub/tutorials/) | Tutorials und Demos für aufwendige Web-Interaktionen | Web, alle Stacks | **Referenz, kein Import** — Technik verstehen und nachbauen, nicht Code übernehmen. Lizenz pro Demo prüfen, falls doch kopiert wird |

**Zur Aktualität:** Diese Kataloge liegen bei ihren Anbietern und werden dort gepflegt. Hier
steht nur, *dass* es sie gibt — nicht ihr Inhalt. Es gibt also nichts, was veralten kann.

### Geprüft und abgelehnt

| Ressource | Datum | Verdikt | Grund |
|---|---|---|---|
| **Motion+ / MotionScore** (€299 einmalig) | 2026-08-16 | nein | Fachlich stark (misst Animations-Render-Kosten aus Source + Runtime, CI-Gate `npx motionscore --threshold`). Aber: ersetzt den Device-Check aus DoD §5 nicht, und `recipe-app` ist React Native → dort wirkungslos. **Neu bewerten**, falls Web-Animation zum Schwerpunkt wird |
| **kokonutui Pro** | 2026-08-16 | nein | Bei ~15 installierten UI-Skills ist „zu wenig Komponenten-Quellen" nicht der Engpass |
| **react-native-reusables** | 2026-08-17 | nein für `recipe-app` | 8.603★, MIT, aktiv — technisch der einzige RN-Fit. Aber `recipe-app` nutzt NativeWind faktisch nicht (1 von 85 Komponenten mit `className`, 65 mit `StyleSheet` + eigenen Tokens); `components.json`, `cn`, `clsx`, `tailwind-merge`, `@rn-primitives` fehlen alle. Anschluss wäre ein Paradigmenwechsel für 85 Komponenten. **Für ein neues RN-Projekt mit NativeWind von Anfang an: erste Wahl** |

---

## §2 Agenten-Erweiterungen — Skills, Plugins, MCPs

> Vetting-pflichtig über `/tooling-gate` (8 Punkte + Vorab-Scan). Diese laufen mit Philipps
> Credentials.

### Aktiv genutzt

| Erweiterung | Funktion | Anmerkung |
|---|---|---|
| **`find-skills`** (vercel-labs, MIT) | **Der Discovery-Kanal für Skills.** `npx skills find <query>` durchsucht [skills.sh](https://skills.sh) live mit Install-Zahlen | Liegt in `~/.claude/skills/`. ⚠️ **`npx skills check` ist ein Alias für `update`** — es prüft nicht, es aktualisiert (verifiziert 2026-08-17). Nie in einem automatischen Job verwenden |
| **`impeccable`** (pbakaus, Plugin) | UI-Design-Suite | Aktiv, v4.1.1. **Aufruf seit 2026-08-17: `/impeccable <subcommand>`** — z. B. `/impeccable critique`, `/impeccable polish`, `/impeccable audit`. Das Plugin bündelt alle früheren Einzel-Skills in einen Dach-Skill (`user-invocable`, siehe `argument-hint`). Die 16 losen Einzelkopien vom 20.05. waren veraltete Duplikate und liegen jetzt unter `~/.claude/.skills-archive-2026-08-17/` — verschoben, nicht gelöscht |
| **`klartext`** (Eigenbau) | Entfernt KI-Sprachmuster aus deutschen und englischen Texten | Deutscher Port von `stop-slop` (MIT). Struktur-Regeln übernommen, Phrasenlisten neu für das Deutsche erhoben. Quelle: `personal-stack/skills/klartext/` |

### Geprüft und abgelehnt

| Ressource | Datum | Verdikt | Grund |
|---|---|---|---|
| **task-observer** (one-skill-to-rule-them-all) | 2026-08-16 | nein | Live-Capture in jeder Session: Token- und Wartungs-Overhead **sicher**, Nutzen **unbewiesen**. Autonomous-Apply kollidiert mit `feedback_align_before_governance_changes`. Schwerwiegender (Fable): ein Fremd-Skill, der autonom Skills umschreibt — inkl. sich selbst — ist bei `autoUpdate: true` ohne Pinning-Möglichkeit ein Eskalationsvektor |
| **`npx skills` als Installer** | 2026-08-16 | nein | Der Skill `find-skills` ist bereits installiert und wird genutzt (s. o.). Den *Installer* parallel zu Claude-Code-Plugins zu fahren erzeugt doppelte Installs mit unklarer Präzedenz — genau der Fall, der bei `impeccable` eingetreten ist |
| **stop-slop** | 2026-08-16 → **portiert 2026-08-17** | nicht installiert, **Idee übernommen** | Die englischen Phrasenlisten greifen für deutsche Texte nicht, die Struktur-Regeln sehr wohl. Nach „Port, don't vendor" als eigener Skill `klartext` umgesetzt (s. o.) — deutsche Phrasenlisten neu erhoben, Struktur-Regeln übernommen, Herkunft und MIT-Lizenz im Skill genannt |
| **@netlify/mcp** | 2026-05-31 | nein | Nur Dev-Komfort, kostet write-fähige Prod-Credential-Fläche + permanente Tools im Context. `netlify-cli` deckt ~95 % ab. Betriebsdetails: Memory `project_netlify_mcp_skip` |
| **open-design**, **claude-mem**, **GSD**, **Everything-Claude-Code**, **Awesome-Subagents**, **codeburn** | 2026-06-01 / 2026-06-12 | quarantine / abgelehnt | Namespace-Bomben, `curl\|bash`, verdeckte Telemetrie, konzeptionelle Doppelstrukturen. Volle Begründungen: Memories `project_tooling_gate_2026_06_vetting`, `project_tooling_gate_2026_06_medium12` |
| **designlang** (design-extract), **anthropics doc-skills** | 2026-06 | zurückgestellt | Sauber, aber ohne belegten Bedarf. Trigger für Reaktivierung in den beiden Memories oben |

---

## §3 In einem Projekt gescheitert — nicht erneut vorschlagen

> Die wichtigste Sektion für Empfehlungen. Was hier steht, ist im Netz nirgends
> dokumentiert — es steht nur in der git-Historie des jeweiligen Projekts.

| Ressource | Projekt | Was passiert ist |
|---|---|---|
| **@gorhom/bottom-sheet** | `recipe-app` | Migriert in `aef114c3`, dann fünf Fix-Commits (Expo-Router-Inkompatibilität → hybrid Modal+gorhom, `container-height-0`-Bug, `onChange(-1)`-Guard beim Mount), dann `84fc573e` Ersatz durch RN Animated, `2c3e902a` „gorhom abandoned". Heute: `@lodev09/react-native-true-sheet` v3.10.1 |
| **react-native-reusables** | `recipe-app` | Passt nicht zum Styling-Ansatz (StyleSheet + eigene Tokens statt NativeWind-Klassen). Details in §1 |

---

## Änderungshistorie

| Datum | Was |
|---|---|
| 2026-08-17 | Angelegt. Erstbefüllung aus der Ressourcen-Session vom 2026-08-16/17 (8 vorgelegte Ressourcen + Codex- und Fable-Review) sowie aus den Tooling-Gate-Verdikten 2026-05/06. Herleitung: `docs/archive/2026-08-16-input-kuration-und-ressourcen-zugriff.md` + `docs/archive/2026-08-17-ressourcen-zufluss.md` |
| 2026-08-17 | `stop-slop` als `klartext` portiert · impeccable-Duplikate archiviert · automatische Kandidaten-Suche über die skills.sh-API im Cockpit (monatlich, read-only) |
