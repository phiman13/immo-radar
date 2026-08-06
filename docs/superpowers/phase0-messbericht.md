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
| Sites geprüft | 39 |
| erreichbar | 35 |
| aktiv geblockt (HTTP 403) | 3 |
| tot / DNS-Fehler | 1 |
| **Vendor-Fingerprint erkannt** | **21 von 35 (60 %)** |
| **Sites mit ≥ 3 auffindbaren Objekt-URLs** | **31 von 35 (89 %)** |
| Objekt-URLs insgesamt gefunden | **4.560** |
| Sites ohne jede auffindbare Objekt-URL | 4 von 35 |
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
| onOffice | 6 | |
| immonex Kickstart | 5 | |
| OpenImmo2WP | 3 | |
| WP-ImmoMakler | 3 | |
| Propstack | 2 | |
| **cursor-cms** (Legacy-Makler-CMS) | 2 | |
| TYPO3-OpenImmo, immobilie1-Widget, FIO, casavi, IS24-Widget | je 1 | **21 von 35 (60 %)** |

Mehrere Fingerprints kamen erst durch nachgereichte Referenz-URLs hinzu:

- **`cursor-cms`** — ein Legacy-Makler-CMS mit URLs der Form
  `index.php4?cmd=searchDetails&objq[cursor]=N`. Es trägt keine erkennbaren
  Asset-Pfade; der Fingerprint läuft deshalb über das **URL-Schema**. Zwei Sites
  der Stichprobe nutzen es identisch — ein Adapter deckt beide ab.
- **`typo3-openimmo`** — TYPO3 mit OpenImmo-Extension (`tx_openimmo`).
- **`immobilie1-widget`** — ein fremdgehostetes Objekt-Widget (Livewire), das
  Objekte auf einer *anderen* Domain hält als die Makler-Site selbst
  (`imothek.de` bindet `immobilie1.de` per `<script src>` ein). Wichtige
  Lehre dazu in Befund 9.

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

Zwei weitere Site-Bauformen erzwangen Nachbesserungen an diesem Verfahren:

- **Flache Root-Slugs.** Manche CMS legen Objekte direkt im Root ab
  (`/moderne-gartenwohnung-in-ruhiger-wohnlage-von-weilheim/`). Damit bildet
  jedes Objekt seine *eigene* Gruppe und die Präfix-Logik läuft leer — die
  Navigation gewinnt. Zusätzliches Signal: Objekt-Slugs sind lang und
  mehrgliedrig (≥ 25 Zeichen, ≥ 4 Bindestriche), Navigationsslugs kurz.
- **Formularlinks pro Objekt.** Eine Site verlinkt pro Objekt einen
  „Anfragen"-Button; diese Gruppe war größer als die der Detailseiten und
  gewann. Links mit `anfrage|request|merkliste|print|cHash` werden verworfen.

**Eine Nachbesserung ging zunächst schief und ist als Warnung dokumentiert:**
Um Navigation auszublenden, entfernte der Prober `<nav>`, `<header>` und
`<footer>` vor der Analyse. Das kostete vier Sites ihre Objekte — ein Theme
verschachtelt die Objektliste innerhalb eines `<header>`, wodurch von 119 Links
noch 3 übrig blieben. Jetzt wird nur `<footer>` entfernt; die Navigation fällt
ohnehin durch die Slug-Länge heraus.

**Wirkung:** Sites mit auffindbaren Objekten stiegen von 12 über 17 und 22 auf
**24 von 27 (89 %)**.

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

## Befund 9 — Weitere Bauformen, weitere Nachbesserungen

Zwei weitere Runden nachgereichter Referenz-URLs deckten vier zusätzliche
Muster auf:

- **Formularlinks können die Objektgruppe zahlenmäßig schlagen.**
  `see-immo.de` verlinkt pro Objekt einen „Anfragen"-Button; diese Gruppe war
  genauso groß wie die der echten Detailseiten und gewann zufällig. Fix:
  Links mit `anfrage|request|merkliste|print|…` werden vor der Gruppierung
  verworfen.
