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
              help = "species_images.csv manifest (crosscheck species-images, §11.8) — embeds citable photo + credit"),
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
img_manifest <- if (!is.null(opt$images) && file.exists(opt$images)) {
  m <- read.csv(opt$images, stringsAsFactors = FALSE, colClasses = "character")
  m$abs_path <- ifelse(nzchar(m$local_file), file.path(dirname(normalizePath(opt$images)), m$local_file), "")
  m
} else NULL

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
  d <- buffer_km / R
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
  # citable photo (v2.3.0 species_images manifest): embed thumbnail + credit line
  im <- if (!is.null(img_manifest)) img_manifest[img_manifest$scientificName == nm & nzchar(img_manifest$local_file), , drop = FALSE] else NULL
  im_path <- if (!is.null(im) && nrow(im) > 0 && file.exists(im$abs_path)) im$abs_path else NA_character_
  hn <- habitat_iucn_note(habitat_m, nm)
  photo_credit <- if (!is.null(im) && nrow(im) > 0) sprintf("Photo: %s (%s%s) via %s",
        trunc_credit(if (nzchar(im$creator[1])) im$creator[1] else im$rightsHolder[1]),
        im$license[1],
        if (nzchar(im$flag[1]) && im$flag[1] == "by-nc") ", license terms apply" else "",
        im$source[1]) else if (!is.null(im) && nrow(im) > 0) sprintf("No citable photo (%s)", im$flag[1]) else ""
  ctx <- ctx_all[ctx_all$key == binom_key(nm), , drop = FALSE]
  e <- counts[[nm]]
  gb <- if (!is.null(e$gbif)) e$gbif else 0L
  ob <- if (!is.null(e$obis)) e$obis else 0L
  n_cor <- sum(c(gb, ob), na.rm = TRUE)
  # three categories (geocurate-consistent): corroboration in the buffer is
  # concordance only if records reach down to the site scale; a species with
  # records somewhere in-region but none near the site is DISCORDANT; zero
  # records at all is NO_RECORD — absence of evidence, never a discordance claim
  near <- if (nrow(ctx) > 0) min(haversine_km(site_lat, site_lon,
                                              ctx$decimalLatitude, ctx$decimalLongitude)) else Inf
  if (n_cor == 0) {
    verdict <- "NO_RECORD";  col_det <- "#8e44ad"; det_note <- "no GBIF/OBIS records anywhere in the buffer"
  } else if (near <= opt[["near-km"]]) {
    verdict <- "CONCORDANT"; col_det <- "#2c6ea3"; det_note <- sprintf("nearest known record %.0f km from site", near)
  } else {
    verdict <- "DISCORDANT"; col_det <- "#e67e22"; det_note <- sprintf("nearest known record %.0f km away (beyond the %s km site threshold)", near, format(opt[["near-km"]], big.mark = ","))
  }

  ex <- c(site_lon - buffer_km / 111 * 1.12, site_lat - buffer_km / 111 * 1.12,
          site_lon + buffer_km / 111 * 1.12, site_lat + buffer_km / 111 * 1.12)
  crop <- sf::st_bbox(c(xmin = ex[1], ymin = ex[2], xmax = ex[3], ymax = ex[4]), crs = 4326)
  coast <- get_coastline("auto", "medium")
  if (!is.null(coast)) coast <- tryCatch(sf::st_crop(coast, crop), error = function(e) coast)

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
    {if (nrow(ctx) > 0)
      geom_point(data = ctx, aes(x = decimalLongitude, y = decimalLatitude),
                 shape = 21, fill = "#7f8c9c", colour = "grey30",
                 size = 1.0, alpha = 0.55, stroke = 0.2)
      else NULL} +
    geom_point(data = det, aes(x = decimalLongitude, y = decimalLatitude),
               shape = 23, fill = col_det, colour = "black", size = 3.4, stroke = 0.5) +
    coord_sf(xlim = ex[c(1, 3)], ylim = ex[c(2, 4)], expand = FALSE) +
    { if (!is.na(im_path)) {
        img <- try(jpeg::readJPEG(im_path), silent = TRUE)
        if (!inherits(img, "try-error")) {
          d <- dim(img); step <- max(1L, min(as.integer(d[1] / 220), as.integer(d[2] / 220)) + 1L)
          small <- img[seq(1L, d[1], by = step), seq(1L, d[2], by = step), , drop = FALSE]
          xr <- diff(range(ex[1], ex[3])); yr <- diff(range(ex[2], ex[4]))
          side <- min(xr, yr) * 0.17
          x0 <- ex[3] - xr * 0.015 - side; y1 <- ex[4] - yr * 0.015; y0 <- y1 - side * (d[1]/d[2]) * (step^0)
          annotation_custom(grid::rasterGrob(as.raster(small), interpolate = TRUE),
                            xmin = x0, xmax = x0 + side, ymin = y0, ymax = y1)
        } else NULL
      } else NULL } +
    labs(title = nm,
         subtitle = paste(c(sprintf(
           "%s: %s — %s GBIF · %s OBIS records in the %s km buffer · %s%s",
           opt_label, verdict,
           format(gb, big.mark = ","), format(ob, big.mark = ","),
           format(buffer_km, big.mark = ","), det_note, depth_note),
           if (nzchar(hn)) paste0("\n", hn) else NULL), collapse = ""),
         x = "Longitude", y = "Latitude",
         caption = paste(c(
             sprintf("pink diamond = eDNA detection site · grey = GBIF/OBIS known occurrences · dashed ring = %s km buffer · %s",
                     format(buffer_km, big.mark = ","), opt_label),
             if (nzchar(photo_credit)) photo_credit else NULL), collapse = " · ")) +
    theme_bw(base_size = 10) +
    theme(panel.grid = element_line(colour = "grey92", linewidth = 0.25),
          plot.title = element_text(face = "italic", size = 12),
          plot.subtitle = element_text(size = 9))

  base_out <- file.path(out_root, paste0(slug(nm), "__", verdict))
  save_fig(p, base_out, formats = c("png", "pdf"), width = 8, height = 8)
  n_ok <- n_ok + 1
}
log_msg(sprintf("per-species maps: %d written to %s", n_ok, out_root))