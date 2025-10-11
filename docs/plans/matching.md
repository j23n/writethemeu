# Recipient Matching Vision

## Goal
Ensure every letter reaches the most relevant representative by combining precise constituency mapping with topic-awareness and reliable representative metadata.

## Core Pillars

1. **Constituency Precision**
   - Replace postal-prefix heuristics with official boundary data:
     - Bundestag Wahlkreise (Bundeswahlleiter / BKG GeoJSON)
     - Landtag electoral districts via state open-data portals or OParl feeds
     - EU parliament treated as nationwide constituency
   - Normalise mandate modes:
     - Direktmandat → voters in that Wahlkreis
     - Landesliste → voters in the state
     - Bundes/EU list → national constituencies
   - Centralise the logic in a “constituency router” so each parliament’s data source is pluggable.

2. **Topic Understanding**
   - Analyse title + body to classify concerns into a canonical taxonomy (reuse committee topics, extend as needed).
   - Infer the responsible level (EU / Bund / Land / Kommune) from topic metadata.
   - Keep the topic model extensible (keyword heuristics today, embeddings or classifiers tomorrow).

3. **Rich Representative Profiles**
   - Build a `RepresentativeProfile` table to store per-source enrichments:
     - Source (ABGEORDNETENWATCH, BUNDESTAG, LANDTAG_*)
     - Normalised fields: focus areas, biography, external links, responsiveness
     - Raw metadata + sync timestamps
   - Importers:
     - Abgeordnetenwatch: `/politicians/{id}` (issues, responsiveness, social links)
     - Bundestag: official vita JSON (`mdbId`) for biography + spokesperson roles
     - Landtage: state-specific data feeds (OParl, CSV, or one-off scrapers)
   - Profiles coexist; the merging service resolves conflicts and picks the best available data.

## Matching Pipeline
1. **Constituency filter**: Use the router and mandate rules to determine eligible reps.
2. **Topic filter**: Narrow to the inferred level and portfolio.
3. **Scoring**: Blend signals—constituency proximity, topic match (committee → topic), activity (votes, questions), responsiveness stats, optional user preferences.
4. **Explanation**: Provide human-readable reasons (“Direct MP for WK 123; sits on Verkehrsausschuss; answered 90% of Abgeordnetenwatch questions”).

## Data Sources Reference

| Use Case                 | Federal                             | State                                       | EU                            |
|-------------------------|-------------------------------------|---------------------------------------------|--------------------------------|
| Mandates & committees   | Abgeordnetenwatch API               | Abgeordnetenwatch, OParl, Landtag portals   | EU Parliament REST API         |
| Constituency boundaries | Bundeswahlleiter GeoJSON, BKG       | Landeswahlleitungen, state GIS datasets     | Whole-of-Germany (single geom) |
| Biography / focus       | Bundestag vita JSON, Abgeordnetenwatch issues | Landtag bios (open data)              | Europarl member profiles       |

## Implementation Notes
- Expose `sync_representative_profiles` commands per source; schedule separately from mandate sync.
- Track `source_version`/`hash` to avoid redundant imports.
- View layer consumes a `RepresentativeProfileService` that aggregates focus areas, biography, links, responsiveness.
- Keep a roadmap for future sources (party press, DIP21 votes, Europarl “files”).

## Next Steps
- Implement `RepresentativeProfile` model + importers for Abgeordnetenwatch and Bundestag.
- Integrate boundary datasets and swap the PLZ router.
- Wire the matching pipeline into the letter form suggestions and automated routing.
- Add logging/monitoring for profile freshness and matching success.

