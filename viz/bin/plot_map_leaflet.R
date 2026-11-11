#!/usr/bin/env Rscript
# plot_map_leaflet.R — occurrence map (maps/ sub-skill worker, v2.0.4).
#
# One interactive Leaflet map, ONE custom control panel. The leaflet layers
# control is NOT used at all (a 60-group control bleeds off screen and its
# verdict toggles duplicated the per-species view).
#
#   fig/01_occurrence_map.html  — self-contained single-file HTML (pinned)
#   fig/01_occurrence_map.png   — webshot2 snapshot (best-effort; Chrome needed)
#
# Panel semantics (v2.0.4, user-confirmed 2026-11-11):
#   * CONCORDANT / OUT_OF_RANGE / AMBIGUOUS checkboxes toggle the GBIF/OBIS
#     context DOTS of the species carrying that verdict (blue in-ring, gray
#     beyond-ring) — the sampling pin stays a NEUTRAL color at all times.
#   * Ring R (--near-km, SP-11 echo) and Detections toggles.
#   * "Per-species view" dropdown: pick one species -> only its context dots
#     show, the view fits its records, status line reports verdict + counts.
#   * Panel is max-height + scrollable: nothing bleeds off the viewport.
#
# Markers are drawn JS-side from injected data (canvas renderer); R renders
# only the offline basemap. jsHooks note: the hook body must use `this` for
# the map — the hook's 3rd argument is NULL in saveWidget output.
#
# Usage:
#   Rscript bin/plot_map_leaflet.R --input <file.parquet|csv> --config <run-config.json> \
#       --outdir <dir> [--input-label <label>] [--near-km <km>] \
#       [--params <crosscheck params.json>] [--counts <occurrence_counts.json>] \
#       [--context <context_occurrences.csv>]

suppressPackageStartupMessages({
  library(optparse); library(jsonlite); library(leaflet); library(htmlwidgets); library(htmltools); library(dplyr)
})
script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

`%||%` <- function(a, b) if (is.null(a) || length(a) == 0) b else a
esc <- function(x) htmltools::htmlEscape(as.character(x), attribute = FALSE)

option_list <- list(
  make_option("--input", type = "character", help = "Occurrence table (parquet/csv/tsv)"),
  make_option("--config", type = "character", help = "Realm run config JSON"),
  make_option("--outdir", type = "character", default = ".", help = "Output directory"),
  make_option("--input-label", type = "character", default = NULL, help = "Dataset label for captions"),
  make_option("--near-km", type = "numeric", default = NULL, help = "Concordance ring R (km; SP-11)"),
  make_option("--params", type = "character", default = NULL, help = "Crosscheck params.json (ring centre = input_extent site)"),
  make_option("--counts", type = "character", default = NULL, help = "occurrence_counts.json (per-species ring/world counts for popups)"),
  make_option("--context", type = "character", default = NULL,
              help = "context_occurrences.csv (context_records.py output): per-species GBIF/OBIS record dots")
)
opt <- parse_args(OptionParser(option_list = option_list))

cfg <- read_run_config(opt$config)
df  <- load_input(opt$input)
validate_dwctable(df)

VERDICTS <- c("CONCORDANT", "OUT_OF_RANGE", "AMBIGUOUS")
VERDICT_COLORS <- c(CONCORDANT = "#1e8449", OUT_OF_RANGE = "#c0392b", AMBIGUOUS = "#e6a817")

name_key <- function(d) d$acceptedScientificName %||% d$scientificName
key_for_input_rows <- name_key(df)

# ---------------------------------------------------------------- verdicts + counts
flagged <- if ("qc_flags" %in% names(df)) grepl("OUT_OF_RANGE", df$qc_flags, fixed = TRUE) else NULL
status_col <- if ("taxon_match_status" %in% names(df)) df$taxon_match_status else NULL
ambiguous <- if (!is.null(status_col)) status_col == "ambiguous" else rep(FALSE, nrow(df))

