#!/usr/bin/env Rscript
# plot_profiles.R — realm-routed environmental profiles (profiles-env/ sub-skill worker).
#
# REALM-AWARE BY CONFIG, NOT BY CODE: the x-axis variable and figure family are
# read from the run config (`profiles` block). The plotting functions below are
# identical for every realm:
#   marine      -> x_variable candidates like [depth_m, depth, ...] -> depth profile
#   freshwater  -> [elev, elevation, env_wc_bio1, ...]              -> elevation/bioclim envelope
#   terrestrial -> [elev, elevation, env_wc_bio1, ...]              -> elevation/bioclim envelope
# env / trait figures render ONLY when the corresponding columns exist in the
# input (PLAN §11.6 graceful-absence rule). Crosscheck trait columns
# (trait_depth_min_m/max, trait_trophic_level, trait_body_size_cm) are optional
# overlays when present; plain obis-gbif-fetch files skip them.
#
# Usage:
#   Rscript bin/plot_profiles.R --input <file.parquet|csv> --config <run-config.json> \
#                               --outdir <dir> [--input-label <label>]

suppressPackageStartupMessages({
  library(optparse); library(ggplot2); library(dplyr); library(tidyr)
})
script_dir <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(script_dir, "lib_viz.R"))

option_list <- list(
  make_option("--input", type = "character", help = "Occurrence table (parquet/csv/tsv)"),
  make_option("--config", type = "character", help = "Realm run config JSON"),
  make_option("--outdir", type = "character", default = ".", help = "Output directory"),
  make_option("--input-label", type = "character", default = NULL, help = "Dataset label for captions")
)
opt <- parse_args(OptionParser(option_list = option_list))

cfg <- read_run_config(opt$config)
df  <- load_input(opt$input)
validate_dwctable(df)

prof_cfg <- if (!is.null(cfg$profiles)) cfg$profiles else list()
formats  <- if (!is.null(cfg$output_formats)) cfg$output_formats else c("png", "pdf")
out_dir  <- file.path(opt$outdir, "fig")

# =====================================================================
# Figure 03: vertical profile — n records (and n species) vs x variable
# =====================================================================
render_profile <- function(x_col, x_label, out_stub) {
  xv <- suppressWarnings(as.numeric(df[[x_col]]))
  ok <- !is.na(xv)
  if (sum(ok) < 10) {
    figure_status(opt$outdir, out_stub, "skipped",
                  sprintf("column '%s' present but only %d non-numeric value(s); need >= 10", x_col, sum(ok)))
    return(FALSE)
  }
  d <- data.frame(x = xv[ok])
  # optional per-species separation when species counts make it meaningful
  ns <- length(unique(na.omit(df$scientificName[ok])))
  use_species <- ns > 1 && ns <= 25
  if (use_species) d$species <- df$scientificName[ok]

  if (use_species) {
    binned <- d %>% mutate(bin = cut(x, breaks = 30)) %>%
      group_by(bin) %>% summarise(x_mid = mean(x, na.rm = TRUE), n_records = n(), n_species = n_distinct(species, na.rm = TRUE)) %>%
      filter(!is.na(x_mid))
    p <- ggplot(binned, aes(x = x_mid)) +
      geom_area(aes(y = n_species), fill = "#2a9d8f", alpha = 0.55) +
      labs(y = sprintf("distinct species (per %s bin)", x_col))
  } else {
    binwidth <- max(diff(range(d$x, na.rm = TRUE)) / 40, 1e-6)
    p <- ggplot(d, aes(x = x)) +
      geom_histogram(bins = 40, fill = "#2a9d8f", colour = "white", linewidth = 0.1) +
      labs(y = "records")
  }
  p <- p + labs(x = if (!is.null(prof_cfg$x_label)) prof_cfg$x_label else x_col,
                title = sprintf("%s distribution of occurrences%s",
                                if (!is.null(prof_cfg$figure_title)) prof_cfg$figure_title else "Depth profile",
                                if (is.null(opt$`input-label`)) "" else paste0(" — ", opt$`input-label`)),
                subtitle = sprintf("%s records with '%s' values · realm: %s",
                                   format(sum(ok), big.mark = ","), x_col, cfg$realm)) +
    theme_bw(base_size = 11) + theme(panel.grid.minor = element_blank())
  if (isTRUE(prof_cfg$reverse_y)) p <- p + scale_y_reverse()  # depth increases downward

  files <- save_fig(p, file.path(opt$outdir, "fig", out_stub), formats = formats, width = 7, height = 6)
  dir.create(file.path(opt$outdir, "work", "plots"), recursive = TRUE, showWarnings = FALSE)
  saveRDS(p, file.path(opt$outdir, "work", "plots", paste0(out_stub, ".rds")))
  figure_status(opt$outdir, out_stub, "rendered",
                extra = list(x_column = x_col, n_used = sum(ok), outputs = files))
  TRUE
}

