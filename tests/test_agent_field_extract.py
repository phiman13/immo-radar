"""Tests für app.agent_field_extract — genereischer, I/O-freier
Feld-Extraktor für Makler-Detailseiten (Phase 2b)."""

from __future__ import annotations

from app.agent_field_extract import (
    extract_fields,
    extract_plz_city,
    extract_price,
    extract_property_type,
    extract_qm,
    extract_rooms,
    extract_title,
    fields_from_jsonld,
    merge_fields,
    parse_feed_items,
)
from app.models import PropertyType


def test_extract_price_parses_thousands_separator():
    assert extract_price("Kaufpreis: 450.000 €") == 450000


def test_extract_price_returns_none_without_match():
    assert extract_price("Preis auf Anfrage") is None


def test_extract_price_prefers_labeled_kaufpreis_over_earlier_hausgeld():
    text = "Hausgeld: 3.500 € Kaufpreis: 650.000 €"
    assert extract_price(text) == 650000


def test_extract_price_falls_back_to_unlabeled_price_when_no_label_present():
    assert extract_price("Objektbeschreibung: sonnige Wohnung, VB 380.000 €") == 380000


def test_extract_qm_parses_comma_decimal():
    assert extract_qm("Wohnfläche 120,5 m²") == 120.5


def test_extract_rooms_parses_zi_abbreviation():
    assert extract_rooms("3,5 Zi. Wohnung") == 3.5


def test_extract_rooms_parses_zimmer_word():
    assert extract_rooms("4 Zimmer Haus") == 4.0


def test_extract_plz_city_finds_plz_and_ort():
    assert extract_plz_city("Objekt in 82327 Tutzing am See") == ("82327", "Tutzing")


def test_extract_plz_city_returns_none_none_without_plz():
    assert extract_plz_city("Schönes Haus mit Garten") == (None, None)


def test_extract_plz_city_does_not_swallow_a_following_capitalized_word():
    """Regression: auf einer ganzen Detailseite (statt eines isolierten
    Kartentext-Snippets) folgt auf PLZ+Ort oft direkt ein weiteres,
    grossgeschriebenes Wort (deutsche Substantivgrossschreibung) -- z.B.
    "82327 Tutzing Immobilie" oder "82346 Andechs Flächenaufstellung". Der
    frühere "optional zweites Grossbuchstaben-Wort"-Teil der Regex nahm das
    fälschlich als Teil des Ortsnamens mit (real beobachtet in Produktion,
    siehe docs/STATUS.md 2026-08-12/14)."""
    assert extract_plz_city("82327 Tutzing Immobilie") == ("82327", "Tutzing")
    assert extract_plz_city("82319 Starnberg Etage") == ("82319", "Starnberg")
    assert extract_plz_city("82346 Andechs Flächenaufstellung") == ("82346", "Andechs")


def test_extract_property_type_detects_doppelhaushaelfte_before_haus():
    assert extract_property_type("Gepflegte Doppelhaushälfte") == PropertyType.DOPPELHAUSHAELFTE


def test_extract_property_type_falls_back_to_unknown():
    assert extract_property_type("Gewerbeobjekt") == PropertyType.UNKNOWN


def test_extract_title_prefers_h1():
    html = "<html><body><h1>Villa am Starnberger See</h1></body></html>"
    assert extract_title(html) == "Villa am Starnberger See"


def test_extract_title_falls_back_to_og_title_without_h1():
    html = '<html><head><meta property="og:title" content="Traumhaus Tutzing"></head></html>'
    assert extract_title(html) == "Traumhaus Tutzing"


def test_extract_title_falls_back_to_text_snippet():
    html = "<html><body><p>Kein Heading hier</p></body></html>"
    text = "Moderne Villa mit Seeblick und grossem Garten in Tutzing direkt am See"
    title = extract_title(html, text)
    assert "Villa" in title


def test_extract_title_returns_placeholder_when_nothing_found():
    assert extract_title("<html><body></body></html>", "") == "Makler-Objekt"


def test_extract_title_decodes_html_entities_and_normalizes_whitespace_from_h1():
    """Regression: reale Makler-Templates liefern <h1>-Inhalte mit
    HTML-Entities (&#8211; als Gedankenstrich, &amp;) und eingebetteten
    Zeilenumbrüchen -- beides landete bisher roh im Titel (real beobachtet
    in Produktion, siehe docs/STATUS.md 2026-08-12/14)."""
    html_source = "<html><body><h1>VERKAUFT &#8211;\r\nTRAUMBLICK &amp; RUHE</h1></body></html>"
    assert extract_title(html_source) == "VERKAUFT – TRAUMBLICK & RUHE"


def test_extract_title_decodes_html_entities_from_og_title():
    html_source = (
        '<html><head><meta property="og:title" content="Haus &amp; Garten in Tutzing"></head></html>'
    )
    assert extract_title(html_source) == "Haus & Garten in Tutzing"


def test_extract_fields_bundles_all_extractions():
    html = "<html><body><h1>Haus in Tutzing</h1></body></html>"
    text = "Haus in Tutzing 82327 Tutzing, Kaufpreis: 450.000 €, 140 m², 5 Zimmer"
    fields = extract_fields(html, text)
    assert fields["title"] == "Haus in Tutzing"
    assert fields["price_eur"] == 450000
    assert fields["qm"] == 140.0
    assert fields["rooms"] == 5.0
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"
    assert fields["property_type"] == PropertyType.HAUS
    assert "address" not in fields