ring_counts <- NULL; world_counts <- NULL
if (!is.null(opt$counts) && file.exists(opt$counts)) {
  cc <- jsonlite::fromJSON(opt$counts, simplifyVector = TRUE)
  nm <- names(cc)
  ring_counts  <- vapply(cc, function(x) as.integer(sum(c(as.numeric(x$gbif %||% 0), as.numeric(x$obis %||% 0)), na.rm = TRUE)), integer(1))
  world_counts <- vapply(cc, function(x) as.integer(sum(c(as.numeric(x$gbif_world %||% 0), as.numeric(x$obis_world %||% 0)), na.rm = TRUE)), integer(1))
  names(ring_counts) <- names(world_counts) <- nm
  idx <- match(key_for_input_rows, nm)
  message(sprintf("[leaflet] counts json: %d taxa; %d/%d input rows matched", length(nm), sum(!is.na(idx)), nrow(df)))
  counts_txt <- ifelse(is.na(idx), "",
    sprintf("in-ring: %d &middot; world: %s", ring_counts[idx], format(world_counts[idx], big.mark = ",", scientific = FALSE)))
  ring_zero <- ifelse(is.na(idx) | (flagged %||% rep(FALSE, nrow(df))), FALSE, ring_counts[idx] == 0)
} else {
  counts_txt <- rep("", nrow(df))
  ring_zero <- rep(FALSE, nrow(df))
}

df$verdict <- rep("CONCORDANT", nrow(df))
df$verdict[ring_zero] <- "OUT_OF_RANGE"
if (!is.null(flagged)) df$verdict[flagged] <- "OUT_OF_RANGE"
df$verdict[ambiguous] <- "AMBIGUOUS"
df$counts_txt <- counts_txt
n_v <- table(factor(df$verdict, levels = VERDICTS))
message(sprintf("[leaflet] verdicts: %s", paste(sprintf("%s=%d", VERDICTS, n_v), collapse = " ")))

# ---------------------------------------------------------------- ring + site
r_km <- opt[["near-km"]]
site_lon <- NULL; site_lat <- NULL
if (!is.null(opt$params) && file.exists(opt$params)) {
  p <- jsonlite::fromJSON(opt$params)
  site_lon <- p$input_extent[1]; site_lat <- p$input_extent[2]
}
if (is.null(site_lon) || is.na(site_lon)) {
  site_lon <- mean(as.numeric(df$decimalLongitude), na.rm = TRUE)
  site_lat <- mean(as.numeric(df$decimalLatitude), na.rm = TRUE)
}
label <- if (!is.null(opt[["input-label"]])) opt[["input-label"]] else "occurrence records"

