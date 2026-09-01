#!/usr/bin/env Rscript
# plot_genus_candidates.R — candidate-panel maps for genus-only ASV groups
# (predicted species from the crosscheck genus-narrow mode).
#
# QUARANTINE RULE: a genus-only ASV has NO species verdict. Candidate panels use
# the labels SUPPORTED / WEAK / NO_RECORD (nearest-record distance vs --near-km)
# — NEVER CONCORDANT / DISCORDANT / NO_RECORD — and write to
# species_maps/genus_candidates/. They never enter the species verdict ledger
# (crosscheck_report / flagged_occurrences stay untouched); the only ledger entry
# is a figure-status record so the report can reference the panel set.
#
# Per genus-only taxon, per candidate species (top-N from genus_candidates.csv):
#   - grey points       : candidate species' GBIF/OBIS context records
#   - dashed ring       : declared buffer radius
#   - hollow diamond    : detection site (unconfirmed candidate hypothesis)
#   - plausibility      : SUPPORTED (nearest <= near-km) / WEAK (in-region,
#                         nearest > near-km) / NO_RECORD (zero context records)
#
# Usage:
#   Rscript bin/plot_genus_candidates.R --candidates <genus_candidates.csv> \
#     --overlay <context_occurrences.csv> --params <params.json> --outdir <out> \
#     [--input <enriched.parquet>] [--near-km 150] [--buffer-km N] \
#     [--max-candidates 3] [--label <label>]

suppressPackageStartupMessages({
  library(optparse); library(jsonlite); library(ggplot2); library(sf)
  suppressPackageStartupMessages({ library(dplyr) })
})

script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

option_list <- list(
  make_option("--candidates", type = "character", help = "genus_candidates.csv (required)"),
  make_option("--input", type = "character", default = NULL, help = "enriched.parquet (for site coords); optional if --site-lat/--site-lon given"),
  make_option("--site-lat", type = "double", default = NULL),
  make_option("--site-lon", type = "double", default = NULL),
  make_option("--overlay", type = "character", default = NULL, help = "context_occurrences.csv (detected taxa)"),
  make_option("--candidates-context", type = "character", default = NULL,
              help = "candidates_context_occurrences.csv: the candidate species own context records (needed for honest plausibility)"),
  make_option("--params", type = "character", default = NULL, help = "params.json (buffer source)"),
  make_option("--outdir", type = "character", help = "viz output dir"),
  make_option("--near-km", type = "double", default = 150),
  make_option("--buffer-km", type = "double", default = NULL),
  make_option("--max-candidates", type = "integer", default = 3L, help = "panels per genus (default 3)"),
  make_option("--label", type = "character", default = NULL),
  make_option("--input-label", type = "character", default = NULL, help = "alias of --label (run_phase compat)"),
  make_option("--config", type = "character", default = NULL, help = "run config (run_phase compat)")
)
opt <- parse_args(OptionParser(option_list = option_list))
for (f in c(opt$candidates, opt$overlay, opt[["candidates-context"]], if (!is.null(opt$input)) opt$input))
  if (!file.exists(f)) stop(sprintf("plot_genus_candidates: not found: %s", f), call. = FALSE)

# ---- detection site (single-site assumption, mirrors per-species maps) -------
if (!is.null(opt[["site-lat"]]) && !is.null(opt[["site-lon"]])) {
  site_lat <- opt[["site-lat"]]; site_lon <- opt[["site-lon"]]
} else if (!is.null(opt$input)) {
  df <- load_input(opt$input)
  df$decimalLatitude  <- as.numeric(df$decimalLatitude)
  df$decimalLongitude <- as.numeric(df$decimalLongitude)
  sites <- unique(df[!is.na(df$decimalLatitude) & !is.na(df$decimalLongitude),
                     c("decimalLatitude", "decimalLongitude")])
  stopifnot(nrow(sites) > 0)
  site_lat <- mean(sites$decimalLatitude); site_lon <- mean(sites$decimalLongitude)
} else stop("need --input or --site-lat/--site-lon", call. = FALSE)