- **Kategorie- und Objektseiten können auf derselben Ebene liegen.**
  `i-m-living.de` legt `/immobilien/neubau/` neben `/immobilien/<objekt-slug>/`
  — beide fallen in dieselbe Präfix-Gruppe. Fix: jedes Gruppenmitglied wird
  zusätzlich einzeln geprüft (`is_object_like`) — kurze, aus einer
  Stichwortliste bekannte Navigationssegmente fliegen auch innerhalb einer
  sonst gültigen Gruppe heraus.
- **Der Objektbezeichner kann im Query-String stecken, nicht im Pfad.**
  `starnberger-immobilien.de` (TYPO3 mit `haus5`-Extension) codiert das Objekt
  als `tx_haus5_haus5[haus]=124`. Ursächlich war ein zweiter, folgenschwerer
  Bug: Der Formularfilter enthielt `cHash` — TYPO3s **generischer**
  Cache-Busting-Parameter, der auf praktisch jedem Link steht, auch auf
  echten Objektseiten. Der Filter hatte damit die Objekte selbst entfernt.
  Entfernt; stattdessen erkennt `is_object_like` Query-Parameter wie
  `cursor=`, `haus=`, `wohnung=` mit numerischem Wert als Objektsignal.
- **Fingerprints können auf reinen Outbound-Links falsch anschlagen.**
  Der erste `immobilie1-widget`-Fingerprint matchte jede Erwähnung von
  `immobilie1.de` — und traf damit auch `dahlercompany.com`, das die Domain
  nur als `rel="nofollow"`-Partnerlink im Footer verlinkt, ohne jede
  technische Anbindung. Fix: nur `src="https://immobilie1.de/…"` zählt
  (Script-/Iframe-Einbettung), kein `href=`.

Eine Domain-Verwechslung kam ebenfalls vor: Für die vom Nutzer genannte URL
`immobilien.vr-starnberg-zugspitze.de` (Subdomain der VR-Bank für Immobilien)
war in der Stichprobe versehentlich nur `vr-starnberg-zugspitze.de` (die
Bank-Hauptseite) eingetragen — eine völlig andere Seite. Nach Korrektur:
77 Objekte, drei Vendor-Fingerprints gleichzeitig (WP-ImmoMakler, onOffice,
Propstack — vermutlich mehrere Regionalableger derselben Bankengruppe mit
unterschiedlicher Technik unter einer Domain).

**Wirkung über alle Nachbesserungsrunden:** Erfassbarkeit stieg von 48 % über
88 % auf **89 % bei 35 erreichbaren Sites**, 4.560 Objekt-URLs gesamt. Von 21
einzeln vom Nutzer genannten Referenz-Maklern sind 18 erfassbar.

## Befund 10 — Die Angebotsseite lässt sich zuverlässig finden

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
| 4 — **typisierte Sitemap** | Fallback | ~11 % (4 Sites, vollständige Objektlisten) | **Aufwerten.** Sitemap-Name verrät den Objekt-Post-Type; liefert die Objektliste vollständig statt paginiert. |
| 4b — strukturelle Detail-Links | mittel | **~26 %** (9 Sites, größter Einzelbeitrag nach Vendor) | Zentrale Stufe, wenn kein Vendor-Fingerprint und keine typisierte Sitemap greifen — Objekte über gleichförmige Link-Gruppen/Query-Signaturen erkannt, unabhängig von Sprache/CMS. |
| 5 — LLM-Rezept | letzte Stufe | Rest, ~11 % (4 Sites ohne Objekte) | Bleibt nötig, aber für deutlich weniger Sites als befürchtet — die Kostenschätzung sinkt entsprechend. |
| **neu** — Browser-Rendering | nicht geplant | 3 Sites blockiert + 2 JS-Shells | **Als Querschnittsfunktion ergänzen**, nicht als eigene Stufe: jede Stufe kann Playwright statt httpx nutzen. |

**Wichtigste Planungsänderung:** Der Bau beginnt mit den fünf Vendor-Adaptern,
nicht mit dem LLM-Rezept. Damit ist nach der ersten Ausbaustufe die Hälfte der
Makler erfasst — mit Code, der pro Anbieter einmal geschrieben und selten
gebrochen wird.