# ---------------------------------------------------------------- per-species context data
ctx <- NULL; sp_meta <- NULL
if (!is.null(opt$context) && file.exists(opt$context)) {
  ctx <- read.csv(opt$context, stringsAsFactors = FALSE)
  ctx$decimalLatitude <- as.numeric(ctx$decimalLatitude)
  ctx$decimalLongitude <- as.numeric(ctx$decimalLongitude)
  ctx <- ctx[!is.na(ctx$decimalLatitude) & !is.na(ctx$decimalLongitude), , drop = FALSE]
  if (!is.null(r_km) && !is.na(r_km)) {
    # v2.5.2 geodesic: in-ring = haversine distance <= R km (matches the
    # server-side circle-polygon counts and context_records window)
    hav <- function(lo, la) 6371 * acos(pmin(1, pmax(-1,
      sin(site_lat * pi/180) * sin(la * pi/180) +
      cos(site_lat * pi/180) * cos(la * pi/180) * cos((lo - site_lon) * pi/180))))
    inw <- 6371 * acos(pmin(1, pmax(-1,
      sin(site_lat * pi/180) * sin(ctx$decimalLatitude * pi/180) +
      cos(site_lat * pi/180) * cos(ctx$decimalLatitude * pi/180) *
      cos((ctx$decimalLongitude - site_lon) * pi/180)))) <= r_km
  } else inw <- rep(TRUE, nrow(ctx))
  hav <- function(lo, la) 6371 * acos(pmin(1, pmax(-1,
    sin(site_lat * pi/180) * sin(la * pi/180) +
    cos(site_lat * pi/180) * cos(la * pi/180) * cos((lo - site_lon) * pi/180))))
  ctx$dist_km <- round(hav(ctx$decimalLongitude, ctx$decimalLatitude))
  ctx$ring_pos <- ifelse(inw, "in-ring", "beyond-ring")

  # dropdown covers EVERY detected species, incl. those whose context fetch
  # returned no rows (e.g. Moolgarda pedaraki / Gerres baconensis: 0 GBIF+OBIS
  # rows in the window AND in the global sample)
  species <- sort(unique(c(unique(ctx$scientificName), unique(df$scientificName))))
  # species verdict mirrors the crosscheck ROW verdicts: any flagged row => OUT_OF_RANGE;
  # ambiguous taxon match => AMBIGUOUS; else CONCORDANT. (Row-majority created MIXED
  # species whose context dots landed in a group no toggle controls.)
  verdict_of_sp <- vapply(species, function(sp) {
    vv <- unique(df$verdict[df$scientificName == sp])
    if ("AMBIGUOUS" %in% vv) "AMBIGUOUS"
    else if ("OUT_OF_RANGE" %in% vv) "OUT_OF_RANGE"
    else if (length(vv) == 1) vv else "CONCORDANT"
  }, character(1))
  n_in  <- as.integer(table(factor(ctx$scientificName[ctx$ring_pos == "in-ring"], levels = species)))
  n_out <- as.integer(table(factor(ctx$scientificName[ctx$ring_pos == "beyond-ring"], levels = species)))
  names(n_in) <- names(n_out) <- species
  bounds <- lapply(species, function(sp) {
    d <- ctx[ctx$scientificName == sp, ]
    if (nrow(d) == 0) return(c(site_lat - 5, site_lon - 5, site_lat + 5, site_lon + 5))  # no records: fall back to site
    c(min(d$decimalLatitude), min(d$decimalLongitude), max(d$decimalLatitude), max(d$decimalLongitude))
  })
  names(bounds) <- species
  sp_meta <- setNames(lapply(species, function(sp) list(
    name = sp, verdict = unname(verdict_of_sp[[sp]]),
    n_in = unname(n_in[[sp]]), n_out = unname(n_out[[sp]]),
    bounds = unname(bounds[[sp]]))), species)
  # compact context matrix: [spIdx, lat, lng, inFlag 1/0, srcIdx 0=g/1=o/2=none, distKm]
  sp_idx <- match(ctx$scientificName, species) - 1L  # 0-based: JS indexes Object.keys(SP)
  src <- ifelse(is.na(ctx$source) | !nzchar(ctx$source), 2,
                pmatch(tolower(substr(ctx$source, 1, 1)), c("g", "o")) - 1L)
  src[is.na(src)] <- 2
  ctx_rows <- cbind(sp_idx, round(ctx$decimalLatitude, 5), round(ctx$decimalLongitude, 5),
                    as.integer(inw), as.integer(src), ctx$dist_km)
  message(sprintf("[leaflet] context: %d records, %d species, %d in-ring / %d beyond-ring, %d with verdict context",
    nrow(ctx_rows), length(species), sum(inw), sum(!inw),
    sum(verdict_of_sp %in% VERDICTS)))
}

# ---------------------------------------------------------------- detections (JS-injected)
det_rows <- cbind(
  round(as.numeric(df$decimalLatitude), 5), round(as.numeric(df$decimalLongitude), 5),
  match(df$verdict, VERDICTS),
  seq_len(nrow(df)) - 1L)

# ---------------------------------------------------------------- land basemap
land <- tryCatch(
  rnaturalearth::ne_countries(scale = "medium", returnclass = "sf"),
  error = function(e) { warn_msg("offline basemap source unavailable — plain frame"); NULL })

# ---------------------------------------------------------------- build the widget
m <- leaflet(width = "100%", height = "720px", options = leafletOptions(preferCanvas = TRUE)) |>
  addControl(htmltools::HTML("<style>.leaflet-container{background:#b6d6e8}</style>"))
if (!is.null(land)) {
  m <- m |> addPolygons(data = land,
    fillColor = "#f0efe9", fillOpacity = 1, color = "#7a8a94", weight = 0.6, smoothFactor = 0.2)
}
m <- m |> setView(lng = site_lon, lat = site_lat, zoom = 6)

# ---------------------------------------------------------------- panel + hook
sp_js   <- if (is.null(sp_meta)) "null" else jsonlite::toJSON(sp_meta, auto_unbox = TRUE, digits = NA)
ctx_js  <- if (is.null(ctx)) "null" else jsonlite::toJSON(ctx_rows)
det_js  <- jsonlite::toJSON(det_rows)
det_txt <- jsonlite::toJSON(lapply(seq_len(nrow(df)), function(i) list(
  name = df$scientificName[i], verdict = df$verdict[i],
  reads = if ("reads" %in% names(df)) df$reads[i] else NA,
  station = if ("station" %in% names(df)) df$station[i] else NA,
  counts = df$counts_txt[i])), auto_unbox = TRUE)

