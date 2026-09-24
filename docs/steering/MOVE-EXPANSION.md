# Intermediate and advanced move expansion

Record date: September 4, 2026. Status: implemented draft definitions; instructor review and release acceptance remain open.

The expansion adds **43 named definitions across all 22 approved groups**, with **86 right/left-oriented runtime variants**. There are **216 reference entries**: the original 173 remain first, in their original order, followed by 43 expansion references. These figures count specific selected variations, not every possible use of a dance term or every move used in line dancing.

## Data and preservation

- `data/expanded-moves.json` contains the 43 definitions, exact event offsets and durations, support transitions, turn amounts, source links and review metadata.
- `data/step-database.json` preserves the original 173 identities, names, aliases and structural mechanics. The existing Wizard notation is corrected to `1-2&`; ambiguity notes and links to selected expansion variants are metadata additions. No original move is removed.
- `data/common-move-explanations.json` contains independently worded draft explanations for all 216 reference identities. An explanation does not override a move's structural mechanics.
- Saved choreography retains its selected event definition, provenance and definition hash. Updating the bundled library must not silently replace a saved dance's move definition.

The pack contains **39 definitions with specified timing, support and rotation fields**, and **four provisional technical cues**: Spiral lock, Spiral hitch, Moonwalk and Roger Rabbit. The latter deliberately leave starting foot, support changes and rotation unspecified. Their two-count display window is provisional, not a standard duration or a completed mechanical definition. Mirroring produces an alternate orientation of the cue; it does not establish an unknown lead foot.

“Specified” means that the encoded fields can be checked for consistency. It does not mean that an instructor has approved the wording, foot placement, style, teachability or physical execution. All 43 definitions carry `mechanics_draft_instructor_review_pending` and `generator_eligible: false`. They are available for manual choreography and remain excluded from automatic generation until a separate review and eligibility decision is recorded.

## Coverage

Counts below are canonical definitions before mirroring. The local suggested difficulty labels total **11 Improver (`I`), 17 Intermediate (`INT`) and 15 Advanced (`A`)**. These are application draft labels, not association certification; the difficulty of a whole dance also depends on its transitions, tempo, phrasing and execution.

| Approved group | Definitions |
|---|---:|
| Wizard / Dorothy | 1 |
| Turning sailors | 4 |
| Turning triples | 4 |
| Heel jack | 2 |
| Vaudeville | 1 |
| Kick-ball-cross | 1 |
| Heel/toe switches | 4 |
| Forward locking triple | 1 |
| Anchor step | 1 |
| Nightclub basic | 2 |
| Samba step | 2 |
| Volta turn | 4 |
| Diamond | 2 |
| Hinge turn | 2 |
| Spiral turn | 2 |
| Twinkle | 2 |
| Pencil turn | 3 |
| Figure-eight turn | 1 |
| Spiral lock | 1 |
| Spiral hitch | 1 |
| Moonwalk | 1 |
| Roger Rabbit | 1 |
| **Total** | **43** |

Turning sailors, turning triples and volta turns each have separate quarter-, half-, three-quarter- and full-turn definitions. Half and full diamonds have an explicit diagonal entry constraint. Pencil variations distinguish turn amount and the supporting foot. Selected variants must retain those distinctions in their names, mirrored instructions, previews and exports.

## Sources and authorship

The seven records below are links for factual context and instructor follow-up. A source link is not a redistribution license, an endorsement, or evidence that the source approves every selected event model. Difficulty guidance and a worked choreography example have different evidentiary roles from a glossary definition.

| Source record | Role |
|---|---|
| [AJ Dance Sheffield — Glynn Rodgers glossary](https://www.ajdancesheffield.com/_files/ugd/2a7956_a35972b446e0473ea9125bc9cd6170ac.pdf) | Named move and rhythm reference |
| [National Teachers Association — Line Dance Level Breakdown](https://www.ntadance.com/line-dance-level-breakdown/) | Difficulty and teaching progression context |
| [Linedancer — Guide to Line Dance Level Definitions](https://www.linedancerweb.com/viewpdf.php?dance=46311) | Whole-dance level context |
| [Taipei International Line Dance Association — terminology](https://www.taipeilinedance.org.tw/about/terminology) | Terminology reference |
| [Maddison Glover — Johnnie Walker Blues, original choreographer's sheet hosted on CopperKnob](https://www.copperknob.co.uk/stepsheets/CD952FD/johnnie-walker-blues) | A worked single-support half-pencil example, not a universal pencil definition |
| [STEEZY / Charise Roberts — Moonwalk (Backslide)](https://www.steezy.co/posts/how-to-do-the-moonwalk-backslide) | Named technique context for a provisional cue |
| [STEEZY / Charise Roberts — Roger Rabbit](https://www.steezy.co/posts/how-to-do-the-roger-rabbit) | Named technique context for a provisional cue |

Explanations and event instructions were newly authored for this pack. The expansion imports no source PDF, diagram, video, photograph or copied teaching passage into the application. Historical private reference materials remain subject to their existing release exclusions. Authorship notes describe this work's provenance; they do not provide a copyright certification or transfer rights in third-party content. No source is represented as providing a verified bulk reusable database or API.

## Recorded implementation checks

These are intermediate implementation results, **not the final full-suite result or a release approval**:

- **10 passed** in the data-authoring check: seven tests in `app/tests/test_expanded_move_data.py` and three in `app/tests/test_common_move_explanations.py`. They check the original 173-entry preservation digest, the approved group set, exact event intervals, specific rhythm/turn distinctions, unknown-field handling, catalog links and explanation coverage.
- **100 passed** in the independently run combined expansion/compiler/history check reported by the runtime integration reviewer. All 86 runtime variants passed the loader and compiler consistency checks; the four provisional definitions remained unverified by the compiler.

These two results should not be added together as a claim of 110 distinct final regression tests. Mechanical consistency checks do not validate teaching prose or demonstrate a dance on the floor. A subsequent focused review identified mirrored direction/angle wording and editor foot-state/unknown-display issues for correction and regression coverage; the final implementation report must record their actual resolution and the later full-suite result.

## Instructor review and acceptance

Before promoting a definition or allowing automatic generation, record the reviewer, date, exact definition hash, demonstrated variant, findings and disposition. Review both orientations and realistic transitions, not just the canonical isolated pattern.

1. Confirm the name and aliases describe the exact selected variation. Separate common alternative endings or rhythms instead of silently treating them as interchangeable.
2. Demonstrate each action at a manageable tempo. Confirm count onset and duration, weight-bearing foot, free foot, travel, turn direction and magnitude, and any required entry facing.
3. Verify mirrored prose and numeric mechanics agree. Specifically check diagonal diamonds, multi-turn triples, figure-eight wording, and half/full pencil turns.
4. Join the move to preceding and following steps. Confirm non-weight-bearing actions use the free foot, unknown transitions stay unverified, and UI previews and exported sheets retain the same instructions.
5. Resolve each provisional cue with a clearly named, demonstrated sequence before asserting its timing or mechanics. Keep ambiguous variants descriptive and excluded from generation.
6. Review suggested level, tempo suitability, space requirements and teaching clarity. Record any restrictions rather than inferring them solely from count totals.
7. After corrections, rerun data, mirror, compiler, save/reopen, export and relevant editor regression checks. Approve generator eligibility separately, with transition constraints and evidence; instructor review does not enable generation automatically.

The existing sprint backlog is `ROADMAP.md`. No `SPRINTS.md` was present when this record was added; no alternate backlog file was changed by this documentation task.
