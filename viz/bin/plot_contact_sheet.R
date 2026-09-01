#!/usr/bin/env Rscript
# plot_contact_sheet.R — species-image contact sheets with citation capture.
#
# fig 07_species_contact_sheet — from species_images.csv (§11.9): one tile per
# species: photo + credit + SPDX license, colour-coded by flag; flagged/missing
# species render as explicit placeholder tiles (flags never silently drop).
#
# fig 08_genus_candidates_sheet — from candidate_images.csv (§11.10, v2.4.0):
# predicted (genus-narrow) candidate species; tiles labeled with candidate_of /
# candidate_rank. Quarantined imagery for genus-level hypotheses — tiles are
# labelled as candidates and never merge into the species layer.
#
# Usage:
#   Rscript bin/plot_contact_sheet.R --images <species_images.csv> \
#     [--candidate-images <candidate_images.csv>] --outdir <out> [--input-label l] [--cols 4]

suppressPackageStartupMessages({
  library(optparse); library(jsonlite); library(jpeg); library(grid)
})

script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

option_list <- list(
  make_option("--images", type = "character", default = NULL, help = "species_images.csv manifest (§11.9)"),
  make_option("--candidate-images", type = "character", default = NULL,
              help = "candidate_images.csv (§11.10) -> also renders fig/08_genus_candidates_sheet"),
  make_option("--outdir", type = "character", help = "viz output dir"),
  make_option("--config", type = "character", default = NULL, help = "run config (run_phase compat)"),
  make_option("--input-label", type = "character", default = NULL, help = "run label"),
  make_option("--cols", type = "integer", default = 4L, help = "grid columns (default 4)")
)
opt <- parse_args(OptionParser(option_list = option_list))
if (is.null(opt$outdir) || (is.null(opt$images) && is.null(opt$`candidate-images`)))
  stop("need --images (and/or --candidate-images) and --outdir", call. = FALSE)

`%||%` <- function(a, b) if (is.null(a) || is.na(a)) b else a
NICE <- c("cc-best" = "CC0 / CC-BY", "by-nc" = "CC (NC/ND terms)",
          "flag-no-license" = "no license", "flag-all-rights-reserved" = "all rights reserved",
          "flag-no-image" = "no image available", "flag-ambiguous-taxon" = "ambiguous taxon",
          "EMPTY" = "")
TILE_COL <- c("cc-best" = "#1a7a3a", "by-nc" = "#b8860b",
              "flag-no-license" = "#a04000", "flag-all-rights-reserved" = "#a04000",
              "flag-no-image" = "#8e44ad", "flag-ambiguous-taxon" = "#666666",
              "EMPTY" = "#444444")
lookup <- function(v, k, default) {
  k <- if (is.na(k) || k == "") "EMPTY" else k
  if (k %in% names(v)) v[[k]] else default
}
trunc <- function(s, w = 46) if (isTRUE(nchar(s) > w)) paste0(substr(s, 1, w - 1), "...") else s

outdir_fig <- file.path(opt$outdir, "fig")
dir.create(outdir_fig, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(opt$outdir, "work"), recursive = TRUE, showWarnings = FALSE)