sp_opts <- if (is.null(sp_meta)) "" else paste0(vapply(names(sp_meta), function(sp) {
  mt <- sp_meta[[sp]]
  sprintf("<option value=\"%s\">%s — %s (%d+&#8239;%%d)</option>",
          esc(sp), esc(sp), esc(mt$verdict), mt$n_in, mt$n_out)
}, character(1)), collapse = "")

chk_color <- function(v) sprintf(
  "<label style='display:block;margin:1px 0'><input type='checkbox' class='ck-verdict' data-v='%s'>&nbsp;<span style='color:%s'>&#9679;</span> %s <span style='color:#888'>(GBIF/OBIS dots)</span></label>",
  v, VERDICT_COLORS[[v]], v)

panel_html <- paste0(
  "<div style='max-height:58vh;overflow-y:auto;padding:8px 10px;background:rgba(255,255,255,.97);",
    "border:1px solid #9aa7b0;border-radius:6px;font:12px/1.4 sans-serif;color:#222'>",
    "<b>Verdict evidence</b> <span style='font-weight:400;color:#666'>(per-verdict species dots)</span>",
    chk_color("CONCORDANT"), chk_color("OUT_OF_RANGE"), chk_color("AMBIGUOUS"),
    "<label style='display:block;margin:1px 0'><input type='checkbox' id='ck-ring' checked>&nbsp;",
      "<span style='color:#3467b2'>&#9679;</span> ring", r_km %||% NA, " km (geodesic)</label>",
    "<label style='display:block;margin:1px 0'><input type='checkbox' id='ck-det' checked>&nbsp;",
      "<span style='color:#2c3e50'>&#9679;</span> detections (site)</label>",
    "<hr style='border:0;border-top:1px solid #ddd'>",
    "<b>Per-species view</b><br>",
    "<select id='spp-select' style='width:220px;max-width:230px;margin-top:3px'>",
      "<option value=''>— pick a species —</option>", sp_opts, "</select>",
    "<div id='spp-status' style='margin-top:4px;color:#345'>pick a species to show its records</div>",
  "</div>")
m <- m |> addControl(htmltools::HTML(panel_html), position = "topright")
m <- m |> addControl(htmltools::HTML(sprintf(
  "<div style='font:11px sans-serif;background:#fff9;padding:2px 6px'><b>%s</b> &middot; %d records &middot; %d species &middot; realm: %s</div>",
  esc(label), nrow(df), length(unique(na.omit(df$scientificName))), esc(cfg$realm))))
m <- m |> addControl(htmltools::HTML(
  "<div style='font:10px sans-serif;color:#445;background:#ffffffcc;padding:1px 5px'>offline basemap: Natural Earth 1:50m</div>"),
  position = "bottomright")

