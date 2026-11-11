---
name: occviz-occurrence-maps
description: "Interactive species occurrence map for DwC-shaped occurrence tables (occurrence-viz maps/ sub-skill, PLAN-marine-edna-meta-skill.md §5). R leaflet (v1.9.0 replacement for the retired rnaturalearth/ggplot2 static maps): self-contained single-file HTML with the concordance ring R drawn as a circle (SP-11 echo), verdict layer toggles (CONCORDANT / OUT_OF_RANGE / AMBIGUOUS), per-species GBIF/OBIS ring-vs-world counts in popups, optional GBIF/OBIS context overlay, offline embedded Natural Earth basemap, best-effort PNG snapshot via webshot2/Chrome. Triggers: \"occurrence map eDNA\", \"plot gbif obis records\", \"species occurrence map\"."
version: 2.0.4
updated: "2026-11-11"
triggers:
  - "occurrence map eDNA"
  - "plot gbif obis records"
  - "species occurrence map"
  - "leaflet occurrence map"
---

# Skill: occviz-occurrence-maps (occurrence-viz / maps)

> **v2.0.4 (2026-11-11) — single custom panel (user feedback).** The leaflet layers control is
> GONE: a 60-group control bled off the viewport and its verdict toggles duplicated the
> per-species view. One custom panel (top-right, max-height 58 vh + scroll) now owns all
> control: CONCORDANT / OUT_OF_RANGE / AMBIGUOUS checkboxes toggle the GBIF/OBIS context dots
> **of the species carrying that verdict** (blue in-ring, gray beyond-ring), plus ring and
> detections toggles and the per-species dropdown. The sampling pin is a **neutral dark**
> color at all times (verdict is carried by the per-verdict species dots, not the pin).
> Markers are drawn JS-side from data injected into the jsHook (canvas renderer); the hook
> body must use `this` for the map and 3rd arg is null.
>
> **v2.0.1 (2026-11-11) — basemap hardening.** Remote tile providers removed entirely after
> OSM policy-blocked the reviewer's browser on the battle-test HTML. The basemap is now embedded
> natural-earth land polygons; the widget makes zero network requests.
>
> **v2.0.0 (2026-11-11) — renderer swap.** The ggplot2 static map renderer
> (`plot_map.R`, `plot_per_species.R`, `plot_genus_candidates.R`) is **retired and
> deleted**. One interactive R-leaflet map is now the single map deliverable.
> The renderer swap was motivated by the Ryan-12S battle test (2026-11-11): the
> static maps could not draw the concordance ring, used a non-discriminable
> 57-hue legend, and collapsed every coincident point into one dot.

## 0. Inputs / Outputs contract

### Inputs (consumed)

| Path | Source | Required? |
| --- | --- | --- |
| occurrence table (parquet/csv/tsv, PLAN §11.6 minimal DwC) | preflight/ (validated) | yes |
| realm run config JSON (`map` block; `output_formats`) | run setup | yes |
| `--near-km R` | SP-11 echo (must equal the crosscheck ring) | recommended |
| `--params` crosscheck params.json (`input_extent` = ring centre) | crosscheck | recommended |
| `--counts` occurrence_counts.json (per-taxa ring/world GBIF+OBIS counts) | crosscheck work dir | optional (popups) |
| `--overlay` context-records CSV (GBIF/OBIS context points) | context fetch | optional (gray layer) |

### Outputs (produced)

| Path | Owner | Format | Notes |
| --- | --- | --- | --- |
| `fig/01_occurrence_map.html` | this skill | **single-file HTML** (pinned deliverable) | self-contained leaflet widget; open in any browser |
| `fig/01_occurrence_map.png` | this skill | PNG snapshot | best-effort via webshot2 + Chrome; skipped with a ledger reason when Chrome is absent |
| `<outdir>/work/figure_status.jsonl` append | this skill | JSONL | consumed by report/ (`.rds` plot snapshots no longer produced for the map) |

## The map, by design

