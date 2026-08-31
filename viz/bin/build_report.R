#!/usr/bin/env Rscript
# build_report.R — multi-panel report + captions manifest (report/ sub-skill worker).
#
# Reads work/figure_status.jsonl written by plot_map.R / plot_profiles.R and:
#   1. assembles a multi-panel summary figure (fig/06_multispecies_overview.png+pdf)
#      from the saved ggplot .rds snapshots (work/plots/*.rds) via patchwork,
#   2. writes fig/figure-captions.md — the auto-generated figure captions manifest,
#   3. writes figure-report.md — run summary (input, realm, figures rendered/skipped).
#
# Usage:
#   Rscript bin/build_report.R --config <run-config.json> --outdir <dir> [--input <file>] [--input-label <label>]

suppressPackageStartupMessages({
  library(optparse); library(jsonlite); library(patchwork); library(ggplot2)
})
script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

option_list <- list(
  make_option("--config", type = "character", help = "Realm run config JSON"),
  make_option("--outdir", type = "character", default = ".", help = "Output directory"),
  make_option("--input", type = "character", default = NULL, help = "Input table path (report header)"),
  make_option("--input-label", type = "character", default = NULL, help = "Dataset label")
)
opt <- parse_args(OptionParser(option_list = option_list))

cfg <- read_run_config(opt$config)
status_file <- file.path(opt$outdir, "work", "figure_status.jsonl")

statuses <- if (file.exists(status_file)) {
  lines <- readLines(status_file, warn = FALSE)
  lines <- lines[nzchar(trimws(lines))]
  do.call(rbind, lapply(lines, function(l) {
    rec <- tryCatch(fromJSON(l, simplifyVector = FALSE), error = function(e) NULL)
    if (is.null(rec)) return(NULL)
    g1 <- function(k) { v <- rec[[k]]; if (is.null(v) || length(v) == 0) "" else paste(as.character(v), collapse = ";") }
    data.frame(figure = g1("figure"), status = g1("status"), reason = g1("reason"),
               file = g1("file"), stringsAsFactors = FALSE)
  }))
} else NULL

if (is.null(statuses) || nrow(statuses) == 0) stop("work/figure_status.jsonl empty or unparseable — rerun maps + profiles phases.", call. = FALSE)

# keep the LAST status per figure (reruns append several records)
statuses$idx <- seq_len(nrow(statuses))
statuses <- do.call(rbind, lapply(split(statuses, statuses$figure), function(g) g[which.max(g$idx), ]))

rendered <- statuses[statuses$status == "rendered", , drop = FALSE]
skipped  <- statuses[statuses$status != "rendered", , drop = FALSE]
log_msg(sprintf("status ledger: %d rendered, %d skipped", nrow(rendered), nrow(skipped)))

# ---------------------------------------------------------------- multi-panel figure
fig06_files <- character(0)
rds_dir <- file.path(opt$outdir, "work", "plots")
if (dir.exists(rds_dir)) {
  rds_files <- sort(list.files(rds_dir, pattern = "\\.rds$", full.names = TRUE))
  panels <- list(); panel_names <- c()
  for (f in rds_files) {
    obj <- tryCatch(readRDS(f), error = function(e) NULL)
    if (!is.null(obj) && inherits(obj, "ggplot")) {
      panels[[length(panels) + 1]] <- obj
      panel_names <- c(panel_names, gsub("\\.rds$", "", basename(f)))
    }
  }
  if (length(panels) >= 2) {
    # drop the facet-grid panel from the combo when it would dominate layout
    use_idx <- if ("02_species_maps" %in% panel_names && length(panels) > 2) {
      which(panel_names != "02_species_maps")
    } else seq_along(panels)
    final_names  <- panel_names[use_idx]
    combo_height <- min(24, 5.2 * length(use_idx))
    combo <- patchwork::wrap_plots(panels[use_idx], ncol = 1) +
      patchwork::plot_annotation(
        title = sprintf("occurrence-viz overview — realm: %s", cfg$realm),
        theme = theme_bw(base_size = 12))
    fig06_files <- save_fig(combo, file.path(opt$outdir, "fig", "06_multispecies_overview"),
                            formats = if (!is.null(cfg$output_formats)) cfg$output_formats else c("png", "pdf"),
                            width = 10, height = combo_height)
    saveRDS(combo, file.path(rds_dir, "06_multispecies_overview.rds"))
    figure_status(opt$outdir, "06_multispecies_overview", "rendered",
                  extra = list(panels = final_names, outputs = fig06_files))
  } else {
    figure_status(opt$outdir, "06_multispecies_overview", "skipped",
                  sprintf("only %d saved panel(s); need >= 2 ggplot objects for a multi-panel figure", length(panels)))
  }
} else {
  figure_status(opt$outdir, "06_multispecies_overview", "skipped", "work/plots/ missing — plotting workers did not run")
}