hook <- paste0(
  "function(el, x, data) {\n",
  "  return (function(el, x, instance) {\n",
  "    var map = this;\n",
  "    var V = {CONCORDANT: '#1e8449', OUT_OF_RANGE: '#c0392b', AMBIGUOUS: '#e6a817'};\n",
  "    var SITE = [", site_lat, ", ", site_lon, "];\n",
  "    var R_KM = ", ifelse(is.null(r_km), "null", r_km), ";\n",
  "    var SP = null, CTX = null;\n",
  "    try { SP = ", sp_js, "; } catch(e) {}\n",
  "    try { CTX = ", ctx_js, "; } catch(e) {}\n",
  "    var DET = ", det_js, ";\n",
  "    var DETX = ", det_txt, ";\n",
  "    // ring\n",
  "    var ring = null;\n",
  "    if (R_KM) {\n",
  "      ring = L.circle(SITE, {radius: R_KM * 1000, color: '#3467b2', weight: 1.5, opacity: 0.8, fill: false});\n",
  "      ring.bindPopup('Concordance ring <b>R = ' + R_KM + ' km</b> (geodesic circle — verdict counts are records within this distance, v2.5.2)');\n",
  "    }\n",
  "    if (ring) map.addLayer(ring);\n",
  "    // detection dots (neutral pin color, by design)\n",
  "    var detLG = L.layerGroup();\n",
  "    for (var i = 0; i < DET.length; i++) {\n",
  "      var d = DET[i], t = DETX[d[3]];\n",
  "      L.circleMarker([d[0], d[1]], {radius: 7, color: '#222', weight: 1, fillColor: '#2c3e50', fillOpacity: 0.85})\n",
  "        .bindPopup('<b>' + t.name + '</b> &middot; ' + t.verdict +\n",
  "          (t.station ? '<br><small>station: ' + t.station + '</small>' : '') +\n",
  "          (t.reads ? '<br><small>reads: ' + Number(t.reads).toLocaleString() + '</small>' : '') +\n",
  "          (t.counts ? '<br><small>' + t.counts + '</small>' : ''))\n",
  "        .addTo(detLG);\n",
  "    }\n",
  "    map.addLayer(detLG);\n",
  "    // verdict context groups (hidden by default)\n",
  "    var ctxLG = {};\n",
  "    Object.keys(V).forEach(function(v) { ctxLG[v] = L.layerGroup(); });\n",
  "    var seenDet = {};\n",
  "    if (CTX && SP) {\n",
  "      for (var i = 0; i < CTX.length; i++) {\n",
  "        var c = CTX[i];\n",
  "        var name = Object.keys(SP)[c[0]] !== undefined ? Object.keys(SP)[c[0]] : null;\n",
  "        if (name === null) continue;\n",
  "        seenDet[c[0]] = 1;\n",
  "        var sp = SP[name]; if (!sp) continue;\n",
  "        var v = sp.verdict;\n",
  "        if (!ctxLG[v]) continue;\n",
  "        var srctxt = (c[4] === 0 ? 'GBIF' : c[4] === 1 ? 'OBIS' : 'context');\n",
  "        L.circleMarker([c[1], c[2]], {radius: c[3] ? 3 : 2.5,\n",
  "            fillColor: c[3] ? '#3467b2' : '#8a8a8a', fillOpacity: c[3] ? 0.65 : 0.4, stroke: false})\n",
  "          .bindPopup('<b>' + name + '</b><br><small>' + srctxt + ' &middot; ' + (c[3] ? 'in-ring' : 'beyond-ring') +\n",
  "            ' &middot; ~' + Number(c[5]).toLocaleString() + ' km from site</small>')\n",
  "          .addTo(ctxLG[v]);\n",
  "      }\n",
  "    }\n",
  "    // panel wiring\n",
  "    var spp = el.querySelector('#spp-select'), status = el.querySelector('#spp-status');\n",
  "    var spLG = null;   // current per-species layer\n",
  "    function hideAllVerdict() {\n",
  "      document.querySelectorAll('.ck-verdict').forEach(function(cb) { cb.checked = false; });\n",
  "      Object.keys(ctxLG).forEach(function(v) { map.removeLayer(ctxLG[v]); });\n",
  "    }\n",
  "    document.querySelectorAll('.ck-verdict').forEach(function(cb) {\n",
  "      cb.addEventListener('change', function() {\n",
  "        var v = cb.getAttribute('data-v');\n",
  "        if (cb.checked) { if (spLG) map.removeLayer(spLG); spLG = null; if (spp) spp.value = ''; hideSpp(); map.addLayer(ctxLG[v]); }\n",
  "        else map.removeLayer(ctxLG[v]);\n",
  "        if (status) status.innerHTML = 'pick a species to show its records';\n",
  "      });\n",
  "    });\n",
  "    var ckRing = el.querySelector('#ck-ring');\n",
  "    if (ckRing) ckRing.addEventListener('change', function() {\n",
  "      if (ckRing.checked && ring) map.addLayer(ring); else if (ring) map.removeLayer(ring);\n",
  "    });\n",
  "    var ckDet = el.querySelector('#ck-det');\n",
  "    if (ckDet) ckDet.addEventListener('change', function() {\n",
  "      if (ckDet.checked) map.addLayer(detLG); else map.removeLayer(detLG);\n",
  "    });\n",
  "    function hideSpp() {}\n",
  "    if (spp) spp.addEventListener('change', function() {\n",
  "      var sp = spp.value;\n",
  "      if (spLG) { map.removeLayer(spLG); spLG = null; }\n",
  "      hideAllVerdict();\n",
  "      if (sp !== '' && SP && SP[sp]) {\n",
  "        var mt = SP[sp];\n",
  "        spLG = L.layerGroup();\n",
  "        if (CTX && SP) {\n",
  "          var idxMap = {}; var names = Object.keys(SP);\n",
  "          for (var k = 0; k < names.length; k++) idxMap[names[k]] = k;\n",
  "          var si = idxMap[sp];\n",
  "          if (si !== undefined && CTX) for (var i = 0; i < CTX.length; i++) {\n",
  "            var c = CTX[i]; if (c[0] !== si) continue;\n",
  "            var srctxt = (c[4] === 0 ? 'GBIF' : c[4] === 1 ? 'OBIS' : 'context');\n",
  "            L.circleMarker([c[1], c[2]], {radius: c[3] ? 3.5 : 3,\n",
  "                fillColor: c[3] ? '#3467b2' : '#8a8a8a', fillOpacity: c[3] ? 0.7 : 0.45, color: '#222', weight: 0.5})\n",
  "              .bindPopup('<b>' + sp + '</b><br><small>' + srctxt + ' &middot; ' + (c[3] ? 'in-ring' : 'beyond-ring') +\n",
  "                ' &middot; ~' + Number(c[5]).toLocaleString() + ' km from site</small>')\n",
  "              .addTo(spLG);\n",
  "          }\n",
  "        }\n",
  "        map.addLayer(spLG);\n",
  "        if (status) status.innerHTML = '<b>' + sp + '</b> &middot; ' + mt.verdict + ' &middot; ' +\n",
  "          mt.n_in + ' in-ring / ' + mt.n_out + ' beyond-ring records';\n",
  "        map.fitBounds([[mt.bounds[0], mt.bounds[1]], [mt.bounds[2], mt.bounds[3]]], {padding: [30, 30], maxZoom: 9});\n",
  "      } else {\n",
  "        if (status) status.innerHTML = 'pick a species to show its records';\n",
  "        map.setView(SITE, 6);\n",
  "      }\n",
  "    });\n",
  "  }).call(this && this.getMap ? this.getMap() : this, el, x, data);\n",
  "}"
)

