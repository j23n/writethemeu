# Wahlkreis-Constituency Separation

## Overview

This architecture separates **geographic Wahlkreise** (electoral districts) from **parliamentary Constituencies** to support the fact that a single address maps to multiple parliament levels.

## Concepts

### Wahlkreis (Electoral District)
- Geographic region used for elections
- An address has exactly 3 Wahlkreise:
  - EU Wahlkreis (all of Germany = 'DE')
  - Federal Wahlkreis (Bundestag, 1-299)
  - State Wahlkreis (Landtag, varies by state)

### Constituency
- Parliamentary representation unit for a specific term
- Usually maps 1:1 to a Wahlkreis (direct mandate winner)
- Can be different (e.g., state-level list when no direct mandate won)

## Data Model

### IdentityVerification
Stores Wahlkreis identifiers:
- `federal_wahlkreis_number`: CharField (e.g., "075")
- `state_wahlkreis_number`: CharField (state-specific)
- `eu_wahlkreis`: CharField (always "DE")

Links to constituencies:
- `constituencies`: ManyToMany to Constituency

### Constituency
Links to geographic Wahlkreis:
- `wahlkreis_id`: CharField (e.g., "075" for Berlin-Mitte)

## Address Resolution Flow

1. **Geocode** address → coordinates
2. **Look up Wahlkreis** from GeoJSON → federal/state Wahlkreis numbers
3. **Store identifiers** on IdentityVerification
4. **Query Constituencies** where wahlkreis_id matches
5. **Add state-level constituencies** (STATE_LIST) for user's state
6. **Store all** in constituencies M2M

## Services

### WahlkreisResolver
Resolves addresses to Wahlkreis identifiers and Constituency objects.

### ConstituencyLocator
Uses WahlkreisResolver for address-based lookups, with PLZ fallback.

## Commands

### sync_wahlkreise
- Downloads Wahlkreis GeoJSON data
- Creates all 299 federal constituencies
- Populates wahlkreis_id fields
- Ensures EU constituency exists