params <- if (!is.null(opt$params) && file.exists(opt$params)) jsonlite::fromJSON(opt$params) else list()
buffer_km <- if (!is.null(opt[["buffer-km"]])) opt[["buffer-km"]] else {
  b <- params$buffer; if (!is.null(b) && !is.null(b$km) && !is.na(b$km)) b$km else 2000
}
opt_label <- if (!is.null(opt$label)) opt$label else if (!is.null(opt$`input-label`)) opt$`input-label` else "eDNA detections"

haversine_km <- function(lat1, lon1, lat2, lon2) {
  R <- 6371.0088; d2r <- pi / 180
  p1 <- lat1 * d2r; p2 <- lat2 * d2r
  dp <- (lat2 - lat1) * d2r; dl <- (lon2 - lon1) * d2r
  a <- sin(dp / 2)^2 + cos(p1) * cos(p2) * sin(dl / 2)^2
  2 * R * asin(min(1, sqrt(a)))
}

# ---- geodesic buffer ring -----------------------------------------------------
ring <- local({
  R <- 6371.0088
  d <- buffer_km / R
  lat0 <- site_lat * pi / 180; lon0 <- site_lon * pi / 180
  brg <- seq(0, 2 * pi, length.out = 73)
  lat2 <- asin(sin(lat0) * cos(d) + cos(lat0) * sin(d) * cos(brg))
  lon2 <- lon0 + atan2(sin(brg) * sin(d) * cos(lat0),
                       cos(d) - sin(lat0) * sin(lat2))
  data.frame(decimalLongitude = lon2 * 180 / pi,
             decimalLatitude  = lat2 * 180 / pi)
})

# ---- context records ----------------------------------------------------------
overlay_files <- c(opt$overlay, opt[["candidates-context"]])
overlay_files <- overlay_files[!is.null(overlay_files) & nzchar(overlay_files)]
if (length(overlay_files) == 0) stop("need --overlay and/or --candidates-context", call. = FALSE)
ctx_all <- do.call(rbind, lapply(unique(normalizePath(overlay_files, mustWork = TRUE)),
                                function(f) read.csv(f, stringsAsFactors = FALSE)))
ctx_all$decimalLatitude  <- as.numeric(ctx_all$decimalLatitude)
ctx_all$decimalLongitude <- as.numeric(ctx_all$decimalLongitude)
ctx_all <- ctx_all[!is.na(ctx_all$decimalLatitude) & !is.na(ctx_all$decimalLongitude), , drop = FALSE]
binom <- function(x) tolower(paste(head(strsplit(trimws(x), "\\s+")[[1]], 2), collapse = " "))
ctx_all$key <- vapply(ctx_all$scientificName, binom, character(1))

haversine_km <- function(lat1, lon1, lat2, lon2) {
  R <- 6371.0088
  d2r <- pi / 180
  p1 <- lat1 * d2r; p2 <- lat2 * d2r
  dp <- (lat2 - lat1) * d2r; dl <- (lon2 - lon1) * d2r
  a <- sin(dp / 2)^2 + cos(p1) * cos(p2) * sin(dl / 2)^2
  2 * R * asin(min(1, sqrt(a)))
}

# ---- candidates ---------------------------------------------------------------
cand <- read.csv(opt$candidates, stringsAsFactors = FALSE, check.names = FALSE)
cand$rank <- suppressWarnings(as.integer(cand$rank))
cand$binomial_key <- vapply(cand$candidate_species, binom, character(1))
cand <- cand[order(cand$genus, cand$rank), , drop = FALSE]
genera <- unique(cand$genus)

out_root <- file.path(opt$outdir, "species_maps", "genus_candidates")
dir.create(out_root, recursive = TRUE, showWarnings = FALSE)
slug <- function(x) gsub("[^A-Za-z0-9._-]+", "_", x)
strip_authors <- function(x) paste(head(strsplit(trimws(x), "\\s+")[[1]], 2), collapse = " ")

