# /usr/bin/env Rscript
# lib_viz.R — shared helpers for the occurrence-viz skill (sourced by bin/*.R scripts).
#
# Conventions inherited from the workspace's AMPLICON/bin/geocurate_inventory.R:
#   * fixed-seed (42) point subsampling for large occurrence tables (map_points_max)
#   * coastline fallback chain: rnaturalearth (medium, 1:50m from rnaturalearthdata)
#     -> maps::map("world") repackaged as sf -> bare frame (no coastline)
#   * fully offline: no API calls, no tile servers.
# Realm-awareness lives in the run-config JSON (config/run-config.<realm>.json),
# NEVER in per-call if(realm==...) branching inside plotting code.

suppressPackageStartupMessages({
  library(jsonlite)
})

VIZ_LOG_PREFIX <- "[occurrence-viz]"
log_msg <- function(...) cat(sprintf("%s %s\n", VIZ_LOG_PREFIX, paste0(...)))
warn_msg <- function(...) cat(sprintf("%s WARNING: %s\n", VIZ_LOG_PREFIX, paste0(...)))

# --------------------------------------------------------------------- proj init
# conda-forge proj >= 9.x no longer ships conda activate scripts, so PROJ_DATA is
# not set automatically and sf/ggplot2 geom_sf rendering fails with
#   "GDAL Error 1: PROJ: proj_create_from_database: Open of <env>/share/proj failed"
# Resolve PROJ_DATA from the running env prefix (derived from the sf install path)
# when unset. Safe no-op when already configured.
.proj_data_init <- function() {
  if (nzchar(Sys.getenv("PROJ_DATA"))) return(invisible(FALSE))
  sf_lib <- system.file(package = "sf")               # .../envs/<env>/lib/R/library/sf
  if (!nzchar(sf_lib)) return(invisible(FALSE))
  prefix <- normalizePath(file.path(sf_lib, "..", "..", "..", ".."), winslash = "/", mustWork = FALSE)
  pd <- file.path(prefix, "share", "proj")
  if (file.exists(file.path(pd, "proj.db"))) {
    Sys.setenv(PROJ_DATA = pd, PROJ_LIB = pd)          # PROJ_LIB kept for older libs
    return(invisible(TRUE))
  }
  invisible(FALSE)
}
.proj_data_init()

# ---------------------------------------------------------------- input loading

#' Load an occurrence table (parquet via arrow, or CSV/TSV via readr).
#' Plain obis-gbif-fetch parquet and edna-crosscheck enriched.parquet both work.
load_input <- function(path) {
  if (!file.exists(path)) {
    stop(sprintf("input file does not exist: %s", path), call. = FALSE)
  }
  ext <- tolower(tools::file_ext(path))
  df <- switch(ext,
    parquet = {
      if (!requireNamespace("arrow", quietly = TRUE)) {
        stop("arrow package required for parquet input (pixi.toml installs r-arrow).", call. = FALSE)
      }
      as.data.frame(arrow::read_parquet(path))
    },
    csv = as.data.frame(readr::read_csv(path, show_col_types = FALSE)),
    tsv = as.data.frame(readr::read_tsv(path, show_col_types = FALSE)),
    stop(sprintf("unsupported input extension '%s' (use parquet | csv | tsv)", ext), call. = FALSE)
  )
  log_msg(sprintf("loaded %d rows x %d cols from %s", nrow(df), ncol(df), path))
  df
}

# Required DwC columns per PLAN §11.6 (standalone input contract)
DWC_REQUIRED <- c("scientificName", "decimalLatitude", "decimalLongitude", "eventDate")

#' Minimal-DwC validation. Returns invisibly; stops on missing required columns.
validate_dwctable <- function(df) {
  miss <- setdiff(DWC_REQUIRED, names(df))
  if (length(miss) > 0) {
    stop(sprintf(
      "input violates PLAN §11.6 contract — missing required DwC column(s): %s (present: %s)",
      paste(miss, collapse = ", "), paste(names(df), collapse = ", ")
    ), call. = FALSE)
  }
  df$decimalLatitude  <- suppressWarnings(as.numeric(df$decimalLatitude))
  df$decimalLongitude <- suppressWarnings(as.numeric(df$decimalLongitude))
  bad <- is.na(df$decimalLatitude) | is.na(df$decimalLongitude) |
    df$decimalLatitude < -90 | df$decimalLatitude > 90 |
    df$decimalLongitude < -180 | df$decimalLongitude > 180
  if (any(bad)) {
    warn_msg(sprintf("dropping %d row(s) with invalid/out-of-range coordinates", sum(bad)))
    df <- df[!bad, , drop = FALSE]
  }
  if (nrow(df) == 0) stop("no rows with valid coordinates after validation", call. = FALSE)
  invisible(TRUE)
}

#' True if ALL columns present.
has_cols <- function(df, cols) all(cols %in% names(df))