- **Per-species selector** (v2.0.3): a `bottomright` dropdown ("Per-species view") listing all
  species with their verdict and in-ring/beyond-ring record counts. Picking one: unhides ONLY
  that species' context layer, hides every other context layer, calls `fitBounds` on the
  species' record extent (clamped maxZoom 9), and prints a status line (`species · verdict · n
  in-ring / m beyond-ring records`). Emptying the selector returns to the site at zoom 6. The
  dropdown does not need the leaflet instance: the jsHook body uses **`this`** (the map, via
  `.call(this.getMap(), ...)`) — the hook's third argument is `null` in `saveWidget` output.
- **Per-species GBIF/OBIS context layers** (v2.0.2): pass `--context <context_occurrences.csv>`
  (produced upstream by `crosscheck/context_records.py <input> <realm> <params> <work>
  --buffer-km <ring> --per-species 200 --outside-cap 150`). Each species becomes ONE toggleable
  layer (`context: <species>`) containing its in-ring records (blue) AND beyond-ring records
  (gray); popups carry source, year, and haversine distance from the site. **Default OFF** —
  the map opens clean (detections + ring + verdict legend); expand the layers control (top-right,
  collapsed) and tick a species to see where it occurs vs the sampling site. This restores the
  per-species "where does this species occur" narrative the retired static per-species maps
  carried, without 57 legend entries.
- **Ring**: one `L.circle` of radius `--near-km` km centred on the crosscheck
  `input_extent` site (fallback: point centroid). Toggling the ring is the SP-11
  echo made visual — a verdict must always be readable against its threshold.
- **Verdict layer groups**: OUT_OF_RANGE / AMBIGUOUS / CONCORDANT rendered as
  toggleable overlay layers (red / amber / green), red on top. Verdict source
  order: `qc_flags` OUT_OF_RANGE → `taxon_match_status` ambiguous →
  `--counts` ring counts (zero in-ring records ⇒ OUT_OF_RANGE).
- **Popups**: per record — species (input name), verdict, accepted name when
  different, reads, station, and (with `--counts`) `in-ring: n · world: m`.
- **Basemap**: OFFLINE — Natural Earth 1:50m land polygons embedded in the widget and a CSS
  ocean colour. No remote tiles at all: OSM policy-blocks `file://` tile requests and CARTO
  key-walls headless Chrome (both verified 2026-11-11).
- **Coincident points** (single-site battles): toggles + site popups expose all
  records; zooming replaces the retired per-species facet small multiples.

## Ask-user stop points

### SP1 — Extent / bbox
Trigger: huge lat/lon spread or antimeridian crossing. Default: data-driven
(`setView` on the data centroid; user zooms interactively). Options: (A) data
extent (recommended), (B) explicit `map.bbox` in config.

### SP2 — Basemap
Pinned: **offline embedded Natural Earth 1:50m land polygons** (rendered into the widget with
`rnaturalearth::ne_countries(scale="medium")`; ocean is a CSS background colour). No remote tile
provider is used at all: OSM policy-blocks tile requests from `file://` pages ("Access blocked —
App is not following the tile usage policy" — user-observed 2026-11-11) and CARTO key-walls
headless Chrome. Options: (A) offline embedded (pinned), (B) future extension only: an explicitly
toggled online-tiles group for networked review sessions.

### SP3 — PNG snapshot
Trigger: no Chrome/Chromium on the host. Behaviour: HTML-only, ledger records
`01_occurrence_map_png: skipped`. Chrome is required for the snapshot; the
interactive HTML is always produced.

## Procedure

```bash
pixi run -e default -- Rscript bin/plot_map_leaflet.R \
    --input <enriched.parquet|csv> --config config/run-config.<realm>.json \
    --outdir <run> --input-label "<label>" \
    --near-km 2000 --params <crosscheck/params.json> \
    --counts <crosscheck/work/occurrence_counts.json>
```

## Troubleshooting — Signature library

| Signature in stderr / log | Likely cause | Suggested fix |
|---|---|---|
| `Tiles render as "API KEY REQUIRED"` | remote tile provider in use | **removed in v1.9.1** — the basemap is embedded offline; if a tile URL reappears, delete the tile layer |
| `'HTML' is not an exported object from 'namespace:htmlwidgets'` | wrong NSE namespace | use `htmltools::HTML`, not `htmlwidgets::HTML` |
| `map is null in the per-species selector` / `Cannot read properties of null (reading 'fitBounds')` | jsHook body used the hook's 3rd argument as the map | the jsHook's 3rd arg is `null` in `saveWidget` output — use **`this`** (onRender wraps with `.call(this.getMap(), …)`) |
| popup shows `in-ring: · world` empty | `--counts` not passed | pass the crosscheck `occurrence_counts.json` |
| ring not visible at default zoom | ring larger than view (e.g. R=2000 km) | zoom out; the ring is a toggleable layer |
| `Access blocked — App is not following the tile usage policy` (OSM 403) | OSM blocks tile requests from `file://` pages (no Referer) | v1.9.1 removed remote tiles entirely — embedded offline basemap |
| verdicts all CONCORDANT although crosscheck flagged OUT_OF_RANGE | `qc_flags` column absent and `--counts` missing | pass `--counts` or the enriched crosscheck parquet |

## What NOT to do

- Do **not** reintroduce a per-species hue legend on the map — verdict colouring
  is the pinned encoding; species detail lives in popups.
- Do **not** silently auto-open popups in the initial view (they occlude the
  site); popups open on click/hover only.
- Do **not** use an API-keyed tile provider — the map must render on the first
  open in any browser (a network connection must never be required).
- Do **not** add realm if-statements — realm differences come from the run config.
