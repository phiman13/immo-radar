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
