from __future__ import annotations

import re

RISK_PATTERNS: dict[str, list[str]] = {
    "erbbaurecht": [r"\berbbau", r"\berbpacht"],
    "denkmalschutz": [r"\bdenkmal", r"\bdenkmalgesch"],
    "sanierungsstau": [
        r"sanierungsbed",
        r"modernisierungsbed",
        r"renovierungsbed",
        r"sanierungsstau",
        r"unsaniert",
        r"\bin die jahre gekommen",
    ],
    "hochwasserrisiko": [r"hochwasser", r"\bHQ100\b"],
    "schimmel": [r"\bschimmel"],
    "asbest": [r"\basbest"],
    "altlasten": [r"\baltlast"],
    "nicht_unterkellert": [r"nicht unterkellert", r"keller fehlt"],
    "rueckstand_hausgeld": [r"r[üu]ckst[äa]nde.*hausgeld", r"nachzahlung.*hausgeld"],
    "wegerecht": [r"\bwegerecht", r"\bgrunddienstbarkeit"],
}

POSITIVE_PATTERNS: dict[str, list[str]] = {
    "kernsaniert": [r"\bkernsaniert", r"vollst[äa]ndig saniert"],
    "neubau": [r"\bneubau", r"erstbezug"],
    "seezugang": [r"seezugang", r"direkt am see", r"steg "],
    "seeblick": [r"seeblick", r"blick auf den see"],
    "bergblick": [r"bergblick", r"alpenblick", r"zugspitzblick"],
    "balkon": [r"\bbalkon"],
    "garten": [r"\bgarten\b"],
    "lift": [r"\blift\b", r"aufzug"],
    "stellplatz": [r"stellplatz", r"tiefgarage", r"\bgarage\b"],
}


def extract_flags(text: str | None) -> tuple[list[str], list[str]]:
    if not text:
        return [], []
    t = text.lower()
    risks = [k for k, pats in RISK_PATTERNS.items() if any(re.search(p, t) for p in pats)]
    positives = [k for k, pats in POSITIVE_PATTERNS.items() if any(re.search(p, t) for p in pats)]
    return risks, positives
