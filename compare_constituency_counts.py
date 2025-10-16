#!/usr/bin/env python
"""
Compare constituency counts between GeoJSON config and Abgeordnetenwatch API.
"""

# From sync_wahlkreise.py STATE_SOURCES
GEOJSON_COUNTS = {
    'BW': 70,
    'BY': 91,
    'BE': 78,
    'HB': None,  # "Unknown" in config
    'NI': 87,
    'NW': 128,
    'ST': 41,
    'SH': 35,
    'TH': 44,
}

# From our API check
API_COUNTS = {
    'BW': 70,   # Baden-Württemberg
    'BY': 91,   # Bayern
    'BE': 78,   # Berlin
    'HB': 2,    # Bremen
    'NI': 87,   # Niedersachsen
    'NW': 128,  # Nordrhein-Westfalen
    'ST': 41,   # Sachsen-Anhalt
    'SH': 35,   # Schleswig-Holstein
    'TH': 44,   # Thüringen
}

STATE_NAMES = {
    'BW': 'Baden-Württemberg',
    'BY': 'Bayern',
    'BE': 'Berlin',
    'HB': 'Bremen',
    'NI': 'Niedersachsen',
    'NW': 'Nordrhein-Westfalen',
    'ST': 'Sachsen-Anhalt',
    'SH': 'Schleswig-Holstein',
    'TH': 'Thüringen',
}

print("Comparison: GeoJSON Config vs Abgeordnetenwatch API")
print("="*70)
print(f"{'Code':5s} {'State':25s} {'GeoJSON':>10s} {'API':>10s} {'Match':>10s}")
print("="*70)

all_match = True
for code in sorted(GEOJSON_COUNTS.keys()):
    geojson_count = GEOJSON_COUNTS[code]
    api_count = API_COUNTS.get(code, 0)

    if geojson_count is None:
        match_str = "Unknown"
        geojson_str = "Unknown"
    elif geojson_count == api_count:
        match_str = "✓"
        geojson_str = str(geojson_count)
    else:
        match_str = "✗ MISMATCH"
        geojson_str = str(geojson_count)
        all_match = False

    print(f"{code:5s} {STATE_NAMES[code]:25s} {geojson_str:>10s} {api_count:>10d} {match_str:>10s}")

print("="*70)

geojson_total = sum(c for c in GEOJSON_COUNTS.values() if c is not None)
api_total = sum(API_COUNTS.values())

print(f"{'TOTAL':5s} {'':<25s} {geojson_total:>10d} {api_total:>10d}")
print()

if all_match:
    print("✓ All counts match!")
else:
    print("✗ Some counts don't match - need to investigate")

print("\nNotes:")
print("- HB (Bremen): GeoJSON config says 'Unknown', API has 2 districts")
print("- We have 9 GeoJSON files total")
print("- Missing from our GeoJSON: HE, HH, MV, RP, SL, SN, BB (7 states)")
