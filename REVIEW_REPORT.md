# Archive and source review

Reviewed on 29 October 2026.

All 20 supplied ZIP archives passed CRC integrity checks and were extracted into separate folders before comparison. Paths were checked to stay within the extraction destination.

The supplied complete package contained all 39 file entries delivered in Parts 1–19: 31 byte-identical entries and eight updated versions. No part file was missing. The complete package had 80 files before this review. Earlier part versions were retained separately during comparison and were not overlaid onto newer files.

## Change made during review

Workflow Chat registered prepared requests but offered no input-authorization control. Added an expandable exact-request review and explicit authorization button for each prepared stage. Changed inputs still require renewed authorization, and generated outputs remain pending separate review. Added an offline regression test for these boundaries. Workflow errors now display as actionable messages in chat.

## Archive comparison

| Part | Path | Complete package |
| --- | --- | --- |
| 1 | `FOLDER_STRUCTURE.txt` | updated in complete |
| 1 | `README.md` | updated in complete |
| 1 | `requirements.txt` | updated in complete |
| 2 | `config.py` | identical |
| 2 | `schemas.py` | identical |
| 3 | `agents/base.py` | identical |
| 3 | `agents/requirements_agent.py` | identical |
| 4 | `agents/compliance_agent.py` | identical |
| 4 | `data/bylaws.json` | identical |
| 5 | `agents/planning_agent.py` | identical |
| 5 | `tools/geometry.py` | identical |
| 6 | `agents/cad_agent.py` | identical |
| 6 | `tools/cad_2d.py` | identical |
| 7 | `agents/modeling_agent.py` | identical |
| 7 | `tools/model_3d.py` | identical |
| 8 | `agents/mep_agent.py` | identical |
| 8 | `agents/structural_agent.py` | identical |
| 9 | `agents/bim_agent.py` | identical |
| 9 | `tools/bim_ifc.py` | identical |
| 10 | `agents/scheduling_agent.py` | identical |
| 10 | `tools/schedule_4d.py` | identical |
| 11 | `agents/cost_agent.py` | identical |
| 11 | `tools/cost.py` | identical |
| 12 | `data/rates_pk.json` | identical |
| 12 | `tools/labour.py` | identical |
| 13 | `agents/labour_agent.py` | identical |
| 13 | `data/labour_rates.json` | identical |
| 14 | `agents/twin_agent.py` | identical |
| 14 | `tools/twin.py` | identical |
| 15 | `agents/report_agent.py` | identical |
| 15 | `tools/report.py` | identical |
| 16 | `agents/orchestrator.py` | identical |
| 16 | `ui/state.py` | updated in complete |
| 17 | `app.py` | updated in complete |
| 17 | `ui/components.py` | updated in complete |
| 18 | `pages/floor_plans.py` | updated in complete |
| 18 | `pages/requirements_chat.py` | identical |
| 19 | `pages/bim_ifc.py` | identical |
| 19 | `pages/model_3d.py` | identical |

## Verification

- Original extracted complete package: all 26 automated tests passed.
- Updated workflow: regression test and all 14 app/page tests passed (15 tests).
- Source and test modules compile successfully.
- Tests use synthetic data and no paid API calls.

The tests cover contracts, geometry and unit checks, workflow invalidation, calendar/cure behavior, IFC schema and report exports. Sample PDF visual review is documented in VALIDATION.md from the original package. Live OpenAI calls, native Windows execution and native Excel recalculation remain untested. Engineering, bylaws and prices require verified project evidence and professional review.

## Contents and use

This is the complete Python source project, including agents, deterministic tools, all 13 pages, data schemas, settings, examples, exports, tests and launch scripts. See README.md for setup and limitations. No earlier part archive is required.