n_pan <- 0
for (g in sort(genera)) {
  rows <- cand[cand$genus == g, , drop = FALSE]
  rows <- head(rows[order(rows$rank), , drop = FALSE], opt[["max-candidates"]])
  n_cand <- nrow(rows)
  for (i in seq_len(n_cand)) {
    r <- rows[i, ]
    sp_name <- r$candidate_species
    ctx <- ctx_all[ctx_all$key == r$binomial_key[1], , drop = FALSE]
    n_gb <- sum(ctx$source == "gbif"); n_ob <- sum(ctx$source == "obis")
    near <- if (nrow(ctx) > 0) min(vapply(seq_len(nrow(ctx)),
            function(j) haversine_km(site_lat, site_lon, ctx$decimalLatitude[j], ctx$decimalLongitude[j]),
            numeric(1))) else Inf
    if (nrow(ctx) == 0) {
      plaus <- "NO_RECORD"; col_pl <- "#8e44ad"
      note <- "no GBIF/OBIS records anywhere in the buffer — absence of evidence, never a ranking"
    } else if (near <= opt[["near-km"]]) {
      plaus <- "SUPPORTED"; col_pl <- "#1a7a3a"
    } else {
      plaus <- "WEAK"; col_pl <- "#e67e22"
    }
    near_note <- if (nrow(ctx) > 0) sprintf("nearest known record %.0f km from site", near) else "no context records"
    ex <- c(min(ring$decimalLongitude), min(ring$decimalLatitude),
            max(ring$decimalLongitude), max(ring$decimalLatitude))

    p <- ggplot() +
      geom_sf(data = rnaturalearth::ne_countries(scale = "medium", returnclass = "sf"),
              fill = "grey90", colour = "grey70", linewidth = 0.2) +
      geom_polygon(data = ring, aes(x = decimalLongitude, y = decimalLatitude),
                   fill = "steelblue", alpha = 0.03, colour = "steelblue",
                   linetype = "dashed", linewidth = 0.5) +
      { if (nrow(ctx) > 0) geom_point(data = ctx, aes(x = decimalLongitude, y = decimalLatitude),
              shape = 16, colour = "grey50", size = 1.6, alpha = 0.9) else NULL } +
      geom_point(aes(x = site_lon, y = site_lat), shape = 23, fill = "white",
                 colour = "grey20", size = 3.6, stroke = 0.9) +
      coord_sf(xlim = ex[c(1, 3)], ylim = ex[c(2, 4)], expand = FALSE) +
      labs(title = sprintf("%s \u2014 candidate %d of %d: %s", g, r$rank, n_cand, sp_name),
           subtitle = sprintf(
             "GENUS-LEVEL HYPOTHESIS, not a species identification \u00b7 %s \u2014 %s GBIF \u00b7 %s OBIS records in the %s km buffer \u00b7 %s",
             plaus, format(n_gb, big.mark = ","), format(n_ob, big.mark = ","),
             format(buffer_km, big.mark = ","), near_note),
           x = "Longitude", y = "Latitude",
           caption = sprintf("hollow diamond = detection site (candidate) \u00b7 grey = candidate species' GBIF/OBIS occurrences \u00b7 dashed ring = %s km buffer \u00b7 %s",
                             format(buffer_km, big.mark = ","), opt_label)) +
      theme_bw(base_size = 10) +
      theme(panel.grid = element_line(colour = "grey92", linewidth = 0.25),
            plot.title = element_text(face = "italic", size = 12),
            plot.subtitle = element_text(size = 9, colour = col_pl))
    base_out <- file.path(out_root, sprintf("%s__rank%d_%s__%s", slug(g), r$rank, slug(sp_name), plaus))
    save_fig(p, base_out, formats = c("png", "pdf"), width = 8, height = 8)
    n_pan <- n_pan + 1
  }
}
log_msg(sprintf("genus-candidate panels: %d written to %s (ledger NOT updated \u2014 candidates never enter the species layer)", n_pan, out_root))