fig03 <- FALSE
x_col <- NULL
if (is.null(prof_cfg$x_variables) && length(prof_cfg) > 0 && !is.null(prof_cfg$x_variable)) {
  prof_cfg$x_variables <- prof_cfg$x_variable
}
if (length(prof_cfg$x_variables) > 0) {
  x_col <- first_col(df, prof_cfg$x_variables)
}
if (is.null(x_col)) {
  figure_status(opt$outdir, "03_env_profile", "skipped",
                sprintf("none of the configured profile x-variable(s) [%s] present in input — env/trait figures require their columns (PLAN §11.6)",
                        paste(prof_cfg$x_variables, collapse = ", ")))
} else {
  log_msg(sprintf("profiles: using x column '%s' (first available of: %s)", x_col, paste(prof_cfg$x_variables, collapse = ", ")))
  fig03 <- tryCatch(render_profile(x_col, prof_cfg$x_label, "03_env_profile"),
                    error = function(e) { figure_status(opt$outdir, "03_env_profile", "skipped", e$message); FALSE })
}

# =====================================================================
# Figure 04: env envelope — per-species observed range/quantiles per env variable
# =====================================================================
fig04 <- FALSE
env_vars <- if (!is.null(prof_cfg$envelope_variables)) prof_cfg$envelope_variables else character(0)
env_present <- if (!is.null(env_vars)) unlist(env_vars)[unlist(env_vars) %in% names(df)] else character(0)

if (length(env_present) > 0) {
  long <- df %>%
    select(scientificName, all_of(env_present)) %>%
    mutate(across(all_of(env_present), suppressWarnings(as.numeric))) %>%
    pivot_longer(all_of(env_present), names_to = "variable", values_to = "value") %>%
    filter(!is.na(value), !is.na(scientificName), nchar(scientificName) > 0) %>%
    group_by(scientificName, variable) %>% filter(n() >= 3) %>% ungroup()
  if (nrow(long) > 0) {
    # mean ± 95% CI computed manually (no Hmisc dependency)
    summ <- long %>%
      group_by(scientificName, variable) %>%
      summarise(mean = mean(value), se = ifelse(n() > 1, sd(value) / sqrt(n()), 0), n = n(),
                .groups = "drop") %>%
      mutate(lo = mean - 1.96 * se, hi = mean + 1.96 * se)
    p_env <- ggplot(summ, aes(x = scientificName, y = mean)) +
      geom_pointrange(aes(ymin = lo, ymax = hi), size = 0.7, colour = "#264653", alpha = 0.9) +
      geom_jitter(data = long, aes(x = scientificName, y = value), width = 0.12, size = 0.4,
                  alpha = 0.25, colour = "#e76f51", inherit.aes = FALSE) +
      coord_flip() + facet_wrap(~variable, scales = "free_x") +
      labs(title = sprintf("Environmental envelopes per species%s",
                           if (is.null(opt$`input-label`)) "" else paste0(" — ", opt$`input-label`)),
           subtitle = "points = records, pointrange = mean ± 95% CI (ENVELOPE context; flags computed upstream in edna-crosscheck — viz plots observations, it never flags)",
           x = NULL, y = if (!is.null(prof_cfg$envelope_label)) prof_cfg$envelope_label else "value") +
      theme_bw(base_size = 11) + theme(axis.text.y = element_text(face = "italic", size = 8))
    fig04 <- tryCatch({
      files <- save_fig(p_env, file.path(opt$outdir, "fig", "04_env_envelope"), formats = formats,
                        width = 9, height = max(4, 0.45 * length(unique(long$scientificName)) + 1.5))
      dir.create(file.path(opt$outdir, "work", "plots"), recursive = TRUE, showWarnings = FALSE)
      saveRDS(p_env, file.path(opt$outdir, "work", "plots", "04_env_envelope.rds"))
      figure_status(opt$outdir, "04_env_envelope", "rendered",
                    extra = list(variables = env_present, outputs = files))
      TRUE
    }, error = function(e) { figure_status(opt$outdir, "04_env_envelope", "skipped", e$message); FALSE })
  } else {
    figure_status(opt$outdir, "04_env_envelope", "skipped",
                  "env columns present but < 3 values per species × variable")
  }
} else {
  figure_status(opt$outdir, "04_env_envelope", "skipped",
                sprintf("none of configured envelope variables [%s] present in input",
                        paste(env_vars, collapse = ", ")))
}

