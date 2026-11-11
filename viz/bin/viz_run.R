#!/usr/bin/env Rscript
# viz_run.R — orchestrator driver for the occurrence-viz skill (v1.8.0).
#
# Runs the full figure set for one input table against one realm run config,
# invoking the standalone phase workers (bin/plot_map_leaflet.R,
# bin/plot_profiles.R, bin/build_report.R). Also exposes the maps/ sub-skill's
# run-preflight validation as `--phase preflight`.
#
# Usage:
#   Rscript bin/viz_run.R --input <file.parquet|csv> --config <run-config.json> \
#                         --outdir <dir> [--input-label <label>] \
#                         [--only maps|profiles|report] [--phase preflight]

suppressPackageStartupMessages({
  library(optparse); library(jsonlite)
})
script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

option_list <- list(
  make_option("--input", type = "character", help = "Occurrence table (parquet/csv/tsv)"),
  make_option("--config", type = "character", help = "Realm run config JSON"),
  make_option("--outdir", type = "character", default = "viz_out", help = "Output directory"),
  make_option("--input-label", type = "character", default = NULL, help = "Dataset label for captions"),
  make_option("--overlay", type = "character", default = NULL,
              help = "Context occurrences CSV (passed to the leaflet maps worker as a gray layer)"),
  make_option("--habitat", type = "character", default = NULL,
              help = "habitat_iucn.csv -> IUCN+habitat annotations (contact sheet legacy feature)"),
  make_option("--near-km", type = "numeric", default = 100,
              help = "Concordance ring R (km) — drawn on the leaflet map (SP-11 echo)"),
  make_option("--counts", type = "character", default = NULL,
              help = "occurrence_counts.json (per-species ring/world counts, leaflet popups)"),
  make_option("--context", type = "character", default = NULL,
              help = "context_occurrences.csv (context_records.py output; one toggleable leaflet layer per species)"),
  make_option("--params", type = "character", default = NULL,
              help = "crosscheck params.json (ring centre = input_extent site)"),
  make_option("--images", type = "character", default = NULL,
              help = "species_images.csv manifest -> contact sheet (fig 07, legacy feature)"),
  make_option("--only", type = "character", default = "maps,profiles,report",
              help = "Comma-separated subset of phases to run"),
  make_option("--phase", type = "character", default = NULL,
              help = "Run only this single phase: preflight | maps | profiles | report")
)
opt <- parse_args(OptionParser(option_list = option_list))

cfg  <- read_run_config(opt$config)
df   <- load_input(opt$input)
validate_dwctable(df)

# ------------------------------------------------------------- run preflight
# maps/ sub-skill SP gating: figure-set feasibility is reported BEFORE rendering.
rpt <- function(k) { v <- cfg$figures[[k]]; if (is.null(v)) FALSE else isTRUE(v) }
req_fig <- c("occurrence_map" = "map", "depth_profile" = "profiles", "env_envelope" = "profiles")
cat("\n== occurrence-viz run preflight ==\n")
cat(sprintf("input           : %s\n", opt$input))
cat(sprintf("realm           : %s (config: %s)\n", cfg$realm, opt$config))
cat(sprintf("records         : %d\n", nrow(df)))
cat(sprintf("species         : %d\n", length(unique(na.omit(df$scientificName)))))
dr <- suppressWarnings(as.numeric(df$eventDate))
if (identical(dr, NA)) dr <- NA; date_range <- tryCatch(paste(range(as.Date(as.character(df$eventDate), format = "%Y-%m-%d"), na.rm = TRUE), collapse = " .. "), error = function(e) "n/a")
cat(sprintf("date range      : %s\n", date_range))
cat("optional columns: ")
opt_cols <- c("trait_depth_min_m", "trait_depth_max_m", "trait_trophic_level", "trait_body_size_cm",
              "qc_flags", "qc_level", "gbif_taxonKey", "worms_AphiaID", "env_layer_class", "acceptedScientificName")
