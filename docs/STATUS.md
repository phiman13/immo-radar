# Status — immo-radar

> Kuratierter Stand-Snapshot (Kanon: *single fact, single place*). Detailhistorie →
> `docs/STATUS-ARCHIVE.md`. Offene Items → **Linear** (Team HER, Projekt `immo-radar`).
> Architektur-/Quellen-Detail: `CLAUDE.md`.

## Status: Stillgelegt (2026-08-18)

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km). VPS-Deployment abgebaut
(Container gestoppt und entfernt, Docker-Image gelöscht, Caddy-Vhost
`immo.herrlich.dev` entfernt), Scheduler läuft nicht mehr. Repo bleibt auf
GitHub bestehen, Code + lokale SQLite-DB liegen weiterhin unter
`/opt/immo-radar` auf der VPS (kein nennenswerter Platzbedarf).

**Falle beim Abbau selbst:** ein GitHub-Webhook (`repos/phiman13/immo-radar/hooks`,
Ziel `https://herrlich.dev/webhook/github`, stack-weiter Auto-Deploy-Listener)
löste beim Push des ersten Stilllegungs-Commits sofort einen Redeploy aus —
Container und Image waren nach dem manuellen Abbau binnen Minuten wieder da.
Fix: Webhook für dieses Repo explizit auf `active:false` gesetzt
(`gh api -X PATCH repos/phiman13/immo-radar/hooks/621091139 -F active=false`),
danach Abbau wiederholt. **Bei Reaktivierung zuerst den Webhook wieder
aktivieren** — sonst deployt kein Push automatisch.

**Grund:** Root-Cause-Analyse nach einer irrelevanten Telegram-Benachrichtigung
deckte zwei Bugs auf (Geocoding-Fail-Open lässt ungeprüfte Objekte durch;
`Listing.lage_score` — die vom Notify-Schwellwert geprüfte Spalte — wurde nie
geschrieben, seit dem ersten Commit). Die anschließende Inhaltsprüfung der
Makler-Kaskade (dem eigentlichen Alleinstellungsmerkmal: Objekte exklusiv bei
einzelnen Maklern, nie auf ImmoScout/Kleinanzeigen) zeigte: von 13 gefundenen
Objekten 46 % bereits verkauft, 85 % ohne Preis, mehrere außerhalb des
Suchgebiets, kein einziges brauchbar. Vier Tage Echtbetrieb ohne jede
Nutzerinteraktion. Der Nutzer teilt die Einschätzung: das Kernversprechen
trägt aktuell nicht, unabhängig von einzelnen Fixes. Details und vollständige
Zahlen → `docs/STATUS-ARCHIVE.md#stilllegungs-analyse-2026-08-18`.

## Reaktivierung

Reversibel, wie schon einmal (Archivierung 2026-06-29 → Reaktivierung
2026-08-06). Sinnvoller Auslöser: ein konkreter, in der manuellen Suche
aufgefallener Fall, den das Tool nachweislich verpasst hätte — nicht ein
erneuter Breitbau-Versuch ohne validierten Bedarf. Bei Reaktivierung zuerst:
`Listing.lage_score`-Dead-Code entfernen (Notify-Gate auf `ai_score`
umstellen, siehe Session-Notizen), dann Kernquellen (Riedel, bs_immo, …)
einzeln auf Datenqualität prüfen, bevor erneut Makler-Abdeckung ausgebaut
wird.

## Branch-Map

- `main` — letzter Deploy-Stand vor Stilllegung. Deploy weiterhin via
  `scripts/deploy.sh` (rsync + docker compose), falls reaktiviert.
