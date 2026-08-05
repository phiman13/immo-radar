# Phase 0 — Vermessung der Makler-Websites

**Datum:** 2026-08-05
**Methode:** `scripts/probe_agent_sites.py`, 28 Makler-Domains im Fünfseenland
und Umgebung, je Site: Startseite, `robots.txt`, Sitemap, Feeds, vermutete
Angebotsseite. Rohdaten: `docs/superpowers/phase0-probe.json`.

**Zweck:** Beantworten, welche Stufen der geplanten Extractor-Kaskade real
zünden — bevor sie gebaut werden.

---

## Kernzahlen

| Messgröße | Ergebnis |
|---|---|
| Sites geprüft | 29 |
| erreichbar | 25 |
| aktiv geblockt (HTTP 403) | 3 |
| tot / DNS-Fehler | 1 |
| **Vendor-Fingerprint erkannt** | **13 von 25 (52 %)** |
| Angebotsseite automatisch gefunden | 24 von 25 (96 %) |
| **Sites mit ≥ 3 auffindbaren Objekt-URLs** | **22 von 25 (88 %)** |
| Objekt-URLs insgesamt gefunden | **4.275** |
| Sites ohne jede auffindbare Objekt-URL | 3 von 25 |
| eindeutiges `RealEstateListing` (JSON-LD) | 3 von 25 |
| echter Objekt-Feed | 1 von 25 |
| **öffentlich abrufbare OpenImmo-XML** | **0 von 25** |
| WordPress als CMS | 15 von 25 |

---

## Befund 1 — Vendor-Fingerprints tragen die Hälfte des Marktes

Das ist das Ergebnis, das die Architektur rechtfertigt. **Fünf Systeme decken
alle 12 erkannten Sites ab:**

| System | Sites | kumulative Abdeckung |
|---|---|---|
| immonex Kickstart | 5 | 21 % |
| onOffice | 4 | 33 % |
| OpenImmo2WP | 3 | 33 % |
| Propstack | 2 | 42 % |
| WP-ImmoMakler | 2 | 50 % |

Dazu je einmal FIO, casavi und ein IS24-Widget.

**Konsequenz:** Fünf Vendor-Adapter ersetzen rund die Hälfte der sonst nötigen
Einzelrezepte. Da diese Systeme ihr Markup zentral erzeugen, bricht ein Adapter
nicht bei einem Relaunch einer einzelnen Maklerseite — genau die Wartungslast,
die den ursprünglichen Ansatz gekippt hätte.

Die 50 % sind eine **Untergrenze**: erkannt wird nur, was Spuren im HTML
hinterlässt. Sites, deren Objektbereich per JavaScript nachgeladen wird, können
denselben Anbieter nutzen, ohne im statischen Markup aufzutauchen.

## Befund 2 — OpenImmo ist als Datenquelle nicht verfügbar

**Null von 24 Sites** liefern eine öffentlich abrufbare OpenImmo-XML. Geprüft
wurden `/openimmo.xml`, `/export/openimmo.xml`, `/wp-content/uploads/openimmo/`,
`/wp-content/uploads/immonex-openimmo/` und `/openimmo/`.

Der Standard ist im Markt präsent — drei Sites nutzen nachweislich OpenImmo2WP,
importieren die Dateien also — aber die XML liegt nicht im Web-Root. Die
Hoffnung auf strukturierte Volldaten als Hauptkanal ist damit **widerlegt**.
OpenImmo bleibt nur mittelbar wertvoll: als Fingerprint, der das erzeugte
Template vorhersagt.

## Befund 3 — Strukturierte Daten sind ein Nebenkanal, kein Fundament

Nur **3 Sites** liefern eindeutiges `RealEstateListing`
(`weichselgartner-immo.de`, `liebhardt-immobilien.de`, `jannikzimmer.com` —
letztere zusätzlich `Apartment`, `House`, `SingleFamilyResidence`).

