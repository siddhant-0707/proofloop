# ProofLoop plan

Agreed on 2026-10-24.
Submission deadline: Sun Oct 25, 5 PM ET on Devpost (target: submit by noon).
Finals: Mon Oct 26, 10:15 AM, Reitz Union (one member in person; the ECE teammate stays on the roster for the two-department rule).

## Decisions

- **Hazard and place:** Hurricane Isaias flooding in the Big Bend, Florida.
- **Study area:** NISAR track 148 ascending, frames 16 (Dixie County and coastal Taylor County) and 17 (Perry).
- **Epochs:** before 2026-09-28, after 2026-10-10 (about one day after landfall).
- **User:** a Taylor or Dixie County emergency manager.
- **Loop:** Planner and Adversary agents on Gemma 4, 3 rounds, each plan tested by the Adversary, structured JSON output only.
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
- **Attacks are tests; they do not accumulate** (superseded the earlier "attacks accumulate, plus a final attack" design on 2026-10-24; see "Plans are for normal conditions" below).
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

Agreed on 2026-10-24. Superseded the same day by "Everyone counts the same; backup plans": the zones stay on the map as context only, and the unwarned attack and outreach are gone.

- **FEMA flood zones:** Special Flood Hazard Area polygons (SFHA_TF = 'T': zones A, AE, AH, VE) from FEMA's National Flood Hazard Layer web service, downloaded once on the first `world.build` and cached in `data/raw/fema`.
  A cell is inside a FEMA zone when its center lies in one of those polygons; zone X and unmapped land are outside.
  8,261 polygons cover 44.6% of the World's cells.
- **Finding:** 659 of the 960 people in radar-flagged cells live outside FEMA flood zones: Perry 253, Cross City 115, Steinhatchee 17.
  Those inland flags are mostly radar brightening under tree canopy, so the claim is radar-observed water change outside FEMA zones, not confirmed flooding.
- **Attack, unwarned outside the flood zone:** affected people outside FEMA zones believe they are safe and stay home; they still count as affected.
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

## Scenario controls and re-plan (#9)

Agreed on 2026-10-24.

- **Controls:** budget ($25,000 to $250,000), shelter offline, road closed, and the FEMA unwarned switch edit a base Scenario shared by the map and the panel.
- **Re-plan:** after a full stress test completes, each change re-plans after a 700 ms debounce.
  A re-plan is one round with no final attack, and the Gemma Planner starts from the previous recommendation instead of drafting from scratch.
- **Planner feedback:** when a plan is over budget, the check lists concrete cuts (lower the reserve to a stated amount, stage fewer seats, drop an outreach or a shelter).
  When a plan fits the budget and only its claims are wrong, the check gives the exact numbers to claim.
- **Stale runs:** the browser aborts and ignores them; the server stops the Loop at the next round once the client disconnects.
- **Measured (Gemma 4 via OpenRouter, 6 re-plans from one previous plan):** 2 verified; typical time 8 to 30 s, with one 68 s outlier.
  Rule-based re-plans are instant and verified, so use them for the live slider moment in the demo.

## Evidence trail and outreach briefing (#10)

Agreed on 2026-10-24.

- **Evidence trail:** every Round and the Recommendation carry evidence for each figure (people affected, sheltered and unreached, robustness, cost, unfunded actions, affected and unreached people outside FEMA zones, budget).
  Each entry lists its sources from the source pack, the formula code applies, this run's inputs (for example cost itemized per action), assumptions and limitations.
  Code builds it from the same simulation trace that scored the plan, so the trail cannot disagree with the number; agent prompts do not see it.
- **Source pack:** moved from `gemma/` to `proofloop/sources.py` so the Loop can cite it; S1 now names frames 16 and 17, and S6 is the 2020 Census block populations.
- **Limitation on every flood figure:** the flood layer is radar-observed water change with a confidence per cell, not an official flood map.
- **Evidence drawer:** every number in the panel (round scores, budgets, the recommendation and the briefing) opens a side drawer with that figure's evidence; Escape or the backdrop closes it.
- **Outreach briefing:** written by code templates, not Gemma, from the recommended plan under the conditions the user set.
  Neighborhoods are the six communities (4 km radius), most affected first, plus one line for people outside any town.
  Each lists people affected, sheltered and outside FEMA zones, the shelters they go to (and how many transport carries), and plain-language steps: where to send residents, transport, closed roads, who outside FEMA zones to warn or reach with outreach, and who cannot reach a shelter.
  A Copy button gives the briefing as plain text for field staff.