def test_fields_from_jsonld_reads_offers_price_and_floor_size():
    node = {
        "@type": "RealEstateListing",
        "name": "Villa am See",
        "url": "https://x.de/objekte/villa-am-see",
        "offers": {"price": 1200000},
        "floorSize": {"value": 180},
        "numberOfRooms": 6,
        "address": {"postalCode": "82327", "addressLocality": "Tutzing"},
    }
    fields = fields_from_jsonld(node)
    assert fields["title"] == "Villa am See"
    assert fields["url"] == "https://x.de/objekte/villa-am-see"
    assert fields["price_eur"] == 1200000
    assert fields["qm"] == 180.0
    assert fields["rooms"] == 6.0
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"


def test_fields_from_jsonld_handles_missing_offers_gracefully():
    node = {"@type": "Apartment", "name": "ETW"}
    fields = fields_from_jsonld(node)
    assert fields["price_eur"] is None
    assert fields["qm"] is None
    assert fields["rooms"] is None
    assert fields["plz"] is None
    assert fields["city"] is None


def test_fields_from_jsonld_parses_freetext_address_string():
    node = {"@type": "House", "name": "Haus", "address": "82327 Tutzing"}
    fields = fields_from_jsonld(node)
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"


def test_fields_from_jsonld_ignores_malformed_name_list_instead_of_raising():
    """Finding 2a: manche Generatoren liefern "name" als Liste statt String —
    RawListing.title ist ein pydantic-str-Feld ohne automatische Koerzierung,
    ein ungeprüfter Wert würde die Konstruktion crashen und den gesamten
    Harvest-Lauf des Agents stillschweigend verwerfen."""
    node = {
        "@type": "RealEstateListing",
        "name": ["Villa", "am See"],
        "url": "https://x.de/objekte/villa-am-see",
        "offers": {"price": 1200000},
    }
    fields = fields_from_jsonld(node)
    assert fields["title"] is None
    assert fields["url"] == "https://x.de/objekte/villa-am-see"
    assert fields["price_eur"] == 1200000


def test_fields_from_jsonld_ignores_malformed_url_object_instead_of_raising():
    node = {
        "@type": "RealEstateListing",
        "name": "Villa am See",
        "url": {"@id": "https://x.de/objekte/villa-am-see"},
        "offers": {"price": 1200000},
    }
    fields = fields_from_jsonld(node)
    assert fields["url"] is None
    assert fields["title"] == "Villa am See"
    assert fields["price_eur"] == 1200000


def test_fields_from_jsonld_coerces_numeric_postal_code():
    node = {
        "@type": "House",
        "name": "Haus",
        "address": {"postalCode": 82327, "addressLocality": "Tutzing"},
    }
    fields = fields_from_jsonld(node)
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"


def test_merge_fields_prefers_primary_and_fills_gaps():
    primary = {"title": "Villa am See", "price_eur": None, "qm": 180.0}
    fallback = {"title": "Fallback-Titel", "price_eur": 999000, "qm": 200.0}
    merged = merge_fields(primary, fallback)
    assert merged["title"] == "Villa am See"
    assert merged["price_eur"] == 999000
    assert merged["qm"] == 180.0


def test_parse_feed_items_extracts_link_title_description():
    feed = """
    <rss><channel>
      <item>
        <title>Haus in Tutzing, 450.000 €</title>
        <link>https://x.de/objekte/haus-tutzing</link>
        <description>140 m², 5 Zimmer</description>
      </item>
    </channel></rss>
    """
    items = parse_feed_items(feed)
    assert len(items) == 1
    assert items[0]["link"] == "https://x.de/objekte/haus-tutzing"
    assert items[0]["title"] == "Haus in Tutzing, 450.000 €"
    assert items[0]["description"] == "140 m², 5 Zimmer"


def test_parse_feed_items_unwraps_cdata_title():
    feed = """
    <feed>
      <entry>
        <title><![CDATA[Villa & Seeblick]]></title>
        <link href="https://x.de/objekte/villa-seeblick"/>
      </entry>
    </feed>
    """
    items = parse_feed_items(feed)
    assert items[0]["title"] == "Villa & Seeblick"
    assert items[0]["link"] == "https://x.de/objekte/villa-seeblick"


def test_parse_feed_items_skips_entries_without_link():
    feed = "<rss><channel><item><title>Kein Link</title></item></channel></rss>"
    assert parse_feed_items(feed) == []


def test_parse_feed_items_decodes_html_entities_in_title():
    feed = """
    <rss><channel>
      <item>
        <title>Villa &amp; Seeblick</title>
        <link>https://x.de/objekte/villa</link>
      </item>
    </channel></rss>
    """
    items = parse_feed_items(feed)
    assert items[0]["title"] == "Villa & Seeblick"


def test_parse_feed_items_decodes_html_entities_in_description():
    feed = """
    <rss><channel>
      <item>
        <title>Haus</title>
        <link>https://x.de/objekte/haus</link>
        <description>120 m&#178; mit B&#228;umen</description>
      </item>
    </channel></rss>
    """
    items = parse_feed_items(feed)
    assert items[0]["description"] == "120 m² mit Bäumen"