Vier weitere zeigen `Product` oder `Place` — zu generisch, um daraus verlässlich
ein Objekt abzuleiten. Die zunächst gemessenen „7 Sites mit Immobilien-JSON-LD"
schrumpfen bei genauer Typprüfung auf 3.

Die Stufe ist billig und wird mitgenommen, trägt aber nur ~12 %.

## Befund 4 — Ein echter Objekt-Feed existiert, aber als Ausnahme

`rogers-immobilien.de` liefert über den WordPress-Standardfeed `/feed/` zehn
Objekte mit `/expose/`-URLs — ein vollständiger, kostenloser und sehr stabiler
Kanal.

Bei allen anderen WordPress-Sites enthält `/feed/` ausschließlich
SEO-Ratgeberartikel („Wie läuft ein Immobilienverkauf ab?", „Immobilie geerbt –
was tun?"). Ob Objekte im Feed landen, hängt davon ab, wie das Plugin den Custom
Post Type registriert.

**Methodischer Hinweis:** Ein erster, naiver Feed-Test (Preis oder m² irgendwo im
Feed-Body) meldete fünf Treffer — alle falsch, weil Ratgebertexte dieselben
Begriffe enthalten. Erst die Prüfung der einzelnen Einträge auf Objekt-URL-Muster
trennte den einen echten Treffer heraus. Derselbe Fehler in der Produktions-
Kaskade hätte vier Sites mit einem leeren Kanal als „erfasst" markiert.

## Befund 5 — Drei Sites blocken, und der User-Agent ist nicht die Ursache

`windisch-immobilien.de`, `aigner-immobilien.de` und `von-poll.com` antworten mit
HTTP 403 — **auch mit einem gewöhnlichen Chrome-User-Agent**. Der Block richtet
sich nicht gegen die ehrliche Bot-Kennung, sondern greift auf einer tieferen
Ebene (vermutlich TLS-/HTTP-Fingerprint der Python-Bibliothek).

Zwei Folgerungen:
1. Die Höflichkeits-Entscheidung (erkennbarer User-Agent) kostet keine Reichweite.
2. Für diese Sites ist ein **echter Browser** die Antwort — Playwright ist im
   Projekt bereits vorhanden. Es braucht keine Verschleierungstechnik, sondern
   eine echte Browser-Engine.

`zillerimmobilien.de` ist per DNS nicht auflösbar — vermutlich aufgegeben.

## Befund 6 — Typisierte Sitemaps sind der unterschätzte Kanal

Der erste Messdurchgang meldete für `loeger-immobilien.de` **null** Objekte. Die
Site hat tatsächlich **201** — sie liegen unter `/listing/…` und stehen
vollständig in einer Sitemap namens `listing-sitemap1.xml`.

Das ist ein verallgemeinerbares Muster: WordPress-SEO-Plugins erzeugen pro
Custom Post Type eine eigene Sitemap und **benennen sie nach dem Typ**. Der
Sitemap-Name verrät damit, wo die Objekte liegen — zuverlässiger, als
URL-Muster zu raten. Der Prober wertet jetzt Unter-Sitemaps aus, deren Name auf
`listing|immobilie|objekt|property|estate|expose` passt.

Ergebnis: 9 Sites liefern ihre Objekte vollständig über typisierte Sitemaps,
insgesamt wurden **4.225 Objekt-URLs** auffindbar.

## Befund 6b — Objektlinks strukturell erkennen schlägt jede Wortliste

`starnbergersee-immobilien.de` galt nach zwei Messdurchgängen als „tot". Die
Site hat **65 Objekte**, zuletzt aktualisiert am 03.08.2026. Zwei Gründe für den
Fehlschluss:

1. Die Angebotsseite heißt `/Angebote.htm` — die Dateiendung verhinderte, dass
   die Heuristik sie als Volltreffer erkannte.
2. Die Objektlinks lauten `index.php4?cmd=searchDetails&objq[cursor]=7` — ein
   Legacy-CMS ohne sprechende Pfade. **Keine Wortliste kann solche URLs
   erkennen**, weil in ihnen kein Vokabular vorkommt.

Daraus folgt der wichtigste methodische Schluss dieser Phase: Objektlinks werden
**strukturell** erkannt, nicht über Vokabular. Eine Angebotsseite verlinkt viele
Objekte nach *identischem Muster* und unterscheidet sie nur im Objektbezeichner,
während Navigationslinks einzeln und uneinheitlich sind. Der Prober gruppiert
interne Links nach ihrem normalisierten Muster (`/objekte/*`,
`/index.php4?cmd&cursor&alias`) und nimmt die größte gleichförmige Gruppe.

Das Verfahren ist sprach-, CMS- und layoutunabhängig — und damit robuster als
jede Musterliste, die man pflegen müsste.

**Wirkung:** Sites mit auffindbaren Objekten stiegen von 17 auf **22 von 25**.

## Befund 7 — Vier Messfehler, die das Bild verzerrt hatten

Alle drei fielen nur auf, weil Zwischenergebnisse gegen die Realität geprüft
wurden statt geglaubt. Sie sind hier dokumentiert, weil derselbe Fehler in der
Produktions-Kaskade jeweils stille Lücken erzeugt hätte:

1. **Feed-Test zu lasch.** Prüfung auf „Preis oder m² irgendwo im Feed" meldete
   5 Objekt-Feeds; alle waren SEO-Ratgeberfeeds. Korrektur: einzelne Einträge
   auf Objekt-URL-Muster prüfen. → 5 auf 1.
2. **JSON-LD zu großzügig.** `WebPage`, `Product` und `Place` wurden als
   Immobiliendaten gezählt. Korrektur: nur echte Immobilientypen. → 7 auf 3.
3. **Objekt-Link-Regex zu eng.** Das Muster verlangte direkt nach `objekt` einen
   Trenner und scheiterte am deutschen Plural (`/objekte/`) sowie am englischen
   Slug `/listing/`. Dadurch meldete der Prober für `riedel-immobilien.de` null
   Objekte, obwohl die Angebotsseite **260** verlinkt. Korrektur: Wortendungen
   zulassen, ein weiteres Pfadsegment verlangen, `listing` ergänzen.
   → von 12 auf 17 Sites mit auffindbaren Objekten, insgesamt 4.225 URLs.

4. **Vokabular-Abhängigkeit der Link-Erkennung.** Auch das reparierte Regex
   versagt bei Legacy-CMS ohne sprechende URLs (Befund 6b). Korrektur: Objekte
   strukturell über gleichförmige Link-Gruppen erkennen. → von 17 auf 22 Sites.

Die letzten beiden Korrekturen zusammen haben die gemessene Erfassbarkeit von
**48 % auf 88 %** gehoben. Beide Fehler ließen echte Objekte unsichtbar
erscheinen — im Betrieb hätte das Makler als „liefert nichts" markiert, die in
Wahrheit ihren gesamten Bestand online haben.

## Befund 8 — Die Angebotsseite lässt sich zuverlässig finden

**23 von 24** Angebotsübersichten wurden allein aus den Startseiten-Links per
Pfad- und Linktext-Heuristik lokalisiert. Der Schritt, den ich als fehleranfällig
eingeschätzt hatte, ist der robusteste der ganzen Kette — und braucht kein LLM.

---

## Konsequenzen für die Kaskade

Die Reihenfolge aus der Spec bleibt richtig, aber die Gewichte verschieben sich
deutlich:

| Stufe | geplant | gemessener Ertrag | Entscheidung |
|---|---|---|---|
| 1 — Feed / OpenImmo | tragend erhofft | **4 %** (1 Site), OpenImmo 0 % | **Behalten als billiger Vorabtest**, nicht als tragende Stufe. Ein `/feed/`-Abruf kostet nichts. |
| 2 — Vendor-Fingerprint | mittel erwartet | **50 %** | **Zur Hauptstufe machen.** Fünf Adapter: immonex, onOffice, OpenImmo2WP, Propstack, WP-ImmoMakler. |
| 3 — JSON-LD | mittel erwartet | 12 % | Mitnehmen, billig. Nur echte Immobilientypen zählen. |
| 4 — **typisierte Sitemap** | Fallback | **36 %** (9 Sites, vollständige Objektlisten) | **Aufwerten.** Sitemap-Name verrät den Objekt-Post-Type; liefert die Objektliste vollständig statt paginiert. |
| 4b — Detail-Links der Angebotsseite | mittel | ergänzend | Behalten als Fallback, wenn keine typisierte Sitemap existiert. |
| 5 — LLM-Rezept | letzte Stufe | Rest, ~25 % | Bleibt nötig, aber für deutlich weniger Sites als befürchtet — die Kostenschätzung sinkt entsprechend. |
| **neu** — Browser-Rendering | nicht geplant | 3 Sites blockiert + 2 JS-Shells | **Als Querschnittsfunktion ergänzen**, nicht als eigene Stufe: jede Stufe kann Playwright statt httpx nutzen. |

**Wichtigste Planungsänderung:** Der Bau beginnt mit den fünf Vendor-Adaptern,
nicht mit dem LLM-Rezept. Damit ist nach der ersten Ausbaustufe die Hälfte der
Makler erfasst — mit Code, der pro Anbieter einmal geschrieben und selten
gebrochen wird.

---

## Die fünf Referenz-Makler (vom Nutzer benannt)

| Site | Stufe | Objekte auffindbar | Bewertung |
|---|---|---:|---|
| `riedel-immobilien.de` | typisierte Sitemap | 3.483 | vollständig erfassbar (Zahl enthält Archiv/verkaufte Objekte — Filterung nötig) |
| `loeger-immobilien.de` | immonex + `listing`-Sitemap | 200 | vollständig erfassbar |
| `ubi-immobilien.de` | onOffice | 3 | erfassbar, kleiner Bestand |
| `starnbergersee-immobilien.de` | strukturelle Link-Gruppe | 16 (von 65 gesamt, paginiert) | erfassbar — Legacy-CMS mit Cursor-URLs; Paginierung muss durchlaufen werden |
| `locate-immobilien.com` | Propstack | 0 | **offen** — Objekte werden per Propstack-JS nachgeladen; auch Playwright-Rendering brachte sie nicht zum Vorschein. Braucht Analyse des Propstack-Endpunkts. |

Vier von fünf sind mit der gemessenen Kaskade erfassbar. Der Propstack-Fall
bleibt offen und ist der lohnendste nächste Schritt, weil er stellvertretend für
alle JS-geladenen Objektlisten steht.

Die Altquelle `starnberg_bader` scheiterte übrigens nicht am Bot-Schutz, sondern
schlicht an der veralteten Domain und den falschen Selektoren — die Objekte
waren die ganze Zeit da.

## Belastbarkeit dieses Ergebnisses

- **Stichprobe:** 28 Sites, per Websuche über die Orte des Suchgebiets gewonnen.
  Nicht zufällig gezogen — größere und SEO-aktive Makler sind überrepräsentiert.
  Der Long Tail kleiner Makler dürfte technisch einfacher gebaut sein (mehr
  statisches HTML, weniger Vendor-Systeme).
- **Nur statisches HTML gemessen.** Alle Zahlen zu Detail-Links und Preisen sind
  Untergrenzen; JS-gerenderte Bereiche wurden nicht erfasst.
- **Fingerprint-Liste ist nicht erschöpfend.** Weitere Systeme (FlowFact,
  JustImmo, immoware, Estatik) waren in der Stichprobe nicht nachweisbar,
  existieren im Markt aber.
