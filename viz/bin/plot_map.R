#!/usr/bin/env Rscript
# plot_map.R — occurrence map (maps/ sub-skill worker).
#
# Reads any DwC-shaped table (PLAN §11.6), plots occurrence points on an
# rnaturalearth basemap (maps::map() fallback per geocurate_inventory.R), one
# panel per species (up to max_species) plus an all-species overview panel.
# Realm-independent: basemap + point colouring come from the run config.
#
# Usage:
#   Rscript bin/plot_map.R --input <file.parquet|csv> --config <run-config.json> \
#                          --outdir <dir> [--input-label <label>]

suppressPackageStartupMessages({
  library(optparse); library(ggplot2); library(sf); library(dplyr); library(patchwork)
})
script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

option_list <- list(
  make_option("--input", type = "character", help = "Occurrence table (parquet/csv/tsv)"),
  make_option("--config", type = "character", help = "Realm run config JSON"),
  make_option("--outdir", type = "character", default = ".", help = "Output directory"),
  make_option("--input-label", type = "character", default = NULL, help = "Dataset label for captions"),
  make_option("--overlay", type = "character", default = NULL,
              help = "Optional CSV of GBIF/OBIS context records plotted under detections")
)
opt <- parse_args(OptionParser(option_list = option_list))

cfg   <- read_run_config(opt$config)
df    <- load_input(opt$input)
validate_dwctable(df)

map_cfg <- cfg$map
if (is.null(map_cfg)) map_cfg <- list()

# ---- subsample (geocurate pattern: cap + fixed seed) ----
max_pts <- if (!is.null(map_cfg$max_points)) map_cfg$max_points else 20000
sub <- subsample_points(df, max_pts)
dfp <- sub$df
if (sub$subsampled) {
  log_msg(sprintf("subsampled %d -> %d points (seed 42) for map clarity", sub$n_original, nrow(dfp)))
}

formats <- if (!is.null(cfg$output_formats)) cfg$output_formats else c("png", "pdf")
fill_scale <- make_fill_scale(if (!is.null(map_cfg$palette)) map_cfg$palette else "viridis",
                              discrete = TRUE, name = "Species")

sp_name <- "scientificName"
n_species <- length(unique(na.omit(dfp[[sp_name]])))
top_n <- if (!is.null(map_cfg$max_species)) map_cfg$max_species else 12

dfp_overlay <- NULL
if (!is.null(opt$overlay) && file.exists(opt$overlay)) {
  ovl <- read.csv(opt$overlay, stringsAsFactors = FALSE)
  ovl$decimalLatitude <- as.numeric(ovl$decimalLatitude)
  ovl$decimalLongitude <- as.numeric(ovl$decimalLongitude)
  ovl <- ovl[!is.na(ovl$decimalLatitude) & !is.na(ovl$decimalLongitude), , drop = FALSE]
  if (nrow(ovl) > 0) {
    message(sprintf("[occurrence-viz] overlay: %d context records from %s", nrow(ovl), basename(opt$overlay)))
    dfp_overlay <- ovl
  }
}

# ---- extent ----
bbox_pad <- 0.10
if (!is.null(map_cfg$bbox)) {
  xlim <- map_cfg$bbox[c(1, 3)]; ylim <- map_cfg$bbox[c(2, 4)]
} else {
  rx <- range(dfp$decimalLongitude, na.rm = TRUE); ry <- range(dfp$decimalLatitude, na.rm = TRUE)
  pad_x <- max(diff(rx) * bbox_pad, 1); pad_y <- max(diff(ry) * bbox_pad, 1)
  xlim <- c(rx[1] - pad_x, rx[2] + pad_x); ylim <- c(ry[1] - pad_y, ry[2] + pad_y)
}
if (!is.null(dfp_overlay) && nrow(dfp_overlay) > 0) {
  xlim <- range(c(xlim, range(dfp_overlay$decimalLongitude, na.rm = TRUE)))
  ylim <- range(c(ylim, range(dfp_overlay$decimalLatitude, na.rm = TRUE)))
  # modest padding so edge context records aren't clipped
  m <- 0.05 * max(diff(xlim), diff(ylim)); xlim <- xlim + c(-m, m); ylim <- ylim + c(-m, m)
}
crop_bbox <- sf::st_bbox(c(xmin = xlim[1], ymin = ylim[1], xmax = xlim[2], ymax = ylim[2]), crs = 4326)