## Scope, and the stress test picks the failures

Agreed on 2026-10-24; replaces the shelter, road and unwarned controls from #9.

- **User controls:** only what the plan is for (the whole area or one of the six towns) and the budget.
  A single-town plan counts only that town's affected people (4 km radius); any shelter may take them, and the agents are offered only that town for transport, outreach and road attacks.
  Changing the town clears the results and waits for a full stress test; budget changes still re-plan.
- **Failures are found, not chosen:** the Adversary tests each round's plan, and once the recommendation is chosen, code scores it under every case on top of the user's scenario.
  Cases are each shelter the plan opens going offline, each affected town's road closing, budget cuts of 10, 25 and 50%, and people outside FEMA zones unwarned, alone and in pairs (never two cuts).
  The whole area is 75 cases and adds about 1 s; a town is about 20.
- **Agent calls are stateless:** every Planner and Adversary call is a fresh API request.
  The Adversary sees only the current conditions and the plan it attacks, never the Planner's reasoning or earlier conversations.
  The Planner sees a summary of earlier rounds on purpose, so it can learn from the Verifier.
- **Confidence:** the per-cell radar evidence stays in the data and the evidence trail but is no longer shown on the map.
- **Hide unpopulated squares:** a map option under the flooding layer hides flagged cells (and, before #27, zoomed-out blocks) with an estimated resident count under 0.5 (which rounds to 0); it is off by default and only changes the map, not the simulation.

## Plan report and review

Agreed on 2026-10-24.

- **Report:** code writes every plan up under the FEMA CPG 101 base-plan headings that Florida county plans also use (research in `docs/research/plan-report-format.md`): purpose and scope, situation overview, planning assumptions, objectives (ICS 202 style), concept of operations, organization and assignment of responsibilities (one row per action, ICS 204 style, labeled by function such as Mass care ESF 6), communications: public alert and warning (the per-neighborhood briefing), administration, finance and logistics, limitations and references.
  The final plan's report adds courses of action considered (every verified plan and why this one) and plan validation (one failure, two at once, and everything the Adversary found at once).
  Every report is marked as an exercise, not an official county document; sections ProofLoop has no data for (direction and control, signatures, continuity, recovery) are left out rather than filled with placeholders.
- **Main page:** only the final, verified plan, as a full-width report below the map; the side panel keeps the controls, live progress and a short summary.
  Every other plan sits in a Review tab, written up the same way for the same conditions: verified but not chosen (with its score against the final plan's), rejected (with the Verifier's reasons), or a re-test.
- **Re-tests are marked:** when the Planner's output is invalid, the round re-tests the best earlier plan and says so, instead of looking like a new verified plan; it is not a separate candidate.
- **The choice is shown:** the recommendation lists every verified plan with its score, the number it is chosen by, so "final" can no longer look like it sits on the wrong plan.
- **No re-plan on finish:** the panel re-plans only when the budget changes, not when a run finishes.

## Plans are for normal conditions; failures are tests

Agreed on 2026-10-24; replaces "attacks accumulate, plus a final attack".

- **Why:** with attacks piling up, by the last round several shelters were offline and the budget cut, so every plan was checked against a disaster and runs could end with no plan at all.
- **Every plan is for the user's conditions:** each round the Planner plans for the scope and budget the user set, and the Verifier checks it there.
  A plan is rejected only for its own mistakes: false claims, over budget, or unknown or offline places.
- **The Adversary tests, it does not change the world:** each round it picks the one failure that hurts that round's plan most; the Round records the failure and the plan's result under it.
  Failures never carry into the next round; the Planner sees them in its history and may hedge if the budget allows.
- **The final plan:** among verified plans, the best score, where the score is half the share sheltered as planned and half the average share over every single failure (each opened shelter offline, each affected town's road closed, each budget cut, people outside FEMA zones unwarned).
  Then the cheaper plan, then the earlier one.
- **There is always a final plan:** when no plan passes verification, code builds a baseline plan (the affordable set of shelters that best survives losing one, plus outreach or transport against the failures the Adversary found when that helps and fits the budget), labeled "Built by code".
  The rule-based Planner proposes the same baseline.
- **Major trouble is reported, never held against a plan:** the report's stress test separates one failure (small trouble) from two at once (major trouble), and shows every failure the Adversary found applied at once.

## Everyone counts the same; backup plans

Agreed on 2026-10-24; replaces the score and the FEMA-zone parts above.

- **No FEMA-zone logic:** every affected person counts the same, inside a FEMA flood zone or not.
  The unwarned attack, target outreach, people staying home and the outside-zone figures are removed from the Simulation, the evidence trail, the briefing, the report and the agents.
- **Map:** FEMA flood zones are always tinted on the map with a legend swatch, and have no checkbox; the pink outside-zone outlines and popup lines are gone.
  Replaced by "The flood looks like a flood (#27)": a checkbox, off by default.
- **Shelter everyone first:** the final plan is the plan that shelters the most people as planned; among those, the most on average under single failures; then the cheaper plan, then the earlier one.
  The baseline picks the affordable set of shelters that shelters the most people, and among those the one that best survives losing a shelter; the Gemma Planner is told to shelter everyone first and hedge only with money left.
  The baseline always competes with the verified plans (the Planner's plan wins ties), so the final plan never shelters fewer people than the budget allows.
  Before 2026-10-25 it competed only when no plan passed; a verified Gemma plan sheltering 453 of 960 at $150,000 became final although $116,850 covers everyone.
- **When the budget cannot shelter everyone:** the report says so up front, with the cost of the cheapest set of shelters that takes everyone (or says no set can).
  When money is the only reason, the run screen asks: it says how many the current budget shelters and offers the lowest budget that covers everyone (the cheapest set of shelters that takes everyone), with "Yes" (sets the budget and re-plans) or "No" (keeps the budget and opens the report).
  It never asks when the current budget already covers everyone, or when no set of shelters can.
- **Backup plans:** for every single failure, the 5 worst pairs and everything the Adversary found at once, code builds a backup plan for those conditions (the baseline, given the failure) and keeps it if it shelters more than the plan does.
  The report shows each as what changes from the plan, for example "Open Taylor County Elementary School instead of Taylor County High School", with the people it shelters.
- **Measured (whole area, $150,000, rule-based):** the plan shelters all 960 as planned.
  With backups, every shelter outage and road closure still shelters everyone; budget cuts of 25% and 50% leave 53% and 47%, because $112,500 or less cannot open enough shelters at $25 per space.
  A run takes about 5 s.

## Three screens over one map

Agreed on 2026-10-25; replaces the side panel, the budget slider and the report below the map.

- **Start:** the map fills the page; a card holds "Plan for" (a dropdown: the whole area or one of the six towns), the budget as a typed number (at least $1,000), the Planner (Gemma 4 or rule-based) and Run.
  Choosing a town flies the map to it.
- **Running:** the map stays as a dimmed background behind one progress card: percent done, time elapsed, and three stages (Plan, Attack, Report) instead of round numbers.
  The percent counts finished rounds plus an estimate of the current one that slows as it goes, so it keeps moving but only reaches 100% when the run ends; Cancel returns to the start.
- **Budget question:** asked on the run screen, only when money alone keeps the plan from sheltering everyone; "Yes" re-plans with the new budget, "No" opens the report.
- **Report:** its own page, with the map beside it (40% of the width on a wide screen, above it on a narrow one) refitted to the area planned; "New plan" returns to the start with the same choices, and the start card can reopen the last report.
- **No live re-plan on budget edits:** the budget is a typed number, so a new run starts only from Run (or "Yes" on the budget question).

## Cascade: a plain report and PDF downloads

Agreed on 2026-10-25; the product is renamed Cascade (the code and repo keep the `proofloop` name).

- **Start card:** Cascade's mark and name, the storm and area as chips, "Area" (a dropdown), the budget typed with thousands separators plus $100k, $150k and $250k presets, the planning engine (AI planner or Instant, rule-based) folded under "Planning engine", and "Build plan".
  The map zooms out to level 5.5 and pans 2.5 degrees past the World's bounds.
- **Run card:** "Building your plan" (or "Updating your plan"), with the stages Draft, Strengthen and Finish; it never says "stress test".
- **The report is only the plan:** no badges, rationale, Planner, Adversary, Verifier, rounds, models or "built by code", and no "courses of action considered" section.
- **Other plans:** a second tab lists every other plan drafted for the same conditions (re-tests and rounds with no plan left out, plus the plan before a budget change), each as "Alternative N" with "Rejected" or "Not chosen", a one-line summary and a plain reason, for example "Rejected: it misstated how many it shelters (said 1,199, really 960)" or "Shelters 453 of 960 (47%); the chosen plan shelters 100%".
  Each expands to its full write-up and has its own PDF button.
  The backup plans section is "Contingencies and backup plans"; the exercise disclaimer moved from a banner to the references note.
  The loop still records every round in the transcript; only the web app stops showing it.
- **Download PDF:** a menu in the report header offers the full plan report (with a snapshot of the map), the field briefing (assignments and town steps), the backup plans, or the other plans (one per page).
  It prints a letterhead version of the report through the browser's print dialog, with the file name set from the page title ("Cascade - Full plan report - Whole area - $150,000"); in the print view every stress case is listed instead of the worst five.

## Runs play on the map (#31)

Agreed on 2026-10-25 for the demo, on the `demo-visuals` branch; replaces the Running screen in "Three screens over one map" and the Run card in "Cascade: a plain report and PDF downloads".
The report stays plain: no Planner, Adversary, Verifier, rounds or models.

- **No veil:** while a run plays, the map is the stage; a counter along the top shows people at risk, sheltered, and budget used (with any reserve held back), and a caption bar along the bottom says what is happening.
- **Beats:** each streamed round plays as beats from a pure storyboard: the Planner's shelters light up (rings sized by capacity) and curved arcs run from each town to its shelters, labelled with people (transport arcs in their own color), then the Verifier's verdict lands as a "Verified" or "Rejected" stamp with the reason.
  Here the run does name the Planner, the Verifier, rounds and Gemma 4: showing the agents at work is the point of the demo.
- **Attack beat (#25):** after the verdict, the Adversary's failure plays and the camera moves in on what it hit.
  A shelter knocked offline sends out two red shock rings, then turns grey ("OFFLINE"); a shelter a budget cut leaves unfunded turns grey ("NO FUNDS"); a closed road draws a red dashed ring at the town's radius.
  Arcs the attack breaks turn red and stop flowing, and each town shows how many of its people are not reached: those who would have walked to a shelter that closed or lost its money, or out of a town cut off from a shelter outside it; funded transport still gets its riders through.
  These counts come from the plan's arcs, so they leave out people flooded outside every town; the counter shows the Simulation's total ("Sheltered 453, was 960"), and the budget tile shows the budget itself, so a cut drops it.
  A closed road never cuts a town off from a shelter inside its radius (`/api/exposure` lists them per town).
- **Reroute beat (#26):** after the attack, people reroute: the arcs are redrawn to the shelters that still take them under the failure ("Rerouted" stamp), and each town shows how many still reach no shelter.
  Each Round carries `attacked_briefing`, the field briefing for the plan with its attack applied, so the arcs and counts are the Simulation's, not estimated from the planned arcs.
- **Pacing:** beats play from a queue, about 5 s for a plan, 3 s for a verdict, 5 s for an attack and 4 s for a reroute, so the instant engine is watchable; while the next round is on its way, the caption says what the run is doing ("Round 2 · Gemma 4 is attacking the last plan and drafting a stronger one").
- **Progress:** one segment per round plus one for the report, done, current (pulsing) or to come, instead of an estimated percent.
- **Skip and Cancel:** Skip stops the playback and opens the report as soon as the run ends; Cancel returns to the start.
  The report (or the budget question) opens once the last beat has had its time.
- **Arcs, not roads:** arcs are drawn town to shelter because the Simulation moves people over grid steps through dry cells, not along roads; people flooded outside every town get no arc.
- It still never says "stress test".

## The flood looks like a flood (#27)

Agreed on 2026-10-25 for the demo, on the `demo-visuals` branch.

- **Dark basemap:** CARTO dark-matter replaces positron; labels get dark halos, towns are near-white and shelters a brighter green.
- **Flood surface:** zoomed out, the map draws `/api/flood-surface.png` instead of the block squares: each kind's flagged-cell confidence blurred over 4 cells (about 240 m) and drawn where it clears 0.02, at its strongest from 0.12.
  The flagged cells are sparse (34,000 of 2.2 million), so lone speckles fade out and clusters read as water.
  Open water is bright blue and nearly opaque; flooding under canopy is a darker cyan and never as opaque, so it always reads fainter.
  It is display only: the Simulation still uses the binary flagged cells, and the legend says the surface is smoothed.
- **Permanent water:** permanent water carries no evidence, and the surface is drawn beneath the basemap's water so blur cannot spill onto the Gulf, rivers or lakes.
- **Close up:** from zoom 13.5 the 60 m cells and their popups take over as before; the surface fades out over the last half zoom level.
  The zoomed-out block popups are gone with the blocks.
- **FEMA zones:** a checkbox, off by default, since the tint covers most of the area; still context only.
- **Narrow screens:** the start screen fits the area below the start card.
