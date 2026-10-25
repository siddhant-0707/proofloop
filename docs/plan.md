# ProofLoop plan

Agreed on 2026-10-24.
Submission deadline: Sun Oct 25, 5 PM ET on Devpost (target: submit by noon).
Finals: Mon Oct 26, 10:15 AM, Reitz Union (one member in person; the ECE teammate stays on the roster for the two-department rule).

## Decisions

- **Hazard and place:** Hurricane Isaias flooding in the Big Bend, Florida.
- **Study area:** NISAR track 148 ascending, frames 16 (Dixie County and coastal Taylor County) and 17 (Perry).
- **Epochs:** before 2026-09-28, after 2026-10-10 (about one day after landfall).
- **User:** a Taylor or Dixie County emergency manager.
- **Loop:** Planner and Adversary agents on Gemma 4, 3 rounds plus a final attack, structured JSON output only.
- **Model hosting:** Gemma 4 26B A4B on OpenRouter (`google/gemma-4-26b-a4b-it`, about $0.07 per 1M input and $0.23 per 1M output tokens; under $1 for the whole event), with the Gemini API (`gemma-4-26b-a4b-it`, free) as the fallback.
  On the Gemini API, Gemma 4 with a JSON schema looped on the Planner prompt (repeated words, 500 errors, RECITATION stops), so it is only the backup.
  Both providers receive a strict JSON schema with shelter ids restricted to valid ones, and every response is validated against the Plan or Attack schema.
  The Planner drafts a plan, code simulates the draft, and Gemma writes its final plan and claims knowing what the draft achieved; the Verifier still checks the final claims.
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
- **Real exposure (#5).** The World's bounding box runs north to 30.15° N so it includes Perry, where Taylor County's shelters are. The numbers below are from frame 16 alone, which has no radar samples over Perry; see the frame 17 note after this section.
  - **Population:** 2020 Census blocks for Dixie (12029) and Taylor (12123) from TIGERweb, downloaded on the first `world.build`. Each block's population is spread evenly over the 60 m cells whose centers fall inside it; blocks smaller than a cell put everyone in their interior point's cell, and blocks cut by the grid edge keep only the share of their area inside. 35,537 people land on the grid (all of Dixie, 18,655 of Taylor's 21,796); 475 live in flagged cells.
  - **Shelters:** the four general-population sites in the 2020 Florida Statewide Emergency Shelter Plan, capacity summed over each site's buildings: Dixie County HS (2,558) and Ruth Raines MS (1,523) in Cross City; Taylor County ES (3,503) and Taylor County HS (3,151) in Perry. The plan has no cost to open, so cost is an assumption: $25 per space for a three-day activation.
  - **Travel reach:** 60 km along the grid (1,000 cells at 60 m), because coastal towns are 30 to 55 km from the shelters. The Cross City shelters reach nearly all 475 affected people; the Perry shelters reach 2.
  - **Default budget:** $150,000, enough to open two of the four shelters.
  - **Performance:** the Simulation's reachability search is vectorized and cached per World and shelter, so a Loop on the 1577 x 1370 grid with the rule-based agents takes under 2 s.
  - **First finding:** losing both Cross City schools leaves almost no affected person within reach of a shelter, so the Adversary's attacks on them decide the run.
- **Frame 17 mosaic (Perry).** The GCOV layer now mosaics frames 16 and 17 (also 10 m, EPSG:32617). Where they overlap, each cell takes both passes from the first frame that measured it on both, so a change is never computed across frames. Permanent water comes from the SME2 water fraction of both frames; cells neither covers are never flagged.
  - **No full download needed:** a granule that isn't downloaded is read in place with HTTP range requests (h5py over a seekable file object) and cropped to the Big Bend. Each frame 17 crop fetched about 290 MB in under 2 minutes, instead of 6.5 GB, and is cached in `data/raw/nisar/crops`.
  - **Result:** 33,965 cells flagged (33,154 under canopy, 811 open water), 960 people in flagged cells. Flagged share by 0.05° latitude band stays between 3.4% and 7.7% with no step at the frame seam (about 29.9 to 30.05° N). Perry 3.7% flagged (171 people), Keaton Beach 1.3%, now covered. All four shelters sit on dry cells.
  - **Loop:** the Perry shelters now matter. The first plan opens Ruth Raines MS and Taylor County HS and shelters 959.5 of 960 affected people; after the Adversary knocks out both Perry shelters and then Ruth Raines, the recommendation shelters about 450.

## Action and attack menus (#7)

Agreed on 2026-10-24.

- **Communities** are the unit for transport and road closures: Keaton Beach, Steinhatchee, Horseshoe Beach, Suwannee, Cross City and Perry.
  Each is an approximate town center with a 4 km radius (a planning assumption).
  Affected people per community on the frame 16 and 17 GCOV mosaic: Perry 300, Cross City 205, Steinhatchee 64, Suwannee 14, Keaton Beach 6, Horseshoe Beach 2.
- **Actions:** open shelter; stage transport (community, seats); allocate budget (contingency reserve, at least $1,000).
  - Transport carries a community's remaining affected people, nearest to its center first, into open shelters that still have beds, even when its road is closed.
    It costs $150 per seat (an assumption).
  - Actions are funded in plan order until the first one the budget cannot cover; it and every later action lose their money.
    The reserve is held back, not spent, so after a budget cut it is used up before any action loses funding.
    In the Simulation this is the same as leaving money unspent: the reserve records a deliberate choice to keep money in hand.
  - A shelter opened twice is paid for once.
- **Attacks:** shelter offline; road closed (community), which cuts a community off from shelters outside it but not from a shelter inside it; budget cut (10 to 50%).
  Known limitation: a closed road does not yet stop people from elsewhere walking through the community or into a shelter inside it.
- **Every attack has a planned counter:** redundant shelters against an offline shelter, transport against a closed road, a reserve against a budget cut.
- **Target outreach moved to #8,** where it means reaching people flooded outside FEMA zones; in #7 it would have needed an unsourced evacuation-compliance rate.
- **Gemma:** the draft check lists the exact cost of each action, because Gemma copied totals well but added them badly.
  Transport is only offered for communities with affected people.
  On the Gemini API fallback, Gemma loops on the Attack union with a rationale, so OpenRouter is effectively the only working provider for the full menus.

## Flooded outside the flood zone (#8)

Agreed on 2026-10-24.

- **FEMA flood zones:** Special Flood Hazard Area polygons (SFHA_TF = 'T': zones A, AE, AH, VE) from FEMA's National Flood Hazard Layer web service, downloaded once on the first `world.build` and cached in `data/raw/fema`.
  A cell is inside a FEMA zone when its center lies in one of those polygons; zone X and unmapped land are outside.
  8,261 polygons cover 44.6% of the World's cells.
- **Finding:** 659 of the 960 people in radar-flagged cells live outside FEMA flood zones: Perry 253, Cross City 115, Steinhatchee 17.
  Those inland flags are mostly radar brightening under tree canopy, so the claim is radar-observed water change outside FEMA zones, not confirmed flooding.
- **Attack, unwarned outside the flood zone:** from the next round on, affected people outside FEMA zones believe they are safe and stay home; they still count as affected.
- **Counter, target outreach (community):** $5,000 per community (an assumption: door-to-door teams, reverse 911 calls, radio).
  Once people are unwarned, outreach makes a community's people outside the zones seek shelter like everyone else.
  Before the attack it changes nothing, so the Planner has to anticipate it.
  People outside every community's 4 km radius cannot be reached by outreach.
- **Every Simulation result** reports the affected people outside FEMA zones whom the plan does not reach.
- **Map:** a FEMA flood zone toggle tints the Special Flood Hazard Area and outlines flagged blocks and cells where people live outside the zones.
- **Second Planner check (agreed 2026-10-24):** if the Planner's final plan would still fail verification (over budget or wrong claims), it gets one more check with the exact numbers and the Verifier's reasons.
  In live runs this turns some rejected rounds into verified ones; Gemma still sometimes overspends by a few thousand dollars, and the Verifier rejects those.
- **No repeated attacks:** an attack already in effect (a shelter already offline, a road already closed, people already unwarned) is invalid Adversary output.
  Gemma's Adversary is only offered roads still open, and the unwarned attack is removed from its schema once in effect.
