# ProofLoop plan

Agreed on 2026-10-24.
Submission deadline: Sun Oct 25, 5 PM ET on Devpost (target: submit by noon).
Finals: Mon Oct 26, 10:15 AM, Reitz Union (one member in person; the ECE teammate stays on the roster for the two-department rule).

## Decisions

- **Hazard and place:** Hurricane Isaias flooding in the Big Bend, Florida.
- **Study area:** NISAR track 148 ascending, frame 16 (Dixie County and coastal Taylor County). Frame 17 (Perry, Tallahassee) is optional.
- **Epochs:** before 2026-09-28, after 2026-10-10 (about one day after landfall).
- **User:** a Taylor or Dixie County emergency manager.
- **Loop:** Planner and Adversary agents on Gemma 4, 3 rounds plus a final attack, structured JSON output only.
- **Model hosting:** Gemma 4 26B A4B (`gemma-4-26b-a4b-it`) on the Gemini API, which is free with no paid tier.
  On a rate-limit error, the same request falls back to OpenRouter's paid `google/gemma-4-26b-a4b-it` (about $0.07 per 1M input and $0.23 per 1M output tokens; under $1 for the whole event).
  Both providers receive the full JSON schema, and every response is validated against the Plan or Attack schema.
  API keys live in the backend's `.env` and are never committed.
- **Scoring:** a small deterministic Python simulation, never an LLM. The Verifier re-runs it on the Planner's claimed numbers.
- **Hindcast:** plans are scored against the flood extent NISAR actually observed.
- **Adversary attacks (fixed menu):** shelter offline, road closed, budget cut, and "flooded outside the flood zone" (FEMA NFHL vs. NISAR).
- **Planner actions (fixed menu):** open shelter, stage transport, allocate budget, target outreach.
- **Sources:** a curated pack (FEMA, NHC, county shelter lists). No open web research at runtime.
- **Demo:** live sliders trigger one re-plan round; a recorded golden run is the fallback.
- **Stack:** Next.js + MapLibre (web), FastAPI (backend), uv.
- **Prizes:** overall, Vobile, MLH Best Use of Gemma, MLH Best Open Source (MIT license).

## Checkpoints

- **Hour 6:** if there is no credible GCOV flood layer, switch the hazard layer to SME2 (soil moisture and gridded backscatter).

## First findings (SME2, frame 16)

- Before and after grids are identical (EASE-Grid 2.0, EPSG:6933, 200 m), so change detection needs no resampling.
- Median soil moisture across the frame rose from 0.229 to 0.277 m³/m³ after Isaias.
- Over Big Bend land, HH backscatter mostly brightened by 1-3 dB (wet soil, flooded vegetation); almost no pixels darkened (0.006%).
- Conclusion: at 200 m, one day after landfall, open-water flooding is not obvious. The flood layer needs 20 m GCOV and must treat both darkening (open water) and brightening (flooding under canopy) as signals.

## Implementation notes

- **Reachability is computed by the Simulation, not stored in the World.**
  A flooded cell reaches a shelter through a 4-connected path of dry cells no longer than the World's travel reach.
  Computing it per Scenario lets future attacks (closed roads) change it without rebuilding the World.
- **Attacks accumulate, and the Adversary gets a final attack.**
  Each round's attack is answered by the next round's plan.
  After the last round the Adversary attacks once more, and no plan answers that final attack.
  The recommendation is the verified plan that shelters the most people under the final Scenario, with every attack applied, so it has survived an attack it never saw.
  Ties go to the earlier round.
- **Agent output is validated before it is used.**
  Malformed plans or attacks, attacks on unknown shelters, and agent exceptions are recorded in the Transcript with a reason and never crash a run.
- **SME2 hazard evidence** is the stronger of |HH change| / 6 dB and soil moisture increase / 0.2 m³/m³, clipped to [0, 1].
  Cells at 0.5 or above are flagged.
  Permanent water (water fraction of 0.5 or more) carries no evidence.
- **GCOV flood layer (#4)** is the primary hazard layer whenever both frame 16 GCOV granules are downloaded; otherwise the World builder falls back to SME2.
  Frame 16 GCOV is 10 m (EPSG:32617). The builder averages 6 x 6 pixels of HH power into cells of about 60 m to suppress speckle, on a regular lat/lon grid (1392 x 1370 cells over the Big Bend), and sets the travel reach to 83 cells (5 km).
  Thresholds, all in HH dB, calibrated on the frame 16 pair:
  - Permanent water: SME2 water fraction of 0.5 or more, or HH of -17 dB or darker before the storm (permanent water has a median of -18.6 dB; land a 1st percentile of -16.3 dB).
  - Open water: darkening of 3 dB or more (full confidence at 6 dB) where the after pass is -15 dB or darker. Without the darkness check, most darkened cells sat around -10 dB after the storm, which is not water.
  - Under canopy: brightening of 3 dB or more beyond the median land change (full confidence at 6 dB), only where the before pass was -12 dB or brighter.
    Land brightened by a median of +1.55 dB (rain-wet soil), so a fixed +3 dB threshold flagged 16% of land.
    Bare fields that were dark before and brightened (the center pivots east of Cross City) are not double bounce.
- **GCOV spot checks (frame 16, 2 km boxes around towns):** 1.0% of cells flagged overall (19,342 under canopy, 534 open water).
  Steinhatchee 4.4% under canopy, Cross City 3.3%, Suwannee 2.8%, Horseshoe Beach 1.1%, all with almost no open water.
  One day after landfall the radar mostly sees water under the trees, not standing open water, matching the SME2 finding.
  Keaton Beach is outside the frame 16 swath (no valid samples).
  The remaining flags are scattered and speckle-like; treat the layer as radar-observed water change with confidence, not a flood map.
