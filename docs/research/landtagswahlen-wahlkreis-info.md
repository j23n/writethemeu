# German Electoral District Geographic Data: Complete Guide

**Germany's 16 states provide varying levels of access to Landtagswahlen electoral district geodata, with Baden-Württemberg, Berlin, and Thuringia offering the best direct downloads in modern formats like GeoJSON and GeoPackage.** Only 3-4 states provide Stimmbezirk (polling district) level data centrally, as most municipalities manage this granular data independently. Below is a comprehensive resource table with direct download links and detailed specifications for programmatic coordinate mapping.

## Complete State-by-State Reference Table

| State | Wahlkreise | Download Link(s) | Format | Detail Level | Status | Notes |
|-------|-----------|------------------|--------|--------------|---------|-------|
| **Baden-Württemberg** | 70 | [GeoJSON](https://www.statistik-bw.de/fileadmin/user_upload/medien/bilder/Karten_und_Geometrien_der_Wahlkreise/LTWahlkreise2026-BW_GEOJSON.zip) \| [Shapefile](https://www.statistik-bw.de/fileadmin/user_upload/medien/bilder/Karten_und_Geometrien_der_Wahlkreise/LTWahlkreise2026-BW_SHP.zip) \| [Download Page](https://www.statistik-bw.de/Wahlen/Download_GeoDaten.jsp) | GeoJSON, Shapefile, CSV, SVG | Wahlkreis only | ✅ Current (2026) | **EXCELLENT** - Multiple formats, forward-looking 2026 data already available. Statistisches Landesamt BW. |
| **Bavaria (Bayern)** | 91 Stimmkreise, 7 Wahlkreise | [FragDenStaat Request #274642](https://fragdenstaat.de/en/request/geometrien-der-stimmkreiseinteilung-zur-landtagswahl-2023-in-bayern/) | Shapefile | Stimmkreis only | ✅ Current (2023) | Via freedom of information request. No central download portal. Contact: Bayerisches Landesamt für Statistik. |
| **Berlin** | 78 | [Wahlkreise](https://daten.berlin.de/datensaetze/geometrien-der-wahlkreise-für-die-wahl-zum-abgeordnetenhaus-von-berlin-2021) \| [Wahlbezirke](https://daten.berlin.de/datensaetze/geometrien-der-wahlbezirke-für-die-wahlen-zum-deutschen-bundestag-berlin-und-zum) | Shapefile | **Both Wahlkreis & Wahlbezirk** | ✅ Current (2021/2023) | **EXCELLENT** - Full polling district data available. EPSG:25833. CC-BY 3.0 license. |
| **Brandenburg** | 44 | Municipal sources only (e.g., [Potsdam](https://opendata.potsdam.de/)) \| Contact Landeswahlleiter | GeoJSON, Shapefile (municipal) | Varies by municipality | ⚠️ Limited | No state-wide Landtagswahl download found. Potsdam has excellent Wahlkreis & Wahlbezirk data. Contact: Ministerium des Innern. |
| **Bremen** | N/A (city-state) | [Wahlbezirke Bremen](http://gdi2.geo.bremen.de/inspire/download/Wahlbezirke/data/Wahlbezirke_HB.zip) \| [GovData](https://www.govdata.de/daten/-/details/wahlbezirke-der-stadt-bremen) | Shapefile, GML | Wahlbezirk (polling districts) | ✅ Current | City-state structure. Separate data for Bremerhaven via vermamt@magistrat.bremerhaven.de. CC BY 4.0. |
| **Hamburg** | Multiple levels | [WFS Service](https://geodienste.hamburg.de/HH_WFS_Wahlen?REQUEST=GetCapabilities&SERVICE=WFS) \| [Transparenzportal](https://suche.transparenz.hamburg.de/dataset/geodaten-zu-wahlen-von-hamburg-bundestags-und-burgerschaftswahl11) | GML (via WFS) | **Both Wahlkreis & Stimmbezirk** (~1,300 units) | ✅ Current | **EXCELLENT detail** - WFS service provides finest granularity. Convertible to GeoJSON/Shapefile. Datenlizenz Deutschland 2.0. |
| **Hesse (Hessen)** | 55 | Contact required: presse@statistik.hessen.de | Likely Shapefile | Wahlkreis only | ⚠️ Limited | Geodata not publicly available. Contact Hessisches Statistisches Landesamt directly to request. |
| **Lower Saxony (Niedersachsen)** | 87 | [Shapefile 2022](https://www.statistik.niedersachsen.de/download/182342) \| [Usage Notes](https://www.statistik.niedersachsen.de/download/182343) \| [Statistics Page](https://www.statistik.niedersachsen.de/themen/Landtagswahlen-niedersachsen/landtagswahlen-in-niedersachsen-tabellen-und-wahlkreiskarten-227429.html) | Shapefile | Wahlkreis; **Stimmbezirk on request** | ✅ Current (2022) | **EXCELLENT** - Direct download + Wahlbezirk data available via email: Wahl@statistik.niedersachsen.de. CC BY 4.0. |
| **Mecklenburg-Vorpommern** | 36 | [LAIV-MV Wahlen](https://www.laiv-mv.de/Wahlen/Landtagswahlen/2021/Wahlkreise-und-–leiter/) \| Contact for Shapefile | Shapefile | Wahlkreis only | ✅ Current (2021) | Shapefiles (KLWK250MV, KLWK750MV) referenced but contact LAIV-MV for downloads. CC BY 4.0. |
| **North Rhine-Westphalia (Nordrhein-Westfalen)** | 128 | [Shapefile 2022](https://www.wahlergebnisse.nrw/landtagswahlen/2022/wahlkreiskarten/16_LW2022_NRW_Wahlkreise.zip) \| [Portal](https://www.wahlergebnisse.nrw/landtagswahlen/2022/wahlkreiskarten.shtml) | Shapefile, PDF, EPS, AI, EMF | Wahlkreis only | ✅ Current (2022) | **VERY GOOD** - Multiple formats. Municipal Stimmbezirk data in some cities (e.g., Cologne open data). |
| **Rhineland-Palatinate (Rheinland-Pfalz)** | 52 | [PDF Maps Only](https://www.wahlen.rlp.de/landtagswahl/wahlkreise/karten-der-wahlkreise) | PDF | PDF maps only | ⚠️ PDF only | **POOR** - No machine-readable geodata. Would need manual digitization or reconstruction from administrative boundaries. |
| **Saarland** | 3 large districts | Contact: landeswahlleitung@innen.saarland.de \| [Geoportal](https://geoportal.saarland.de/) | Likely WFS/Shapefile | Only 3 Wahlkreise | ⚠️ Limited | **Special system** - Only 3 large regional constituencies. Specific geodata not publicly available. Contact Statistisches Amt or LVGL. |
| **Saxony (Sachsen)** | 60 | [WMS Service](https://geodienste.sachsen.de/wms_smr_wahlkreise/guest?Request=GetCapabilities&Service=WMS&Version=1.3.0) \| [Verwaltungsatlas](https://www.verwaltungsatlas.sachsen.de/wahlkreise-4001.html) \| [Geoportal](https://geoportal.sachsen.de/cps/metadaten_portal.html?id=acd178cc-acbe-4586-bc65-8643ae938500) | WMS | Wahlkreis only | ✅ Current (2024) | WMS service accessible via GIS software. No direct Shapefile download. Datenlizenz Deutschland 2.0. |
| **Saxony-Anhalt (Sachsen-Anhalt)** | 41 | [2021 Shapefile](https://wahlergebnisse.sachsen-anhalt.de/wahlen/lt21/wahlkreiseinteilung/downloads/download.php) \| [2016 Shapefile](https://wahlergebnisse.sachsen-anhalt.de/wahlen/lt16/wahlkreiseinteilung/downloads/download.php) | Shapefile | Wahlkreis only | ⚠️ 2026 pending | Historical data available. 2026 election geodata not yet released (election: Sep 2026). Contact Landeswahlleiterin. |
| **Schleswig-Holstein** | 35 | [GeoJSON](https://geodienste.hamburg.de/download?url=https://geodienste.hamburg.de/SH_WFS_Wahlen&f=json) \| [CSV](https://geodienste.hamburg.de/download?url=https://geodienste.hamburg.de/SH_WFS_Wahlen&f=csv) \| [MetaVer](https://metaver.de/trefferanzeige?docuuid=8D9A9A39-F57E-4C7A-9078-A601D249A8FF) | GeoJSON, CSV, GML | Wahlkreis only | ✅ Current (2022) | **EXCELLENT** - Direct GeoJSON download. Datenlizenz Deutschland 2.0. Managed by Statistik Nord. |
| **Thuringia (Thüringen)** | 44 | [GeoPackage 2024](https://wahlen.thueringen.de/landtagswahlen/informationen/vektor/2024/16TH_L24_Wahlkreiseinteilung.zip) \| [Landtagswahl Info](https://wahlen.thueringen.de/landtagswahlen/lw_informationen.asp) | **GeoPackage (GPKG)** | Wahlkreis only | ✅ Current (2024) | **EXCELLENT** - Modern GeoPackage format. EPSG:25832. Direct download. Best practice example. |

## Data availability summary by quality tier

**Tier 1 - Excellent (direct download, modern formats):** Baden-Württemberg, Berlin, Hamburg, Lower Saxony, Schleswig-Holstein, Thuringia

**Tier 2 - Good (requires minor effort):** Bavaria, Bremen, Mecklenburg-Vorpommern, North Rhine-Westphalia, Saxony

**Tier 3 - Limited (requires contact or manual work):** Brandenburg, Hesse, Rhineland-Palatinate, Saarland, Saxony-Anhalt

## Technical specifications for programmatic use

**Coordinate Systems:** Most datasets use ETRS89/UTM zone 32N (EPSG:25832) or UTM zone 33N (EPSG:25833). Berlin uses EPSG:25833, Thuringia explicitly uses EPSG:25832. Always verify the .prj file or metadata.

**GeoJSON conversion:** Shapefiles can be converted to GeoJSON using GDAL/OGR: `ogr2ogr -f GeoJSON output.geojson input.shp`. Hamburg's WFS service can directly export GeoJSON via the download parameter `f=json`.

**Attribute fields:** Most datasets include Wahlkreis number (WKR_NR, Wahlkreis_Nr) and name (WKR_NAME, Wahlkreis_Name) as attributes. Check documentation for exact field names.

**License compliance:** Most use Datenlizenz Deutschland - Namensnennung 2.0 or CC BY variants. Attribution is required. Example: "© Statistisches Landesamt Baden-Württemberg, 2026" or "© GeoBasis-DE/[State]/[Year]".

## Stimmbezirk level data reality

**Only 3-4 states provide centralized Stimmbezirk data:** Berlin (direct download), Hamburg (via WFS with ~1,300 districts), Lower Saxony (on email request), and Bremen (Wahlbezirke). All other states confirmed that Stimmbezirk boundaries are managed by approximately 11,000+ individual German municipalities and are not centrally available as geodata.

**Municipal alternatives:** Large cities often publish local Stimmbezirk data on open data portals. Confirmed sources include Cologne (offenedaten-koeln.de), Potsdam (opendata.potsdam.de), Leipzig, and Frankfurt. For specific municipalities, search "[city name] open data Wahlbezirke" or contact the local statistical office.

## Key contacts for data requests

- **Baden-Württemberg:** Statistisches Landesamt via download page
- **Bavaria:** Bayerisches Landesamt für Statistik (via FragDenStaat or direct request)
- **Hesse:** presse@statistik.hessen.de
- **Lower Saxony (Wahlbezirk data):** Wahl@statistik.niedersachsen.de
- **Brandenburg:** Ministerium des Innern und für Kommunales, Potsdam
- **Rhineland-Palatinate:** Landeswahlleiter via wahlen.rlp.de
- **Saarland:** landeswahlleitung@innen.saarland.de
- **Saxony-Anhalt (2026 data):** lwl@mi.sachsen-anhalt.de
- **Thuringia:** wahlen@statistik.thueringen.de

## Implementation Status

### Currently Integrated (9 states)

The following states have been integrated into WriteThem.eu's data import system:

| State | Code | Status | Command |
|-------|------|--------|---------|
| Baden-Württemberg | BW | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state BW` |
| Bavaria | BY | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state BY` |
| Berlin | BE | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state BE` |
| Bremen | HB | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state HB` |
| Lower Saxony | NI | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state NI` |
| North Rhine-Westphalia | NW | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state NW` |
| Saxony-Anhalt | ST | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state ST` |
| Schleswig-Holstein | SH | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state SH` |
| Thuringia | TH | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state TH` |

Run `python manage.py fetch_wahlkreis_data --all-states` to download all available states.

### Pending Integration (7 states)

The following states require manual contact or additional tooling:

- Brandenburg: No state-wide download, requires municipal requests
- Hamburg: WFS service available (requires WFS client implementation)
- Hesse: Contact required for data access
- Mecklenburg-Vorpommern: Contact LAIV-MV for Shapefile access
- Rhineland-Palatinate: Only PDF maps available
- Saarland: Contact required (special 3-district system)
- Saxony: WMS service only (visualization, not vector data)

See `/data-sources/` page for contact information and data request procedures.

## Implementation workflow for coordinate mapping

**Step 1:** Download GeoJSON/Shapefile for target state(s) from links above. Prioritize GeoJSON where available (Baden-Württemberg, Schleswig-Holstein) for direct web integration.

**Step 2:** Load into GIS library or PostGIS database. For Python, use GeoPandas: `gdf = gpd.read_file('wahlkreise.shp')`. For PostgreSQL/PostGIS: `shp2pgsql -I -s 25832 wahlkreise.shp wahlkreise | psql -d yourdb`.

**Step 3:** Create spatial index for efficient point-in-polygon queries. In PostGIS: `CREATE INDEX idx_wahlkreise_geom ON wahlkreise USING GIST (geom);`

**Step 4:** Map coordinates to districts using spatial join or point-in-polygon query. Example PostGIS: `SELECT wk.wahlkreis_name FROM wahlkreise wk WHERE ST_Contains(wk.geom, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326));`

**Step 5:** For Stimmbezirk-level mapping where unavailable, consider: (a) requesting municipal data for specific cities, (b) using Wahlkreis level as fallback, or (c) exploring administrative boundary hierarchies (Gemeinden) as proxy.

## Conclusion

Germany's electoral geodata landscape shows significant variation in accessibility and standardization. Six states demonstrate best practices with modern, directly downloadable formats. However, the lack of centralized Stimmbezirk data across most states reflects the federal structure where municipalities maintain electoral administration independently. For production systems requiring fine-grained polling district mapping, Baden-Württemberg, Berlin, Hamburg, and Lower Saxony provide the most complete state-level coverage, while other applications should plan to either work at Wahlkreis granularity or engage with individual municipalities for local Stimmbezirk data.

All data sources verified as of October 15, 2025, from official state statistical offices, electoral authorities, and open data portals.