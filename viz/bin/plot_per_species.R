#!/usr/bin/env Rscript
# plot_per_species.R — one map image PER SPECIES: eDNA detections vs GBIF/OBIS
# occurrences inside the declared buffer zone (concordance / discordance view).
#
# For each species in the enriched occurrence table (§11.2):
#   - grey points  : GBIF/OBIS known occurrence records (context_occurrences.csv
#                    from crosscheck/context_records.py, same buffer scale)
#   - dashed ring  : the declared buffer radius (km) centred on the detection
#                    site (spherical destination points, no new R deps)
#   - pink diamond : the eDNA detection site row(s) for this species
#   - verdict      : EXPECTED (corroborated in buffer) / UNEXPECTED (zero
#                    corroboration), with N=GBIF, M=OBIS counts, from
#                    occurrence_counts.json of the crosscheck run
#   - FishBase     : depth tolerance lines annotated on the map band (FishBase
#                    contributes traits, not point occurrences — occurrence
#                    points are the GBIF/OBIS layer)
#
# Usage:
#   Rscript bin/plot_per_species.R --input <enriched.parquet> \
#     --overlay <context_occurrences.csv> --params <params.json> \
#     --counts <occurrence_counts.json> --outdir <out> \
#     [--buffer-km N] [--label <label>] [--max-species 200]
#
# Writes: <out>/species_maps/<slug>__<EXPECTED|UNEXPECTED>.png/.pdf

suppressPackageStartupMessages({
  library(optparse); library(jsonlite); library(ggplot2); library(sf); library(dplyr)
  suppressPackageStartupMessages({ library(jpeg); library(grid) })
})

script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

`%||%` <- function(a, b) if (is.null(a) || (length(a) == 1 && is.na(a) && !is.logical(a))) b else a

# haversine distance (km) between a site and a set of record coordinates
haversine_km <- function(lat1, lon1, lat2, lon2) {
  R <- 6371.0088; to_rad <- pi / 180
  dlat <- (lat2 - lat1) * to_rad; dlon <- (lon2 - lon1) * to_rad
  a <- sin(dlat / 2)^2 + cos(lat1 * to_rad) * cos(lat2 * to_rad) * sin(dlon / 2)^2
  2 * R * asin(sqrt(a))
}

opt <- parse_args(OptionParser(option_list = list(
  make_option("--input", type = "character", help = "enriched.parquet (§11.2)"),
  make_option("--config", type = "character", default = NULL, help = "run config (accepted for run_phase compatibility)"),
  make_option("--input-label", type = "character", default = NULL, help = "alias of --label (run_phase compatibility)"),
  make_option("--overlay", type = "character", help = "context_occurrences.csv (GBIF/OBIS backdrop)"),
  make_option("--params", type = "character", help = "crosscheck params.json"),
  make_option("--habitat", type = "character", default = NULL,
              help = "habitat_iucn.csv (crosscheck habitat-iucn, §11.11) — subtitle annotation"),
  make_option("--images", type = "character", default = NULL,
              help = "ACCEPTED BUT IGNORED since v1.8.1 — photo inset removed from maps (redundant; covered map regions). Photos live in the report's Species images tab and fig 07 contact sheet."),
  make_option("--counts", type = "character", default = "work/occurrence_counts.json",
              help = "occurrence_counts.json from the crosscheck run"),
  make_option("--outdir", type = "character", default = "species_maps"),
  make_option("--buffer-km", type = "numeric", default = NULL,
              help = "buffer radius override; default = params.json buffer km"),
  make_option("--near-km", type = "numeric", default = 100,
              help = "site-level corroboration threshold: nearest known record within this distance = CONCORDANT"),
  make_option("--label", type = "character", default = NULL, help = "overrides --input-label"),
  make_option("--max-species", type = "numeric", default = 200)
)))

for (f in c(opt$input, opt$overlay, opt$params, if (!is.null(opt$images)) opt$images, if (!is.null(opt$habitat)) opt$habitat))
  if (!file.exists(f)) stop(sprintf("plot_per_species: not found: %s", f), call. = FALSE)

df <- load_input(opt$input)
df$decimalLatitude  <- as.numeric(df$decimalLatitude)
df$decimalLongitude <- as.numeric(df$decimalLongitude)
df$trait_depth_min_m <- as.numeric(df$trait_depth_min_m)
df$trait_depth_max_m <- as.numeric(df$trait_depth_max_m)

params <- jsonlite::fromJSON(opt$params)
counts <- if (file.exists(opt$counts)) jsonlite::fromJSON(opt$counts) else list()
habitat_m <- load_habitat_manifest(opt$habitat)
opt_label <- if (!is.null(opt$label)) opt$label else if (!is.null(opt$`input-label`)) opt$`input-label` else "eDNA detections"
buffer_km <- if (!is.null(opt[["buffer-km"]])) opt[["buffer-km"]] else {
  b <- params$buffer; if (!is.null(b) && !is.null(b$km) && !is.na(b$km)) b$km else 2000
}

# detection site(s): coordinates of the rows themselves
sites <- unique(df[!is.na(df$decimalLatitude) & !is.na(df$decimalLongitude),
                   c("decimalLatitude", "decimalLongitude")])