coast <- get_coastline(coast_choice = if (!is.null(map_cfg$coastline)) map_cfg$coastline else "auto",
                       scale = if (!is.null(map_cfg$coast_scale)) map_cfg$coast_scale else "medium")

base_layer <- function() {
  l <- list()
  if (!is.null(coast)) {
    cw <- safe_crop_coast(coast, crop_bbox)
    l[[length(l) + 1]] <- geom_sf(data = cw, fill = "grey90", colour = "grey55", size = 0.2)
  }
  l
}

theme_viz <- theme_bw(base_size = 11) +
  theme(panel.grid = element_line(colour = "grey92", linewidth = 0.3),
        strip.text = element_text(face = "italic", size = 8))

# ---- figure 01: all-species occurrence map (points coloured by species) ----

p_overview <- ggplot() +
  base_layer() +
  {if (!is.null(dfp_overlay) && nrow(dfp_overlay) > 0)
    geom_point(data = dfp_overlay, aes(x = decimalLongitude, y = decimalLatitude),
               shape = 21, fill = "#7f8c9c", colour = "grey30", size = 1.1, alpha = 0.55, stroke = 0.25) else NULL} +
  geom_point(data = dfp, aes(x = decimalLongitude, y = decimalLatitude,
                             colour = .data[[sp_name]]), size = 1.6, alpha = 0.85) +
  fill_scale +
  coord_sf(xlim = xlim, ylim = ylim, expand = FALSE) +
  labs(title = wrap_title(sprintf("Occurrence records%s%s",
                       if (sub$subsampled) sprintf(" (subsampled %s of %s)", format(nrow(dfp), big.mark = ","), format(sub$n_original, big.mark = ",")) else "",
                       if (is.null(opt$`input-label`)) "" else paste0(" — ", opt$`input-label`))),
       subtitle = wrap_title(sprintf("%s species · %s points%s · realm: %s", n_species, format(nrow(dfp), big.mark = ","),
                   if (!is.null(dfp_overlay) && nrow(dfp_overlay) > 0) sprintf(" · overlay: %s context records (GBIF/OBIS)", format(nrow(dfp_overlay), big.mark = ",")) else "",
                   cfg$realm)),
       x = "Longitude", y = "Latitude", colour = "Species") +
  theme_viz +
  # v1.0.3: legend SHOWN on the all-species overview (was suppressed; without it the
  # colour -> species mapping is unreadable). Italic species keys, right side.
  theme(legend.position = "right",
        legend.title = element_text(face = "bold", size = 9),
        legend.text = element_text(face = "italic", size = 8))

fig01 <- tryCatch({
  out_files <- save_fig(p_overview, file.path(opt$outdir, "fig", "01_occurrence_map"), formats = formats,
                        width = 9, height = 6)
  dir.create(file.path(opt$outdir, "work", "plots"), recursive = TRUE, showWarnings = FALSE)
  saveRDS(p_overview, file.path(opt$outdir, "work", "plots", "01_occurrence_map.rds"))
  figure_status(opt$outdir, "01_occurrence_map", "rendered",
                extra = list(points = nrow(dfp), n_original = sub$n_original, subsampled = sub$subsampled,
                             n_species = n_species, coastline = if (is.null(coast)) "none" else "sf",
                             outputs = out_files))
  TRUE
}, error = function(e) { figure_status(opt$outdir, "01_occurrence_map", "skipped", e$message); FALSE })

# ---- figure 02: small-multiples per species (up to top_n species) ----
fig02 <- FALSE
sp_counts <- dfp %>% group_by(.data[[sp_name]]) %>% summarise(n = dplyr::n()) %>%
  arrange(desc(n)) %>% slice_head(n = top_n)