# =====================================================================
# Figure 05: trait-space (crosscheck trait columns, OPTIONAL — render only when present)
# =====================================================================
fig05 <- FALSE
t_depth   <- first_col(df, c("trait_depth_min_m", "trait_depth_max_m"))
t_trophic <- if ("trait_trophic_level" %in% names(df)) "trait_trophic_level" else NULL
t_size    <- if ("trait_body_size_cm" %in% names(df)) "trait_body_size_cm" else NULL

if (!is.null(t_trophic) && (!is.null(t_depth) || !is.null(t_size))) {
  x_col_t <- if (!is.null(t_depth)) t_depth else t_size
  d5 <- df %>% select(scientificName, !!sym(x_col_t), !!sym(t_trophic)) %>%
    mutate(across(c(!!sym(x_col_t), !!sym(t_trophic)), suppressWarnings(as.numeric))) %>%
    filter(!is.na(.data[[x_col_t]]), !is.na(.data[[t_trophic]]))
  if (nrow(d5) >= 5) {
    p5 <- ggplot(d5, aes(x = .data[[x_col_t]], y = .data[[t_trophic]])) +
      geom_jitter(width = 0.02, height = 0.02, size = 1.1, alpha = 0.5, colour = "#2a6f97") +
      labs(title = "Trait space (FishBase traits via edna-crosscheck enriched table)",
           subtitle = x_col_t, x = x_col_t, y = t_trophic) +
      theme_bw(base_size = 11) + theme(legend.position = "bottom")
    fig05 <- tryCatch({
      files <- save_fig(p5, file.path(opt$outdir, "fig", "05_trait_space"), formats = formats,
                        width = 7, height = 6)
      dir.create(file.path(opt$outdir, "work", "plots"), recursive = TRUE, showWarnings = FALSE)
      saveRDS(p5, file.path(opt$outdir, "work", "plots", "05_trait_space.rds"))
      figure_status(opt$outdir, "05_trait_space", "rendered",
                    extra = list(x = x_col_t, y = t_trophic, outputs = files))
      TRUE
    }, error = function(e) { figure_status(opt$outdir, "05_trait_space", "skipped", e$message); FALSE })
  } else {
    figure_status(opt$outdir, "05_trait_space", "skipped",
                  sprintf("trait columns present but < 5 rows with both '%s' and '%s'", x_col_t, t_trophic))
  }
} else {
  figure_status(opt$outdir, "05_trait_space", "skipped",
                "trait columns (trait_depth_*/trait_trophic_level/trait_body_size_cm) absent — skipped (optional per PLAN §11.6)")
}

log_msg(sprintf("profiles phase done (fig03=%s, fig04=%s, fig05=%s)", fig03, fig04, fig05))