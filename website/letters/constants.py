"""Static constants and helpers for geographic normalization."""

from __future__ import annotations

from typing import Optional

GERMAN_STATE_ALIASES = {
    'Baden-Württemberg': ['Baden-Württemberg', 'BW'],
    'Bayern': ['Bayern', 'Bavaria', 'BY'],
    'Berlin': ['Berlin', 'BE'],
    'Brandenburg': ['Brandenburg', 'BB'],
    'Bremen': ['Bremen', 'HB'],
    'Hamburg': ['Hamburg', 'HH'],
    'Hessen': ['Hessen', 'Hesse', 'HE'],
    'Mecklenburg-Vorpommern': ['Mecklenburg-Vorpommern', 'MV'],
    'Niedersachsen': ['Niedersachsen', 'Lower Saxony', 'NI'],
    'Nordrhein-Westfalen': ['Nordrhein-Westfalen', 'North Rhine-Westphalia', 'NRW', 'NW'],
    'Rheinland-Pfalz': ['Rheinland-Pfalz', 'Rhineland-Palatinate', 'RP'],
    'Saarland': ['Saarland', 'SL'],
    'Sachsen': ['Sachsen', 'Saxony', 'SN'],
    'Sachsen-Anhalt': ['Sachsen-Anhalt', 'Saxony-Anhalt', 'ST'],
    'Schleswig-Holstein': ['Schleswig-Holstein', 'SH'],
    'Thüringen': ['Thüringen', 'Thuringia', 'TH'],
}

PARTY_ALIASES = {
    'spd': 'SPD',
    'sozialdemokratische partei deutschlands': 'SPD',
    'cdu': 'CDU',
    'csu': 'CSU',
    'cdu/csu': 'CDU/CSU',
    'afd': 'AfD',
    'alternative für deutschland': 'AfD',
    'fdp': 'FDP',
    'freie demokratische partei': 'FDP',
    'bsw': 'BSW',
    'bsw.': 'BSW',
    'freiebürger': 'BSW',
    'bündnis 90/die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'bündnis90/die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'bündnis 90 / die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'bündnis90 / die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'bündnis 90/ die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'bündnis 90/ die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'gruene': 'BÜNDNIS 90/DIE GRÜNEN',
    'grüne': 'BÜNDNIS 90/DIE GRÜNEN',
    'die grünen': 'BÜNDNIS 90/DIE GRÜNEN',
    'grüne/bündnis 90': 'BÜNDNIS 90/DIE GRÜNEN',
    'grüne (bündnis 90/ die grünen)': 'BÜNDNIS 90/DIE GRÜNEN',
    'die linke': 'DIE LINKE',
    'linke': 'DIE LINKE',
    'the left': 'DIE LINKE',
    'linke.': 'DIE LINKE',
    'fraktionslos': 'Fraktionslos',
    'freiewähler': 'FREIE WÄHLER',
    'freie wähler': 'FREIE WÄHLER',
    'freie wählergemeinschaft': 'FREIE WÄHLER',
    'freie wähler / fw': 'FREIE WÄHLER',
    'fw': 'FREIE WÄHLER',
    'grüne/efa': 'Grüne/EFA',
    'greens/efa': 'Grüne/EFA',
    's&d': 'S&D',
    'evp': 'EVP',
    'renew': 'Renew',
    'renew europe': 'Renew',
    'bündnis deutschland': 'Bündnis Deutschland',
    'bündnis deutschland.': 'Bündnis Deutschland',
}


def normalize_german_state(state: Optional[str]) -> Optional[str]:
    """Return canonical German state name if known."""
    if not state:
        return None

    state_clean = state.strip()
    if not state_clean:
        return None

    lower_value = state_clean.lower()

    for canonical, variants in GERMAN_STATE_ALIASES.items():
        if lower_value == canonical.lower():
            return canonical
        for variant in variants:
            if lower_value == variant.lower():
                return canonical

    return state_clean


def normalize_party_name(party: Optional[str]) -> Optional[str]:
    """Return canonical party label when known."""
    if not party:
        return party

    cleaned = party.strip()
    if not cleaned:
        return cleaned

    canonical = PARTY_ALIASES.get(cleaned.lower())
    return canonical or cleaned