render_sheet <- function(manifest_file, prefix, title_txt, is_candidate = FALSE) {
  manifest_path <- normalizePath(manifest_file, mustWork = TRUE)
  work_dir <- dirname(manifest_path)
  rows <- read.csv(manifest_path, stringsAsFactors = FALSE, colClasses = "character", na.strings = NULL)
  get_col <- function(df, nm, default = "") {
    if (nm %in% names(df)) { v <- df[[nm]]; v[is.na(v)] <- default; v } else rep(default, nrow(df))
  }
  img_col  <- get_col(rows, "local_file")
  flag_col <- get_col(rows, "flag")
  lic_col  <- get_col(rows, "license")
  cred_col <- get_col(rows, "attribution")
  src_col  <- get_col(rows, "source")
  cand_col <- get_col(rows, "candidate_display")
  cof_col  <- get_col(rows, "candidate_of")
  crank_col<- get_col(rows, "candidate_rank")

  n <- nrow(rows)
  label <- opt$`input-label` %||% "species reference images"

  draw_sheet <- function() {
    ncols <- max(1L, min(opt$cols %||% 4L, 6L)); nrows <- ceiling(n / ncols)
    cell_w <- 3.1; cell_h <- 2.7
    old <- par(mfrow = c(nrows, ncols), mar = c(0.3, 0.3, 1.1, 0.3),
               oma = c(1.8, 0.6, 2.2, 0.6), bg = "white", xpd = NA)
    on.exit(par(old), add = TRUE)
    for (i in seq_len(n)) {
      fl <- flag_col[i]
      plot.new(); plot.window(xlim = 0:1, ylim = 0:1)
      main_txt <- if (is_candidate) {
        bquote(italic(.(rows$scientificName[i])) ~
                 sprintf("  [candidate of %s, rank %s]", cof_col[i], crank_col[i]))
      } else {
        bquote(italic(.(gsub("_", " ", rows$scientificName[i]))))
      }
      title(main = main_txt, cex.main = 0.78, font.main = 3, line = 0.2)
      tile_col <- lookup(TILE_COL, fl, "#444444")
      img_path <- file.path(work_dir, img_col[i])
      if (nzchar(img_col[i]) && file.exists(img_path)) {
        img <- try(jpeg::readJPEG(img_path), silent = TRUE)
        if (!inherits(img, "try-error")) {
          d <- dim(img)
          step <- max(1L, min(as.integer(d[1] / 300), as.integer(d[2] / 300)) + 1L)
          small <- img[seq(1L, d[1], by = step), seq(1L, d[2], by = step), , drop = FALSE]
          rasterImage(as.raster(small), 0.03, 0.16, 0.97, 0.86)
        } else text(0.5, 0.5, "image decode failed", cex = 0.7, col = "#a04000")
      } else if (fl == "flag-ambiguous-taxon") {
        text(0.5, 0.5, "ambiguous taxon\n(review queue)", cex = 0.62, col = "#666666")
      } else {
        text(0.5, 0.5, if (nzchar(fl)) lookup(NICE, fl, fl) else "no image", cex = 0.62, col = "#8e44ad")
      }
      lic_line <- if (nzchar(lic_col[i])) lic_col[i] else if (nzchar(fl)) lookup(NICE, fl, fl) else "-"
      text(0.5, 0.105, labels = trunc(cred_col[i]), cex = 0.42, col = "#555555")
      text(0.5, 0.04,  labels = lic_line, cex = 0.46, col = tile_col)
      text(0.97, 0.93, labels = src_col[i], cex = 0.40, col = "#999999", adj = 1)
    }
    n_img <- sum(nzchar(img_col)); n_flag <- sum(grepl("^flag", flag_col))
    mtext(sprintf(title_txt, n, n_img, n_flag),
          outer = TRUE, side = 3, line = 0.8, cex = 1.05, font = 2)
    mtext("Photos reused under their stated licenses with creator attribution; flagged tiles are explicit by design (flags never silently drop).",
          outer = TRUE, side = 1, line = 0.5, cex = 0.55, col = "#555555")
    list(n = n, n_img = n_img, n_flag = n_flag)
  }

  dims <- local({
    r <- nrow(read.csv(manifest_path, stringsAsFactors = FALSE, colClasses = "character", na.strings = NULL))
    ncols <- max(1L, min(opt$cols %||% 4L, 6L))
    c(width = ceiling(r / ncols) * 0 + ncols * 3.1, height = ceiling(r / ncols) * 2.7 + 0.9)
  })
  png(file.path(outdir_fig, paste0(prefix, ".png")), width = dims[1], height = dims[2],
      units = "in", res = 150)
  st <- draw_sheet(); invisible(dev.off())
  pdf(file.path(outdir_fig, paste0(prefix, ".pdf")), width = dims[1], height = dims[2], onefile = TRUE)
  draw_sheet(); invisible(dev.off())

  out_rel <- c(paste0("fig/", prefix, ".png"), paste0("fig/", prefix, ".pdf"))
  fs_key <- if (is_candidate) "08_genus_candidates_sheet" else "07_species_contact_sheet"
  extra <- if (is_candidate) list(n_candidates = st$n, n_images = st$n_img, n_flagged = st$n_flag,
                                  outputs = out_rel)
           else list(n_species = st$n, n_images = st$n_img, n_flagged = st$n_flag, outputs = out_rel)
  log_msg(sprintf("%s: %d tiles (%d photos, %d flagged) -> %s.{png,pdf}", fs_key, st$n, st$n_img, st$n_flag, prefix))
  figure_status(opt$outdir, fs_key, "rendered", extra = extra)
  invisible(NULL)
}

if (!is.null(opt$images)) {
  lbl <- opt$`input-label` %||% "species reference images"
  render_sheet(opt$images, "07_species_contact_sheet",
               sprintf("Citable species images (%%s species · %%s photos embedded · %%s flagged) — %s", lbl),
               is_candidate = FALSE)
}
if (!is.null(opt$`candidate-images`)) {
  render_sheet(opt$`candidate-images`, "08_genus_candidates_sheet",
               "Genus-narrow candidate species predicted for genus-only ASV groups (%s candidates · %s photos · %s flagged) — hypotheses, NOT species identifications",
               is_candidate = TRUE)
}