#!/usr/bin/env Rscript
# make_test_fixture.R — synthetic DwC fixture generator for occurrence-viz battle-test.
# Per pinned decision: synthetic is acceptable when offline; noted in battle-test-report.md.
#
# Writes (arrow::write_parquet):
#   test/test_fixture_marine.parquet      — ~600 records, 8 species, Coral Triangle / Malacca box,
#                                           with depth_m + Bio-ORACLE-like env cols + FishBase-like trait cols
#   test/test_fixture_terrestrial.parquet — ~600 records, 6 species, Borneo land box,
#                                           with elev + WorldClim-like env_wc_* cols
#   test/test_fixture_minimal.parquet     — minimal-DwC-only file (PLAN §11.6 graceful-absence check)
#
# These are NOT plain obis-gbif-fetch output — they mimic edna-crosscheck
# enriched.parquet shape (base DwC columns + optional crosswalk/trait/env columns),
# and the minimal file checks the standalone contract.

suppressPackageStartupMessages({ library(dplyr) })
here <- function(...) file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))), ...)

set.seed(42)
mk_dwc <- function(species, n, lon_range, lat_range) {
  data.frame(
    scientificName  = rep(species, length.out = n),
    decimalLatitude  = round(runif(n, lat_range[1], lat_range[2]), 5),
    decimalLongitude = round(runif(n, lon_range[1], lon_range[2]), 5),
    eventDate = format(seq(Sys.Date() - n, by = "day", length.out = n), "%Y-%m-%d"),
    stringsAsFactors = FALSE
  )
}

# ------------------------------------------------ marine fixture
marine_species <- c(
  "Decapterus macarellus", "Thunnus albacares", "Scomberomorus commerson",
  "Epinephelus areolatus", "Rastrelliger brachysoma", "Carcharhinus sorrah",
  "Stolephorus commersonnii", "Selar crumenophthalmus"
)
dm <- do.call(rbind, lapply(seq_along(marine_species), function(i) {
  n <- 60 + (i * 17) %% 90
  df <- mk_dwc(marine_species[i], n, lon_range = c(98, 127), lat_range = c(2, 10))
  df$depth_m <- round(pmin(pmax(rweibull(n, shape = 1.6, scale = 60) + 3, 1), if (i %% 3 == 0) 900 else 250), 1)
  df
}))
# Bio-ORACLE-like surface env cols (edna-crosscheck env_bio_* naming, PLAN §11.1 prefix)
dm$env_bio_temp_ss     <- round(rnorm(nrow(dm), mean = 28.5, sd = 1.1), 3)
dm$env_bio_salinity_ss <- round(rnorm(nrow(dm), mean = 33.4, sd = 0.5), 3)
# FishBase-like trait cols (same values per species — trait lookups are per-taxon in crosscheck)
sp_depth_max <- setNames(c(400, 250, 90, 120, 60, 140, 50, 170), marine_species)
dm$trait_depth_min_m    <- 5
dm$trait_depth_max_m    <- sp_depth_max[dm$scientificName]
dm$trait_trophic_level  <- setNames(c(3.1, 4.2, 3.8, 3.6, 2.8, 4.0, 3.0, 3.3), marine_species)[dm$scientificName]
dm$trait_body_size_cm   <- setNames(c(35, 150, 120, 35, 25, 110, 9, 22), marine_species)[dm$scientificName]
dm$qc_flags  <- sample(c("", "", "", "ENVELOPE_VIOLATION"), nrow(dm), replace = TRUE, prob = c(.7,.15,.1,.05))
dm$qc_level  <- ifelse(dm$qc_flags == "", "ok", "warning")
dm$env_layer_class <- "surface"
dm$realm <- "marine"

# ------------------------------------------------ terrestrial fixture
terr_species <- c(
  "Sus barbatus", "Muntiacus muntjak", "Pongo pygmaeus", "Tragulus napu",
  "Macaca fascicularis", "Lophura ignita"
)
dt <- do.call(rbind, lapply(seq_along(terr_species), function(i) {
  n <- 70 + (i * 23) %% 60
  df <- mk_dwc(terr_species[i], n, lon_range = c(109.5, 117.5), lat_range = c(-3.8, 6.8))
  # elevation: species-typical bands (lowland -> montane)
  band <- switch(((i - 1) %% 3) + 1, c(10, 400), c(150, 900), c(600, 2100))
  df$elev <- round(runif(n, band[1], band[2]), 1)
  df
}))
dt$env_wc_bio1  <- round(27 - 0.006 * dt$elev + rnorm(nrow(dt), 0, 0.35), 2)   # annual mean T
dt$env_wc_bio12 <- round(2400 - 0.18 * dt$elev + rnorm(nrow(dt), 0, 180), 0)   # annual precip
dt$env_layer_class <- "elev-bioclim"
dt$trait_depth_min_m <- NA_real_; dt$trait_depth_max_m <- NA_real_
dt$trait_trophic_level <- setNames(c(2.2, 2.9, 2.1, 2.1, 2.4, 2.5), terr_species)[dt$scientificName]
dt$trait_body_size_cm <- setNames(c(120, 80, 130, 60, 45, 60), terr_species)[dt$scientificName]
dt$qc_flags <- ""; dt$qc_level <- "ok"

# ------------------------------------------------ minimal fixture (§11.6 graceful absence)
dmin <- mk_dwc(marine_species[1:4], 120, lon_range = c(98, 127), lat_range = c(2, 10))

out_dir <- here()
if (!requireNamespace("arrow", quietly = TRUE)) {
  stop("arrow package required to write parquet fixtures (pixi env provides r-arrow).", call. = FALSE)
}
arrow::write_parquet(dm,   file.path(out_dir, "test_fixture_marine.parquet"))
arrow::write_parquet(dt,   file.path(out_dir, "test_fixture_terrestrial.parquet"))
arrow::write_parquet(dmin, file.path(out_dir, "test_fixture_minimal.parquet"))
cat(sprintf("wrote fixtures:\n  %s (%d rows, %d cols)\n  %s (%d rows, %d cols)\n  %s (%d rows, %d cols)\n",
            file.path(out_dir, "test_fixture_marine.parquet"), nrow(dm), ncol(dm),
            file.path(out_dir, "test_fixture_terrestrial.parquet"), nrow(dt), ncol(dt),
            file.path(out_dir, "test_fixture_minimal.parquet"), nrow(dmin), ncol(dmin)))