# NOTE on hook invocation: htmlwidgets jsHooks run with `this` = the widget
# instance (its getMap() is the Leaflet map) — verified live via CDP.
# The hook body therefore binds `.call(this.getMap(), ...)`; the hook's 3rd
# argument is NULL in saveWidget output, never the map.
m <- htmlwidgets::onRender(m, js = htmlwidgets::JS(hook))

fig_dir <- file.path(opt$outdir, "fig")
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)
html_path <- file.path(fig_dir, "01_occurrence_map.html")
saveWidget(m, html_path, selfcontained = TRUE, title = paste("occurrence-viz —", label))
message(sprintf("[occurrence-viz] wrote %s (self-contained leaflet, custom panel v2.0.4)", html_path))
figure_status(opt$outdir, "01_occurrence_map", "rendered", extra = list(
  html = "fig/01_occurrence_map.html", renderer = "leaflet", ui = "custom-panel-v2.0.4",
  ring_km = if (is.null(r_km)) NA else r_km, n_records = nrow(df),
  n_species = length(unique(na.omit(df$scientificName))),
  context_species = if (is.null(sp_meta)) 0 else length(sp_meta),
  context_records = if (is.null(ctx)) 0 else nrow(ctx)))

# PNG snapshot via webshot2/Chrome (best effort)
formats <- if (!is.null(cfg$output_formats)) cfg$output_formats else c("png", "pdf")
snapshot_ok <- FALSE
if ("png" %in% formats) {
  snapshot_ok <- tryCatch({
    if (is.na(Sys.getenv("CHROMOTE_CHROME", unset = NA_character_)) && Sys.which("google-chrome") != "")
      Sys.setenv(CHROMOTE_CHROME = unname(Sys.which("google-chrome")))
    if (is.na(Sys.getenv("CHROMOTE_CHROME", unset = NA_character_))) FALSE else {
      url <- paste0("file://", normalizePath(html_path, winslash = "/"))
      webshot2::webshot(url, file = file.path(fig_dir, "01_occurrence_map.png"),
                        vwidth = 1600, vheight = 1000, delay = 3)
      TRUE
    }
  }, error = function(e) {
    warn_msg(sprintf("[leaflet] PNG snapshot skipped: %s", conditionMessage(e))); FALSE
  })
  figure_status(opt$outdir, "01_occurrence_map_png", if (snapshot_ok) "rendered" else "skipped",
                file_path = if (snapshot_ok) file.path(fig_dir, "01_occurrence_map.png") else "",
                reason = if (!snapshot_ok) "webshot2/Chrome unavailable" else "")
} else {
  figure_status(opt$outdir, "01_occurrence_map_png", "skipped", reason = "png not in output_formats")
}
message(sprintf("[occurrence-viz] maps phase ok (renderer=leaflet, ui=custom-panel, png_snapshot=%s)", snapshot_ok))
quit(status = 0)