# ---------------------------------------------------------------- captions manifest
label <- if (!is.null(opt$`input-label`)) opt$`input-label` else (if (!is.null(opt$input)) basename(opt$input) else "n/a")
fmt_num <- function(n) format(as.numeric(n), big.mark = ",")
dir.create(file.path(opt$outdir, "fig"), recursive = TRUE, showWarnings = FALSE)
captions <- c(
  "# Figure captions manifest — occurrence-viz",
  sprintf("Run: %s · realm: **%s** · generated: %s", label, cfg$realm, format(Sys.time(), "%Y-%m-%d %H:%M %Z")),
  "",
  "Auto-generated by the `report/` sub-skill (bin/build_report.R). Captions are starting points for publication — edit freely.",
  ""
)
fmt_num <- function(n) format(as.numeric(n), big.mark = ",")
fig_num <- 1
for (i in seq_len(nrow(rendered))) {
  r <- rendered[i, ]
  ex <- r$extra
  exg <- function(k) { v <- ex[[k]]; ifelse(is.null(v), NA, v) }
  cap <- switch(as.character(r$figure),
    "01_occurrence_map" = sprintf("**Figure %d.** Occurrence records for %s (%s points shown%s; %s distinct species). Basemap: rnaturalearth (medium, 1:50m) or maps::map() fallback, per the geocurate pattern.",
                                  fig_num, label,
                                  ifelse(is.na(exg("points")), "?", fmt_num(exg("points"))),
                                  ifelse(isTRUE(as.logical(exg("subsampled"))), sprintf(" — random subsample of %s records", exg("n_original")), ""),
                                  ifelse(is.na(exg("n_species")), "?", exg("n_species"))),
    "02_species_maps"   = sprintf("**Figure %d.** Per-species occurrence maps for the top-record-count species (small multiples).", fig_num),
    "03_env_profile"    = sprintf("**Figure %d.** Occurrence distribution along `%s` (x-axis: %s). Realm-routed profile: marine \u2192 depth, freshwater/terrestrial \u2192 elevation/bioclim — identical plotting code, variable chosen by run config.",
                                  fig_num, exg("x_column"),
                                  if (is.null(cfg$profiles)) "value" else if (is.null(cfg$profiles$x_label)) "value" else cfg$profiles$x_label),
    "04_env_envelope"   = sprintf("**Figure %d.** Environmental envelopes per species across %s (points = records; pointrange = mean \u00b1 95%% CI). Envelope *flags* are computed upstream by edna-crosscheck; this figure plots observations only, it never flags.",
                                  fig_num,
                                  ifelse(is.null(exg("variables")), "?", paste(unlist(exg("variables")), collapse = ", ", sep = ""))),
    "05_trait_space"    = sprintf("**Figure %d.** Trait space: `%s` vs `%s` (FishBase traits from enriched crosscheck output; optional per PLAN \u00a711.6).",
                                  fig_num, exg("x"), exg("y")),
    "06_multispecies_overview" = sprintf("**Figure %d.** Multi-panel overview combining %s.", fig_num,
                                  ifelse(is.null(exg("panels")), "?", paste(unlist(exg("panels")), collapse = " + "))),
    sprintf("**Figure %d.** %s", fig_num, as.character(r$figure))
  )
  files <- unlist(r$file); files <- if (is.null(files)) unlist(exg("outputs")) else files
  files <- files[!is.na(files) & nzchar(files)]
  n_shown <- if (!is.null(exg("n_used"))) fmt_num(exg("n_used")) else if (!is.null(exg("points"))) fmt_num(exg("points")) else "n/a"
  captions <- c(captions,
    sprintf("### fig/%s", sub("\\.(png|pdf|svg)$", "", basename(as.character(r$figure)))),
    sprintf("- %s", cap),
    sprintf("- files: %s", paste(paste0("`", files, "`"), collapse = ", ")),
    sprintf("- records represented: %s", n_shown),
    "")
  fig_num <- fig_num + 1
}
n_rendered_figs <- fig_num - 1

writeLines(captions, file.path(opt$outdir, "fig", "figure-captions.md"))

# ---------------------------------------------------------------- report markdown
report <- c(
  "# occurrence-viz figure report",
  "",
  sprintf("- input: `%s`", if (is.null(opt$input)) "n/a" else opt$input),
  sprintf("- label: %s", label),
  sprintf("- realm: **%s** (routed via `%s`)", cfg$realm, opt$config),
  sprintf("- figures rendered: %d  · skipped: %d", nrow(rendered), nrow(skipped)),
  ""
)
if (nrow(skipped) > 0) {
  report <- c(report, "## Skipped figures (graceful absence per PLAN §11.6)", "")
  for (i in seq_len(nrow(skipped))) {
    reason <- skipped$reason[[i]]
    report <- c(report, sprintf("- `%s`: %s", skipped$figure[[i]],
      if (length(reason) == 0 || is.na(reason) || !nzchar(as.character(reason))) "(no reason recorded)" else as.character(reason)))
  }
  report <- c(report, "")
}
report <- c(report,
  "## Notes", "",
  "- Multi-panel figure assembled with patchwork from per-figure ggplot snapshots (work/plots/*.rds).",
  "- PNG at 300 dpi + vector PDF per pinned output contract; add `svg` to `output_formats` (requires svglite) at run preflight if wanted.",
  sprintf("- captions manifest: `fig/figure-captions.md`", ""),
  "")
writeLines(report, file.path(opt$outdir, "figure-report.md"))

figure_status(opt$outdir, "figure_captions_manifest", "rendered",
              file_path = "fig/figure-captions.md", extra = list(n_figures = n_rendered_figs))
log_msg(sprintf("report phase done: %d figure caption entries; fig/figure-captions.md + figure-report.md written", n_rendered_figs))