stopifnot(nrow(sites) > 0)
site_lat <- mean(sites$decimalLatitude); site_lon <- mean(sites$decimalLongitude)
n_sites <- nrow(sites)

# ---- geodesic buffer ring (spherical destination points, 72 bearings) --------
ring <- local({
  R <- 6371.0088
  d <- opt[["near-km"]] / R
  lat0 <- site_lat * pi / 180; lon0 <- site_lon * pi / 180
  brg <- seq(0, 2 * pi, length.out = 73)
  lat2 <- asin(sin(lat0) * cos(d) + cos(lat0) * sin(d) * cos(brg))
  lon2 <- lon0 + atan2(sin(brg) * sin(d) * cos(lat0),
                       cos(d) - sin(lat0) * sin(lat2))
  data.frame(decimalLongitude = lon2 * 180 / pi,
             decimalLatitude  = lat2 * 180 / pi)
})

# ---- context records (GBIF/OBIS backdrop) ------------------------------------
ctx_all <- read.csv(opt$overlay, stringsAsFactors = FALSE)
ctx_all$decimalLatitude  <- as.numeric(ctx_all$decimalLatitude)
ctx_all$decimalLongitude <- as.numeric(ctx_all$decimalLongitude)
ctx_all <- ctx_all[!is.na(ctx_all$decimalLatitude) & !is.na(ctx_all$decimalLongitude), , drop = FALSE]
ctx_all$key <- tolower(vapply(strsplit(trimws(ctx_all$scientificName), "\\s+"),
                              function(w) paste(head(w, 2), collapse = " "), character(1)))
binom_key <- function(nm) tolower(paste(head(strsplit(trimws(nm), "\\s+")[[1]], 2), collapse = " "))

# ---- per-species rendering ----------------------------------------------------
out_root <- file.path(opt$outdir, "species_maps")
dir.create(out_root, recursive = TRUE, showWarnings = FALSE)
slug <- function(x) gsub("[^A-Za-z0-9._-]+", "_", x)
trunc_credit <- function(x, w = 60) { x <- gsub(",? *uploaded by.*$", "", x); if (nchar(x) > w) paste0(substr(x, 1, w - 3), "...") else x }

species <- sort(unique(na.omit(df$scientificName)))
species <- head(species, opt[["max-species"]])
n_ok <- 0