if (nrow(sp_counts) > 1) {
  keep_sps <- sp_counts[[sp_name]]
  dfs <- dfp[dfp[[sp_name]] %in% keep_sps, , drop = FALSE]
  p_facet <- ggplot() +
    base_layer() +
    geom_point(data = dfs, aes(x = decimalLongitude, y = decimalLatitude), colour = "#1f77b4",
               size = 0.8, alpha = 0.55) +
    coord_sf(xlim = xlim, ylim = ylim, expand = FALSE) +
    facet_wrap(sp_name, ncol = 4, labeller = labeller(.default = label_wrap_gen(24))) +
    labs(subtitle = sprintf("Top %d species by record count", nrow(sp_counts)),
         x = "Longitude", y = "Latitude") +
    theme_viz
  fig02 <- tryCatch({
    out_files <- save_fig(p_facet, file.path(opt$outdir, "fig", "02_species_maps"), formats = formats,
                          width = 11, height = max(3.2, 0.9 * ceiling(nrow(sp_counts) / 4) + 2))
    dir.create(file.path(opt$outdir, "work", "plots"), recursive = TRUE, showWarnings = FALSE)
    saveRDS(p_facet, file.path(opt$outdir, "work", "plots", "02_species_maps.rds"))
    figure_status(opt$outdir, "02_species_maps", "rendered",
                  extra = list(species = keep_sps, n_species = length(keep_sps),
                               points = nrow(dfs), outputs = out_files))
    TRUE
  }, error = function(e) { figure_status(opt$outdir, "02_species_maps", "skipped", e$message); FALSE })
} else {
  figure_status(opt$outdir, "02_species_maps", "skipped",
                sprintf("only %d distinct species; single-species map redundant with overview", n_species))
}

# ---- per-species map files: one file per species (default on; opt out via
# map.per_species_files: false in the run config) — separate from fig02's
# combined small-multiples panel, which stays for backwards-compatible overview use.
n_per_species <- 0
if (!identical(map_cfg$per_species_files, FALSE)) {
  per_dir <- file.path(opt$outdir, "fig", "per_species")
  dir.create(per_dir, recursive = TRUE, showWarnings = FALSE)
  slug <- function(x) gsub("[^A-Za-z0-9._-]+", "_", x)
  for (nm in sort(unique(na.omit(dfp[[sp_name]])))) {
    dsp <- dfp[dfp[[sp_name]] == nm, , drop = FALSE]
    p_sp <- ggplot() +
      base_layer() +
      geom_point(data = dsp, aes(x = decimalLongitude, y = decimalLatitude),
                 colour = "#1f77b4", size = 1.4, alpha = 0.75) +
      coord_sf(xlim = xlim, ylim = ylim, expand = FALSE) +
      labs(title = wrap_title(nm),
           subtitle = sprintf("%s record%s", format(nrow(dsp), big.mark = ","), if (nrow(dsp) == 1) "" else "s"),
           x = "Longitude", y = "Latitude") +
      theme_viz + theme(plot.title = element_text(face = "italic"))
    out_files <- save_fig(p_sp, file.path(per_dir, slug(nm)), formats = formats, width = 7, height = 5.5)
    figure_status(opt$outdir, sprintf("per_species_%s", slug(nm)), "rendered",
                  extra = list(species = nm, points = nrow(dsp), outputs = out_files))
    n_per_species <- n_per_species + 1
  }
  log_msg(sprintf("per-species maps: %d files written to fig/per_species/", n_per_species))
}

onland_note <- if (!is.null(cfg$qc) && isTRUE(cfg$qc$onland_flagged)) {
  "NOTE: marine realm — verify visually that no occurrence points fall on land (check_onland logic lives in edna-crosscheck; this map is the visual sanity check)."
} else NULL
if (!is.null(onland_note)) log_msg(onland_note)

log_msg(sprintf("maps phase done (fig01=%s, fig02=%s, per_species=%d)", fig01, fig02, n_per_species))