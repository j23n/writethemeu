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
