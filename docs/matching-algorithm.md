# Constituency Matching Algorithm

## Overview

WriteThem.eu uses a two-stage process to match users to their correct Bundestag constituency:

1. **Address Geocoding**: Convert user's address to latitude/longitude coordinates
2. **Point-in-Polygon Lookup**: Find which constituency polygon contains those coordinates

## Stage 1: Address Geocoding

We use OpenStreetMap's Nominatim API to convert addresses to coordinates.

### Process:
1. User provides: Street, Postal Code, City
2. System checks cache (GeocodeCache table) for previous results
3. If not cached, query Nominatim API with rate limiting (1 req/sec)
4. Cache result (success or failure) to minimize API calls
5. Return (latitude, longitude) or None

### Fallback:
If geocoding fails or user only provides postal code, fall back to PLZ prefix heuristic (maps first 2 digits to state).

## Stage 2: Point-in-Polygon Lookup

We use official Bundestag constituency boundaries (GeoJSON format) with shapely for geometric queries.

### Process:
1. Load GeoJSON with 299 Bundestag constituencies on startup
2. Create shapely Point from coordinates
3. Check which constituency Polygon contains the point
4. Look up Constituency object in database by external_id
5. Return Constituency or None

### Performance:
- GeoJSON loaded once at startup (~2MB in memory)
- Class-level caching prevents repeated loads
- Lookup typically takes 10-50ms
- No external API calls required

## Data Sources

- **Constituency Boundaries**: [dknx01/wahlkreissuche](https://github.com/dknx01/wahlkreissuche) (Open Data)
- **Geocoding**: [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) (Open Data)
- **Representative Data**: [Abgeordnetenwatch API](https://www.abgeordnetenwatch.de/api)

## Accuracy

This approach provides constituency-accurate matching (exact Wahlkreis), significantly more precise than PLZ-based heuristics which only provide state-level accuracy.

### Known Limitations:
- Requires valid German address
- Dependent on OSM geocoding quality
- Rate limited to 1 request/second (public API)

## Implementation Details

### Services

- **AddressGeocoder** (`letters/services.py`): Handles geocoding with caching
- **WahlkreisLocator** (`letters/services.py`): Performs point-in-polygon matching
- **ConstituencyLocator** (`letters/services.py`): Integrates both services with PLZ fallback

### Database Models

- **GeocodeCache** (`letters/models.py`): Caches geocoding results to minimize API calls
- **Constituency** (`letters/models.py`): Stores constituency information with external_id mapping to GeoJSON

### Management Commands

- **fetch_wahlkreis_data**: Downloads official Bundestag constituency boundaries
- **test_matching**: Tests address matching with sample German addresses
