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
})

script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

`%||%` <- function(a, b) if (is.null(a) || (length(a) == 1 && is.na(a) && !is.logical(a))) b else a

opt <- parse_args(OptionParser(option_list = list(
  make_option("--input", type = "character", help = "enriched.parquet (§11.2)"),
  make_option("--overlay", type = "character", help = "context_occurrences.csv (GBIF/OBIS backdrop)"),
  make_option("--params", type = "character", help = "crosscheck params.json"),
  make_option("--counts", type = "character", default = "work/occurrence_counts.json",
              help = "occurrence_counts.json from the crosscheck run"),
  make_option("--outdir", type = "character", default = "species_maps"),
  make_option("--buffer-km", type = "numeric", default = NULL,
              help = "buffer radius override; default = params.json buffer km"),
  make_option("--label", type = "character", default = "eDNA detections"),
  make_option("--max-species", type = "numeric", default = 200)
)))

for (f in c(opt$input, opt$overlay, opt$params))
  if (!file.exists(f)) stop(sprintf("plot_per_species: not found: %s", f), call. = FALSE)

df <- load_input(opt$input)
df$decimalLatitude  <- as.numeric(df$decimalLatitude)
df$decimalLongitude <- as.numeric(df$decimalLongitude)
df$trait_depth_min_m <- as.numeric(df$trait_depth_min_m)
df$trait_depth_max_m <- as.numeric(df$trait_depth_max_m)

params <- jsonlite::fromJSON(opt$params)
counts <- if (file.exists(opt$counts)) jsonlite::fromJSON(opt$counts) else list()

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

species <- sort(unique(na.omit(df$scientificName)))
species <- head(species, opt[["max-species"]])
n_ok <- 0

for (nm in species) {
  det <- df[df$scientificName == nm & !is.na(df$decimalLatitude), , drop = FALSE]
  ctx <- ctx_all[ctx_all$key == binom_key(nm), , drop = FALSE]
  e <- counts[[nm]]
  gb <- if (!is.null(e$gbif)) e$gbif else 0L
  ob <- if (!is.null(e$obis)) e$obis else 0L
  n_cor <- sum(c(gb, ob), na.rm = TRUE)
  verdict <- if (n_cor > 0) "EXPECTED" else "UNEXPECTED"
  col_det <- if (n_cor > 0) "#2c6ea3" else "#e84393"

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
    labs(title = nm,
         subtitle = sprintf(
           "%s: %s — %s GBIF · %s OBIS records inside the %s km buffer%s",
           opt$label, verdict,
           format(gb, big.mark = ","), format(ob, big.mark = ","),
           format(buffer_km, big.mark = ","), depth_note),
         x = "Longitude", y = "Latitude",
         caption = sprintf("pink diamond = eDNA detection site · grey = GBIF/OBIS known occurrences · dashed ring = %s km buffer · %s",
                           format(buffer_km, big.mark = ","), opt$label)) +
    theme_bw(base_size = 10) +
    theme(panel.grid = element_line(colour = "grey92", linewidth = 0.25),
          plot.title = element_text(face = "italic", size = 12),
          plot.subtitle = element_text(size = 9))

  base_out <- file.path(out_root, paste0(slug(nm), "__", verdict))
  save_fig(p, base_out, formats = c("png", "pdf"), width = 8, height = 8)
  n_ok <- n_ok + 1
}
log_msg(sprintf("per-species maps: %d written to %s", n_ok, out_root))