for (nm in species) {
  det <- df[df$scientificName == nm & !is.na(df$decimalLatitude), , drop = FALSE]
  # v1.8.1: photo inset REMOVED from map images (redundant with the report's Species
  # images tab and it covered map regions); --images still accepted for viz_run compat
  # but the manifest is no longer read here.
  hn <- habitat_iucn_note(habitat_m, nm)
  ctx <- ctx_all[ctx_all$key == binom_key(nm), , drop = FALSE]
  # v2.5.1 merged-ring semantics: ONE ring = map ring = concordance threshold.
  # ctx rows are classified by haversine distance to the site: within ring = in-ring
  # evidence; beyond-ring rows are DISPLAY evidence (they corroborate "the species
  # exists, but not here" — the DISCORDANT narrative). World counts (occurrence
  # lookup v2.5.1) make NO_RECORD mean "absent from GBIF/OBIS everywhere we looked".
  ring_km <- opt[["near-km"]]
  ctx$dist_km <- haversine_km(site_lat, site_lon, ctx$decimalLatitude, ctx$decimalLongitude)
  ctx$in_ring <- !is.na(ctx$dist_km) & ctx$dist_km <= ring_km
  n_ring_gb <- sum(ctx$in_ring & ctx$source == "gbif")
  n_ring_ob <- sum(ctx$in_ring & ctx$source == "obis")
  n_beyond  <- sum(!ctx$in_ring)
  e <- counts[[nm]]
  gb <- if (!is.null(e$gbif)) e$gbif else 0L
  ob <- if (!is.null(e$obis)) e$obis else 0L
  gb_w <- if (!is.null(e$gbif_world)) e$gbif_world else NA_integer_
  ob_w <- if (!is.null(e$obis_world)) e$obis_world else NA_integer_
  n_world <- sum(c(gb_w, ob_w), na.rm = TRUE)
  n_ring <- n_ring_gb + n_ring_ob
  near_in <- if (any(ctx$in_ring)) min(ctx$dist_km[ctx$in_ring]) else Inf
  near_out <- if (any(!ctx$in_ring)) min(ctx$dist_km[!ctx$in_ring]) else Inf
  has_world <- !is.na(gb_w) || !is.na(ob_w)
  beyond_note <- if (has_world && n_world > 0) {
    sprintf("%s GBIF · %s OBIS records beyond the ring",
            format(max(0L, as.integer(gb_w) - as.integer(gb)), big.mark = ","),
            format(max(0L, as.integer(ob_w) - as.integer(ob)), big.mark = ","))
  } else if (n_beyond > 0) sprintf("%d backdrop records beyond the ring", n_beyond) else ""
  if (has_world && n_world == 0) {
    verdict <- "NO_RECORD";  col_det <- "#8e44ad"; det_note <- "no GBIF/OBIS records anywhere we looked"
  } else if (n_ring > 0 || (n_ring == 0 && (gb + ob) > 0 && near_in <= ring_km)) {
    verdict <- "CONCORDANT"; col_det <- "#2c6ea3"; det_note <- sprintf("nearest known record %.0f km from site", if (any(ctx$in_ring)) near_in else near_out)
  } else if (!has_world && n_ring == 0 && (gb + ob) == 0 && n_beyond == 0 && nrow(ctx) == 0) {
    # legacy counts manifest (pre-merged-ring): zero region counts + no rows => NO_RECORD
    verdict <- "NO_RECORD";  col_det <- "#8e44ad"; det_note <- "no GBIF/OBIS records anywhere in the buffer"
  } else {
    nd <- if (!is.infinite(near_out)) near_out else near_in
    verdict <- "DISCORDANT"; col_det <- "#e67e22"
    det_note <- if (!is.infinite(nd)) sprintf("nearest known record %.0f km away — beyond the %s km ring", nd, format(ring_km, big.mark = ","))
                 else "no records within reach of the site"
  }

  # display horizon: always shows the whole ring + the nearest beyond-ring records,
  # so the DISCORDANT narrative ("it occurs, but over THERE") is visible on the map
  horizon_km <- if (!is.infinite(near_out)) max(3 * ring_km, 1.3 * near_out) else 3 * ring_km
  horizon_km <- min(horizon_km, 15000)
  ex <- c(site_lon - horizon_km / 111 * 1.08, site_lat - horizon_km / 111 * 1.08,
          site_lon + horizon_km / 111 * 1.08, site_lat + horizon_km / 111 * 1.08)
  crop <- sf::st_bbox(c(xmin = ex[1], ymin = ex[2], xmax = ex[3], ymax = ex[4]), crs = 4326)
  coast <- get_coastline("auto", "medium")
  if (!is.null(coast)) coast <- safe_crop_coast(coast, crop)

  depth_note <- {
    if (!is.null(det$trait_depth_min_m[1]) && !is.na(det$trait_depth_min_m[1]) &&
        !is.null(det$trait_depth_max_m[1]) && !is.na(det$trait_depth_max_m[1]))
      sprintf(" · FishBase depth tolerance: %s–%s m",
              format(det$trait_depth_min_m[1]), format(det$trait_depth_max_m[1]))
    else ""
  }

  p <- ggplot() +
    geom_sf(data = coast, fill = "grey92", colour = "grey55",
            size = 0.2, inherit.aes = FALSE) +
    geom_polygon(data = ring, aes(x = decimalLongitude, y = decimalLatitude),
                 fill = "#3498db", alpha = 0.04, colour = "#2c6ea3",
                 linewidth = 0.5, linetype = "dashed") +
    {if (nrow(ctx) > 0 && any(!ctx$in_ring))
      geom_point(data = ctx[!ctx$in_ring, , drop = FALSE], aes(x = decimalLongitude, y = decimalLatitude),
                 shape = 21, fill = alpha("#c8cfd8", 0.25), colour = "grey55",
                 size = 1.0, alpha = 0.6, stroke = 0.25)
      else NULL} +
    {if (nrow(ctx) > 0 && any(ctx$in_ring))
      geom_point(data = ctx[ctx$in_ring, , drop = FALSE], aes(x = decimalLongitude, y = decimalLatitude),
                 shape = 21, fill = "#7f8c9c", colour = "grey30",
                 size = 1.1, alpha = 0.6, stroke = 0.2)
      else NULL} +
    geom_point(data = det, aes(x = decimalLongitude, y = decimalLatitude),
               shape = 23, fill = col_det, colour = "black", size = 3.4, stroke = 0.5) +
    coord_sf(xlim = ex[c(1, 3)], ylim = ex[c(2, 4)], expand = FALSE) +
    labs(title = nm,
         subtitle = paste(c(sprintf(
           "%s: %s — %s GBIF · %s OBIS records within the %s km ring · %s%s",
           opt_label, verdict,
           format(gb, big.mark = ","), format(ob, big.mark = ","),
           format(ring_km, big.mark = ","), det_note, depth_note),
           if (nzchar(beyond_note)) beyond_note else NULL,
           if (nzchar(hn)) paste0("\n", hn) else NULL), collapse = ""),
         x = "Longitude", y = "Latitude",
         caption = paste(c(
             sprintf("pink diamond = eDNA detection site · grey = occurrences within the %s km ring · pale = beyond the ring · dashed ring = concordance threshold · %s",
                     format(ring_km, big.mark = ","), opt_label)), collapse = " · ")) +
    theme_bw(base_size = 10) +
    theme(panel.grid = element_line(colour = "grey92", linewidth = 0.25),
          plot.title = element_text(face = "italic", size = 12),
          plot.subtitle = element_text(size = 9))

  base_out <- file.path(out_root, paste0(slug(nm), "__", verdict))
  save_fig(p, base_out, formats = c("png", "pdf"), width = 8, height = 8)
  n_ok <- n_ok + 1
}
log_msg(sprintf("per-species maps: %d written to %s", n_ok, out_root))