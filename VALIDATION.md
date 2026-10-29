# Validation record

Validated on 2026-10-29 with 64-bit Linux and Python 3.12.14.

- Installed requirements.txt into a new isolated virtual environment; pip check found no broken requirements.
- All 26 automated tests passed in the clean environment. The suite checks the home screen and all 13 pages, typed contracts, unit/geometry guards, workflow approval and stale-source checks, calendar and curing behavior, and report exports.
- The complete synthetic 10-marla Lahore Ground + 2 scenario generated CAD, meshes, IFC, schedule, cost, labour, monitoring and report outputs without API calls.
- IFC schema validation, PDF parsing, mesh references, and Excel formula/cache checks are included in the automated tests.
- All five pages of the sample PDF were rendered and visually inspected for clipping and overlap.

See TEST_CHECKLIST.md for interactive checks. Sample results are under examples/sample_outputs and can be regenerated using examples/run_sample.py.

## Scope of verification

No real OpenAI API credential was supplied. Live model access, response quality, billing, and production API behavior require testing with your own account. Native Windows execution and native Excel recalculation were not tested. Workbook structure and cached totals were checked programmatically. This is preliminary concept coordination software; synthetic examples do not verify engineering, building regulations, market prices or construction safety.
