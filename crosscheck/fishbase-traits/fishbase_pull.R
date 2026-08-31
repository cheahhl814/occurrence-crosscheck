#!/usr/bin/env Rscript
# fishbase_pull.R — bulk-pull FishBase species + synonyms tables via rfishbase
# (CRAN package; since ~v4 it reads static parquet snapshots from a
# Source Cooperative S3 bucket rather than a live per-name REST API, so one
# call here == one bulk download, matching the skill's "never per-point API
# calls" convention). Falls back cleanly (empty JSON, exit 0) if rfishbase
# is not installed or the network pull fails — the Python caller treats
# that as "FishBase unavailable" and nulls out fishbase_SpeCode / traits
# rather than crashing the run.
#
# Usage: Rscript fishbase_pull.R <names_file: one scientificName per line> <out.json>

# Persist duckdb's downloaded extensions across subprocess invocations (each
# fishbase_pull.R run is a fresh R session otherwise, re-downloading the
# same httpfs/etc extensions every time — a real, observed source of
# cold-start slowness in this skill's own battle test).
dir.create("~/.duckdb", showWarnings = FALSE)

args <- commandArgs(trailingOnly = TRUE)
names_file <- args[1]
out_json <- args[2]

names <- readLines(names_file)
names <- names[nzchar(trimws(names))]

result <- list()

ok <- requireNamespace("rfishbase", quietly = TRUE) &&
      requireNamespace("jsonlite", quietly = TRUE)

if (!ok) {
  message("fishbase_pull.R: rfishbase/jsonlite not installed; emitting empty result")
} else {
  library(jsonlite)
  species_tbl <- tryCatch(rfishbase::species(names), error = function(e) NULL)
  if (is.null(species_tbl) || nrow(species_tbl) == 0) {
    message("fishbase_pull.R: no FishBase species matches (or pull failed)")
  } else {
    for (i in seq_len(nrow(species_tbl))) {
      row <- species_tbl[i, ]
      # NOTE: rfishbase's `species` table 'Species' column is already the FULL
      # binomial ("Gadus morhua"), not just the specific epithet -- paste(Genus,
      # Species) was double-prefixing the genus (bug found + fixed during this
      # skill's own battle test: keys came out as "Gadus Gadus morhua").
      sciname <- row$Species
      result[[sciname]] <- list(
        SpecCode = as.integer(row$SpecCode),
        DepthRangeShallow = as.numeric(row$DepthRangeShallow),
        DepthRangeDeep = as.numeric(row$DepthRangeDeep),
        Length = as.numeric(row$Length),
        # rfishbase 'species' table doesn't carry trophic level directly;
        # that lives in the 'ecology' table. Pull it best-effort.
        trophic_level = NA_real_
      )
    }
    eco_tbl <- tryCatch(rfishbase::ecology(names), error = function(e) NULL)
    if (!is.null(eco_tbl) && nrow(eco_tbl) > 0 && "FoodTroph" %in% names(eco_tbl)) {
      for (i in seq_len(nrow(eco_tbl))) {
        row <- eco_tbl[i, ]
        # NOTE: rfishbase's `species` table 'Species' column is already the FULL
      # binomial ("Gadus morhua"), not just the specific epithet -- paste(Genus,
      # Species) was double-prefixing the genus (bug found + fixed during this
      # skill's own battle test: keys came out as "Gadus Gadus morhua").
      sciname <- row$Species
        if (!is.null(result[[sciname]])) {
          result[[sciname]]$trophic_level <- as.numeric(row$FoodTroph)
        }
      }
    }
  }
}

writeLines(jsonlite::toJSON(result, auto_unbox = TRUE, null = "null", na = "null"), out_json)
