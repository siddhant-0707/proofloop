# ProofLoop plan

Agreed on 2026-10-24.
Submission deadline: Sun Oct 25, 5 PM ET on Devpost (target: submit by noon).
Finals: Mon Oct 26, 10:15 AM, Reitz Union (one member in person; the ECE teammate stays on the roster for the two-department rule).

## Decisions

- **Hazard and place:** Hurricane Isaias flooding in the Big Bend, Florida.
- **Study area:** NISAR track 148 ascending, frame 16 (Dixie County and coastal Taylor County). Frame 17 (Perry, Tallahassee) is optional.
- **Epochs:** before 2026-09-28, after 2026-10-10 (about one day after landfall).
- **User:** a Taylor or Dixie County emergency manager.
- **Loop:** Planner and Adversary agents on Gemini 3, 3 rounds, structured JSON output only.
- **Scoring:** a small deterministic Python simulation, never an LLM. The Verifier re-runs it on the Planner's claimed numbers.
- **Hindcast:** plans are scored against the flood extent NISAR actually observed.
- **Adversary attacks (fixed menu):** shelter offline, road closed, budget cut, and "flooded outside the flood zone" (FEMA NFHL vs. NISAR).
- **Planner actions (fixed menu):** open shelter, stage transport, allocate budget, target outreach.
- **Sources:** a curated pack (FEMA, NHC, county shelter lists). No open web research at runtime.
- **Demo:** live sliders trigger one re-plan round; a recorded golden run is the fallback.
- **Stack:** Next.js + MapLibre (web), FastAPI (backend), uv.
- **Prizes:** overall, Vobile, MLH Best Use of Gemini, MLH Best Open Source (MIT license).

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