---

## Die 21 Referenz-Makler (vom Nutzer benannt, drei Runden)

| Site | Stufe | Objekte | Vendor |
|---|---|---:|---|
| `riedel-immobilien.de` | typisierte Sitemap | 3.489 | — |
| `loeger-immobilien.de` | Vendor | 200 | immonex, OpenImmo2WP |
| `sedlmayr-immo.de` | typisierte Sitemap | 79 | — |
| `immobilien.vr-starnberg-zugspitze.de` | Vendor | 77 | WP-ImmoMakler, onOffice, Propstack |
| `schlossberger-immobilien.de` | Vendor | 59 | immonex, OpenImmo2WP |
| `kpcimmobilien.de` | Vendor | 50 | WP-ImmoMakler |
| `i-m-living.de` | Detail-Links | 46 | — |
| `bpl-immobilien.de` | typisierte Sitemap | 33 | — |
| `immobilien-sis.com` | typisierte Sitemap | 33 | — |
| `starnberger-immobilien.de` | Detail-Links | 19 | — |
| `see-immo.de` | Feed | 20 | TYPO3-OpenImmo |
| `starnbergersee-immobilien.de` | Vendor | 16 | cursor-cms |
| `remax-starnberg.com` | Vendor | 13 | cursor-cms |
| `ubi-immobilien.de` | Vendor | 12 | onOffice |
| `heidinger-immobilien.de` | Root-Slugs | 10 | — |
| `funer-immobilien-starnberg.de` | Detail-Links | 8 | — |
| `nikki-livings.de` | Detail-Links | 3 | — |
| `dahlercompany.com` | Detail-Links | 3 | — |
| `locate-immobilien.com` | — | **0** | Propstack |
| `imothek.de` | — | **0** | immobilie1-widget (fremdgehostet) |
| `aigner-immobilien.de` | — | **0** | blockiert (403, braucht Browser) |

**18 von 21 sind erfassbar.** Jede dieser URLs hat mindestens eine Verbesserung
ausgelöst — die Referenzen des Nutzers waren der mit Abstand wirksamste Testfall
der ganzen Phase, wirksamer als die ursprünglich per Websuche zusammengestellte
Stichprobe.

<details>
<summary>Frühere Zwischenstände dieser Tabelle</summary>

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

</details>

## Belastbarkeit dieses Ergebnisses

- **Stichprobe:** 39 Sites — 18 per Websuche über die Orte des Suchgebiets
  gewonnen, 21 vom Nutzer als real relevante Referenz-Makler benannt. Nicht
  zufällig gezogen — größere und SEO-aktive Makler sind überrepräsentiert. Der
  Long Tail kleiner Makler dürfte technisch einfacher gebaut sein (mehr
  statisches HTML, weniger Vendor-Systeme).
- **Nur statisches HTML gemessen.** Alle Zahlen zu Detail-Links und Preisen sind
  Untergrenzen; JS-gerenderte Bereiche wurden nicht erfasst — der `locate`- und
  `imothek`-Fall (Propstack bzw. fremdgehostetes Widget) zeigen, dass das real
  vorkommt und mit reinem `httpx` nicht lösbar ist.
- **Fingerprint-Liste ist nicht erschöpfend.** Weitere Systeme (FlowFact,
  JustImmo, immoware, Estatik) waren in der Stichprobe nicht nachweisbar,
  existieren im Markt aber.
- **Die Objekt-Erkennung selbst wurde iterativ gehärtet, nicht vorab bewiesen.**
  Fünf verschiedene Bauformen (deutsche/englische Slugs, Legacy-CMS mit
  Query-Parametern, flache Root-Slugs, Formularlinks, Kategorie-Vermischung)
  brauchten je eine eigene Korrektur, gefunden ausschließlich durch echte Sites,
  die die vorherige Annahme widerlegten. Eine 22. oder 23. Referenz-URL könnte
  ein weiteres Muster aufdecken, das die aktuelle Logik noch nicht abdeckt.