#' First column from `candidates` present in df, else NULL.
first_col <- function(df, candidates) {
  hit <- vapply(candidates, function(c) c %in% names(df), logical(1))
  if (!any(hit)) NULL else candidates[which(hit)[1]]
}

# ------------------------------------------------------- geocurate pattern: subsample

#' Random subsample of points above max_points, seed fixed at 42 (geocurate pattern).
subsample_points <- function(df, max_points, seed = 42) {
  n <- nrow(df)
  if (is.null(max_points) || is.na(max_points) || max_points <= 0 || n <= max_points) {
    return(list(df = df, n_original = n, subsampled = FALSE))
  }
  set.seed(seed)
  keep <- sample.int(n, max_points)
  list(df = df[keep, , drop = FALSE], n_original = n, subsampled = TRUE)
}

# ------------------------------------------------------------- basemap fallback

#' Basemap polygons: rnaturalearth (medium 1:50m via rnaturalearthdata) ->
#' maps::map("world") -> NULL (bare frame). Mirrors geocurate `--map_coastline auto`.
#' scale in {small, medium, large} (large only with rnaturalearthhires installed).
get_coastline <- function(coast_choice = "auto", scale = "medium") {
  rne_ok <- requireNamespace("rnaturalearth", quietly = TRUE) &&
            requireNamespace("rnaturalearthdata", quietly = TRUE)
  use <- coast_choice
  if (use == "auto") use <- if (rne_ok) "rnaturalearth" else if (requireNamespace("maps", quietly = TRUE)) "maps" else "none"
  if (use == "rnaturalearth" && !rne_ok) {
    warn_msg("rnaturalearth(-data) not available; falling back to maps::map().")
    use <- if (requireNamespace("maps", quietly = TRUE)) "maps" else "none"
  }
  log_msg(sprintf("coastline source: %s", use))
  if (use == "rnaturalearth") {
    tryCatch(rnaturalearth::ne_countries(scale = scale, returnclass = "sf"),
             error = function(e) {
               warn_msg(sprintf("ne_countries failed (%s); falling back to maps::map().", e$message))
               NULL
             })
  } else if (use == "maps") {
    tryCatch(sf::st_as_sf(maps::map("world", plot = FALSE, fill = TRUE)),
             error = function(e) { warn_msg("maps::map fallback failed."); NULL })
  } else NULL
}

#' Crop coastline polygons to bbox, guarding a confirmed sf 1.1.2 bug: when the
#' bbox longitude span exceeds 180 deg, st_crop()/st_intersection() misread it
#' as antimeridian-crossing and silently drop most/all continents (st_area of
#' the result can be <5% of the true intersecting area) even though no error
#' is raised. st_intersects() (predicate only) is unaffected, so use it to
#' select features and skip the buggy clip for wide boxes instead of risking
#' silent data loss.
safe_crop_coast <- function(coast, bbox) {
  if (is.null(coast)) return(NULL)
  keep <- lengths(sf::st_intersects(coast, sf::st_as_sfc(bbox))) > 0
  cw <- coast[keep, , drop = FALSE]
  span <- unname(bbox["xmax"] - bbox["xmin"])
  if (is.na(span) || span > 180) {
    if (!is.na(span) && span > 180) warn_msg(sprintf(
      "bbox longitude span %.0f deg > 180; st_crop() silently drops large polygons at this span (known sf bug) — using unclipped intersecting features instead.",
      span))
    return(cw)
  }
  tryCatch(sf::st_crop(cw, bbox), error = function(e) cw)
}

#' Wrap long title/subtitle text onto multiple lines so it doesn't bleed past
#' the plot edge — ggplot2 does not auto-wrap plot.title/subtitle text.
wrap_title <- function(txt, width = 62) paste(strwrap(txt, width = width), collapse = "\n")

# ------------------------------------------------------------------ run config

#' Read + validate the realm run config (config/run-config.<realm>.json).
read_run_config <- function(path) {
  cfg <- jsonlite::fromJSON(path, simplifyVector = TRUE)
  for (k in c("realm", "figures")) {
    if (is.null(cfg[[k]])) stop(sprintf("run config missing required key '%s'", k), call. = FALSE)
  }
  if (!cfg$realm %in% c("marine", "freshwater", "terrestrial")) {
    stop(sprintf("run config realm '%s' not in {marine, freshwater, terrestrial}", cfg$realm), call. = FALSE)
  }
  cfg
}

# ------------------------------------------------------------------- palettes

