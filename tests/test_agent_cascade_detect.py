"""Tests für app.agent_cascade_detect — reine, I/O-freie Erkennungsbausteine
der Extraktions-Kaskade, promoted aus Phase 0 (scripts/probe_agent_sites.py)."""

from __future__ import annotations

from app.agent_cascade_detect import (
    content_signals,
    detect_structured,
    detect_vendors,
    find_detail_links,
    is_object_like,
    link_shape,
)


def test_link_shape_groups_object_slugs_by_prefix():
    assert link_shape("https://x.de/objekte/haus-am-see") == "/objekte/*"
    assert link_shape("https://x.de/objekte/wohnung-tutzing") == "/objekte/*"


def test_link_shape_normalizes_query_keys_not_values():
    a = link_shape("https://x.de/index.php4?cmd=searchDetails&cursor=7")
    b = link_shape("https://x.de/index.php4?cmd=searchDetails&cursor=99")
    assert a == b


def test_is_object_like_rejects_known_nav_segment():
    assert is_object_like("https://x.de/immobilien/kontakt") is False


def test_is_object_like_accepts_long_hyphenated_slug():
    assert is_object_like("https://x.de/immobilien/moderne-gartenwohnung-tutzing") is True


def test_is_object_like_accepts_legacy_query_id():
    assert is_object_like("https://x.de/index.php4?cmd=searchDetails&objq[cursor]=7") is True


def test_find_detail_links_groups_object_pages_and_skips_nav():
    html = """
    <html><body>
      <a href="/immobilien/moderne-villa-am-see-tutzing">A</a>
      <a href="/immobilien/gemuetliche-wohnung-starnberg">B</a>
      <a href="/immobilien/grosszuegiges-haus-poecking">C</a>
      <a href="/immobilien/kontakt">Kontakt</a>
      <a href="/immobilien/team">Team</a>
    </body></html>
    """
    n, sample = find_detail_links(html, "https://x.de/immobilien/")
    assert n == 3
    assert all("/immobilien/" in u for u in sample)
    assert not any(u.endswith(("/kontakt", "/team")) for u in sample)


def test_find_detail_links_finds_flat_root_slugs():
    html = """
    <html><body>
      <a href="/moderne-gartenwohnung-in-ruhiger-wohnlage-tutzing">A</a>
      <a href="/grosszuegiges-einfamilienhaus-mit-seeblick-poecking">B</a>
      <a href="/exklusive-villa-direkt-am-starnberger-see">C</a>
      <a href="/kontakt">Kontakt</a>
    </body></html>
    """
    n, sample = find_detail_links(html, "https://x.de/")
    assert n == 3
    assert len(sample) == 3


def test_find_detail_links_returns_empty_below_group_threshold():
    html = '<html><body><a href="/immobilien/einzelnes-objekt-tutzing">A</a></body></html>'
    n, sample = find_detail_links(html, "https://x.de/immobilien/")
    assert n == 0
    assert sample == []


def test_detect_vendors_matches_onoffice_fingerprint():
    blob = '<script src="https://cdn.example.de/onoffice-for-wp-websites/app.js"></script>'
    assert "onoffice" in detect_vendors(blob)


def test_detect_vendors_returns_empty_for_unknown_markup():
    assert detect_vendors("<html><body>Nichts Besonderes</body></html>") == []


def test_detect_structured_extracts_immo_jsonld_type():
    html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Testobjekt"}
    </script>
    """
    result = detect_structured(html)
    assert "RealEstateListing" in result["jsonld_types"]


def test_detect_structured_ignores_generic_webpage_type():
    html = '<script type="application/ld+json">{"@type": "WebPage"}</script>'
    result = detect_structured(html)
    assert result["jsonld_types"] == ["WebPage"]


def test_content_signals_counts_prices_and_areas():
    html = "Preis: 450.000 € — Wohnfläche: 120 m² — Zweites Objekt: 89.000 EUR, 45 m²"
    sig = content_signals(html)
    assert sig["prices"] == 2
    assert sig["areas"] == 2