present_opt <- opt_cols[opt_cols %in% names(df)]
cat(paste(present_opt, collapse = ", "), "\n")
prof_cfg <- if (!is.null(cfg$profiles)) cfg$profiles else list()
x_col <- if (!is.null(prof_cfg$x_variables)) first_col(df, prof_cfg$x_variables) else NULL
cat(sprintf("profile x-col   : %s\n", if (is.null(x_col)) paste0("(none of: ", paste(prof_cfg$x_variables, collapse = ", "), ")") else x_col))
env_vars <- if (!is.null(prof_cfg$envelope_variables)) unlist(prof_cfg$envelope_variables) else character(0)
env_present <- env_vars[env_vars %in% names(df)]
cat(sprintf("envelope vars   : %s\n", if (length(env_present) == 0) paste0("(none of: ", paste(env_vars, collapse = ", "), ")") else paste(env_present, collapse = ", ")))
cat("\n")
figure_status(opt$outdir, "preflight", "rendered", extra = list(
  input = opt$input, realm = cfg$realm, records = nrow(df),
  n_species = length(unique(na.omit(df$scientificName))),
  profile_x = if (is.null(x_col)) NA else x_col, env_present = env_present))

# ------------------------------------------------------------- invoke workers
phases <- strsplit(tolower(opt$only), "\\s*,\\s*")[[1]]
if (!is.null(opt$phase)) phases <- opt$phase
run_phase <- function(phase, script, args_extra = character(0)) {
  log_msg(sprintf("invoking %s worker: %s", phase, script))
  args <- c(file.path(script_dir, script),
            "--config", opt$config, "--outdir", opt$outdir,
            if (!is.null(opt$input)) c("--input", opt$input) else character(0),
            if (!is.null(opt$`input-label`)) c("--input-label", opt$`input-label`) else character(0),
            args_extra)
  cmd <- paste(c(shQuote(file.path(R.home("bin"), "Rscript")), shQuote(args)), collapse = " ")
  cat(sprintf("\n[phase %s] %s\n", phase, cmd))
  st <- system(cmd)
  if (st != 0) {
    warn_msg(sprintf("phase '%s' worker exited with status %d", phase, st))
  }
  st == 0
}
# workers validate the input themselves; --input is passed through. For maps
# and profiles the input flag is required:
if ("preflight" %in% phases) phases <- setdiff(phases, "preflight")
if (!is.null(opt$images) && !"contactsheet" %in% phases) {
  phases <- setdiff(phases, "report")
  phases <- c(phases, "contactsheet", "report")  # contact sheet feeds the captions manifest
}
if (length(phases) == 0) {
  log_msg("preflight-only run complete (no figures requested).")
  quit(status = 0)
}
ok <- TRUE
for (ph in phases) {
  script <- switch(ph, maps = "plot_map_leaflet.R", contactsheet = "plot_contact_sheet.R",
                   profiles = "plot_profiles.R", report = "build_report.R",
                   stop(sprintf("unknown phase '%s' (maps | profiles | report)", ph), call. = FALSE))
  extra <- if (!is.null(opt$overlay)) c("--overlay", opt$overlay) else character(0)
  if (ph == "maps") {
    extra <- c(if (!is.null(opt$context)) c("--context", opt$context) else character(0),
               if (!is.null(opt$params)) c("--params", opt$params) else character(0),
               if (!is.null(opt$counts)) c("--counts", opt$counts) else character(0))
    if (!is.null(opt[["near-km"]])) extra <- c(extra, "--near-km", format(opt[["near-km"]], digits = 6))
  }
  if (ph == "contactsheet") {
    extra <- c("--images", opt$images,
               "--input-label", if (!is.null(opt$`input-label`)) opt$`input-label` else "species reference images",
               if (!is.null(opt$habitat)) c("--habitat", opt$habitat) else character(0))
  }
  ok <- run_phase(ph, script, extra) && ok
}
log_msg(sprintf("viz_run complete (all phases ok: %s). Outputs in %s/fig + %s/figure-report.md", ok, opt$outdir, opt$outdir))
if (!ok) quit(status = 1)