#' Parse palette spec "scico:<name>" | "viridis" | "viridis:<name>" into a
#' ggplot2 scale function; falls back gracefully.
make_fill_scale <- function(palette_spec, discrete = TRUE, direction = 1, name = "") {
  parts <- strsplit(palette_spec, ":", fixed = TRUE)[[1]]
  pkg <- parts[1]
  pal <- if (length(parts) > 1) parts[2] else NULL
  out <- tryCatch({
    if (pkg == "scico" && requireNamespace("scico", quietly = TRUE)) {
      fun <- if (discrete) scico::scale_fill_scico_d else scico::scale_fill_scico
      fun(palette = if (is.null(pal)) "batlow" else pal, direction = direction, name = name)
    } else if (pkg %in% c("viridis", "viridisLite")) {
      # _d variants are native ggplot2 exports (the viridis pkg itself only ships _c/_b)
      opt <- if (is.null(pal)) "viridis" else pal
      ggplot2::scale_fill_viridis_d(option = opt, direction = direction, name = name, begin = 0.1, end = 0.9)
    } else stop(sprintf("unknown palette spec: %s", palette_spec), call. = FALSE)
  }, error = function(e) {
    warn_msg(sprintf("palette '%s' unavailable (%s); using default ggplot2 palette.", palette_spec, e$message))
    NULL
  })
  out
}

# ------------------------------------------------------------------ output helper

#' Save a ggplot in every configured format. formats: subset of
#' c("png","pdf","svg"); png rendered at `dpi` (default 300); pdf via cairo_pdf
#' (vector, fonts embedded); svg only when the svglite package is available.
save_fig <- function(p, out_base, formats = c("png", "pdf"), width = 10, height = 7, dpi = 300) {
  dir.create(dirname(out_base), recursive = TRUE, showWarnings = FALSE)
  written <- c()
  for (fmt in formats) {
    if (fmt == "svg" && !requireNamespace("svglite", quietly = TRUE)) {
      warn_msg("svg requested but 'svglite' not installed; skipping svg output.")
      next
    }
    path <- sprintf("%s.%s", out_base, fmt)
    tryCatch({
      ggsave(path, p, width = width, height = height, units = "in", dpi = dpi,
             device = switch(fmt, png = "png", pdf = cairo_pdf, svg = svglite::svglite))
      written <- c(written, path)
      log_msg(sprintf("wrote %s", path))
    }, error = function(e) warn_msg(sprintf("failed to write %s: %s", path, e$message)))
  }
  written
}

# -------------------------------------------------------------- figure status log

#' Append a per-figure status record (rendered / skipped + reason) — consumed by
#' bin/build_report.R for the captions manifest. Thread-safe enough via appendJsonLines.
figure_status <- function(outdir, figure, status, reason = "", file_path = "", extra = list()) {
  dir.create(file.path(outdir, "work"), recursive = TRUE, showWarnings = FALSE)
  rec <- list(
    figure = figure, status = status, reason = reason, file = file_path,
    extra = extra, timestamp = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z")
  )
  line <- jsonlite::toJSON(rec, auto_unbox = TRUE)
  cat(line, "\n", sep = "", file = file.path(outdir, "work", "figure_status.jsonl"), append = TRUE)
  invisible(TRUE)
}

# ---- v2.5.0 / v1.6.0: habitat + IUCN render helpers (§11.11) ------------------
IUCN_TILE_COL <- c(
  "LC" = "#1a7a3a", "NT" = "#7fa845", "VU" = "#d98e04", "EN" = "#d14444",
  "CR" = "#8e2a2a", "EX" = "#111111", "EW" = "#444444",
  "DD" = "#777777", "NE" = "#9aa7b0", EMPTY = "#9aa7b0")
IUCN_LABEL <- c(LC = "LC Least Concern", NT = "NT Near Threatened", VU = "VU Vulnerable",
                EN = "EN Endangered", CR = "CR Critically Endangered",
                EX = "EX Extinct", EW = "EW Extinct in the Wild",
                DD = "DD Data Deficient", NE = "NE Not Evaluated")

load_habitat_manifest <- function(path) {
  if (is.null(path) || !nzchar(path) || !file.exists(path)) return(NULL)
  m <- read.csv(path, stringsAsFactors = FALSE, colClasses = "character")
  m
}

# single-line habitat+iucn annotation for one taxon; NA-safe
habitat_iucn_note <- function(m, name) {
  if (is.null(m)) return("")
  r <- m[m$scientificName == name, , drop = FALSE]
  if (nrow(r) == 0) return("")
  hab <- if (nzchar(r$habitat[1]) && !grepl("^flag:", r$habitat[1]))
    sprintf("habitat %s", gsub("/", " / ", r$habitat[1])) else ""
  iucn <- if (nzchar(r$iucn_category[1]) && !grepl("^flag:", r$iucn_category[1]))
    sprintf("IUCN %s", r$iucn_category[1]) else ""
  paste(c(hab, iucn), collapse = " \u00b7 ")
}

iucn_col_for <- function(m, name) {
  if (is.null(m)) return("#9aa7b0")
  r <- m[m$scientificName == name, , drop = FALSE]
  if (nrow(r) == 0 || !r$iucn_code[1] %in% names(IUCN_TILE_COL)) return("#9aa7b0")
  IUCN_TILE_COL[[r$iucn_code[1]]]
}
