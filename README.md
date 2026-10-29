# GharBuilder AI

**Guided choices update:** dropdowns, custom entries, room-count/budget patterns, account-model selection and table-based module inputs are available. See [MODULE_GUIDE.md](MODULE_GUIDE.md) for each module's choices and next actions.

**Start here:** enter your API key and model ID, then press **Connect & continue**. You can also select **Enter project details without AI**. Home shows the next required step. See [UX_FLOW_FIX.md](UX_FLOW_FIX.md) for the latest input, logo and theme fixes.

<img src="assets/agent-mark.svg" alt="GharBuilder AI agent logo" width="72" />

**Agent Studio:** use your own API key and model to inspect project facts, plan next steps, execute reviewed specialist tools and request revisions. Compact grouped navigation keeps connection controls visible. Read [AGENTIC_UPGRADE.md](AGENTIC_UPGRADE.md) for the automation scope and click-through workflow.

**Actionable UI update:** Start from the clickable Home cards or the API-free project form. See ACTIONS_UPDATE.md for the exact click-through workflow.

Agentic House Design & Estimation Studio. This ZIP is the complete assembled project; earlier part ZIPs are not required. It includes the corrected NumPy-aware workflow fingerprint helper.

This reviewed edition adds exact-input authorization controls in Workflow Chat. See REVIEW_REPORT.md for the comparison of all 20 supplied archives and the review findings.

## Run on Windows

Install **64-bit Python 3.12**, extract this folder, and open PowerShell in it:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Alternatively, double-click `run_windows.bat`. Keep the terminal open. Do not use a Python file called `streamlit.py`, `openai.py` or `pandas.py` in this folder. Use the virtual-environment interpreter for every command; activation is unnecessary.

On macOS/Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Or run `bash run_unix.sh`. Open the local URL printed by Streamlit, normally `http://localhost:8501`. Python 3.12/Linux is the validated environment. Windows launch commands are provided but native Windows execution was not tested here. Python 3.15 is not a tested target; native IFC wheel availability matters.

## Try without an API key

Open **Demonstration** and choose **Build separate demonstration workspace**. This creates an isolated, clearly synthetic 10-marla Lahore Ground + 2-floor scenario. Download its exports, or explicitly load it into the workflow pages. Existing session work is replaced only if you choose the replacement checkbox and button.

The downloadable ZIP contains sample outputs. Generated binary samples are excluded from this source repository; generate them from the command line:

```powershell
.\.venv\Scripts\python.exe examples\run_sample.py
```

The example assumes a 30 × 75 ft plot, 225 sq ft/marla, and 5 ft front/rear open spaces. It is **not an LDA-compliant or engineered house design**. Its 5,850 sq ft total covered envelope, hypothetical duration, wage inputs, fees, MEP coefficients and progress observations illustrate software behavior only. The synthetic wage of PKR 100/day deliberately tests arithmetic and is not a market quotation or legal wage assertion.

## Use your own project

1. Enter your OpenAI API key in the sidebar password field, and enter a model ID available to your API project with Responses/function-calling and structured-output support. Use **Test API connection** for an explicit small API request.
2. Open **Requirements Chat**. Provide facts conversationally, a few at a time. Review the extracted brief and correct mistakes before confirming it. The JSON correction option is available for precise edits.
3. On **Floor Plans**, generate and acknowledge the bylaw evidence review. Unverified or missing rules remain undetermined. Enter and explicitly accept a concept envelope; it does not establish statutory approval.
4. Generate coordinated alternatives through the planning agent, review every floor and geometry warning, approve the result, then select one alternative. Generate/review the CAD bundle.
5. Build/review the **3D Model**, inspect floor controls and exploded display, and export assembled GLB/OBJ. Door/window infill must be enabled before IFC export.
6. On **Engineering allowances**, review a candidate grid and optional supplied section dimensions. Enter MEP coefficients only from an explicit project assumption/source. Schema and synthetic example JSON files are included. Unknown sizes stay unresolved.
7. On **BIM & IFC**, add optional element materials, costs, phase and maintenance information. Generate/review IFC4, inspect properties, then download it.
8. On **4D Schedule**, enter duration, crew and curing inputs and a work calendar. Dates for Ramadan/Eid, monsoon effects and holidays must be supplied explicitly; none are guessed. The schedule is an early-start planning baseline without finite-resource levelling.
9. On **Cost Estimation**, choose either the area benchmark or itemized BOQ. Rates Settings supplies editable quotations. Unknown rates and incomplete BOQ scope do not become zero-price construction. Fees/utility extras, taxes and contingency have explicit scope rules. What-if controls do not change the approved design.
10. On **Labour**, allocate each scheduled crew among trades, supply city-specific wages, and review paid versus productive person-days, workforce peaks and alternative contract scenarios.
11. On **Digital Twin**, enter dated task observations. Unreported progress remains unknown. Sensor series are separate simulations with no connected devices or equipment control.
12. On **Reports & Downloads**, assemble only current approved source stages and available geometry exports. Review the package before downloading PDF, Excel or the complete export ZIP.

**Workflow agent** can run prepared, input-authorized specialists or record revision requests. It cannot approve outputs or invent missing driver values. Visit a stage and prepare/review its inputs first. Requirements changes return to the brief; layout changes return to planning. Stale outputs cannot be used as current sources or downloads. Optional specialist explanations are available at review gates when credentials are configured.

## API keys, costs and persistence

The application never writes the entered key to files, exports, project metadata or logs. Credentials and API clients live in the current Streamlit session. A server may provide credentials through environment variables, Streamlit secrets or an owner-managed `.env`; `.env.example` contains no secret. Do not commit your actual `.env` or `.streamlit/secrets.toml`.

There are no automatic requests on startup. The connection test, interview, layout generation, workflow conversation and optional specialist explanations incur API usage when invoked. Session token counts include returned usage for retries. Prices are not hardcoded: add exact model IDs and dated USD-per-million-token prices to `model_pricing.json`. The UI displays a scenario estimate at configured prices, not an API billing statement. ChatGPT subscriptions do not provide API credit.

Project state, private setting overrides, observations and generated models are in session memory. Restarting the server or session can lose unsaved work. Export your files before closing. Project metadata JSON excludes credentials and binaries and is **not a complete session backup/import format**. Shared deployment authentication, a database, role permissions, backups and multi-worker persistence are not implemented. Run on a trusted local/single-user installation until those deployment requirements are added.

## Rates, bylaws and evidence

- `data/rates_pk.json`: seed area scenarios from the user's supplied ranges. Material/fee quotations and most city factors are null. Seed grey/finishing splits are labelled assumptions, not observed averages.
- `data/labour_rates.json`: ten trade entries with no invented wage amounts. The eight-hour day is a modelling convention requiring confirmation, not a legal-hours assertion.
- `data/bylaws.json`: an unverified Lahore/LDA editing template with null numerical limits. This package contains no verified authority bylaw dataset or city seismic-zone lookup.
- `data/calendar_exceptions.json`: editable weekdays and dated productivity exceptions. Curing uses elapsed days; overlapping slowdowns use the minimum factor.
- `data/model_pricing.json`: empty price list until dated model prices are supplied.

Settings edits are schema-validated and private to the session. Export JSON to retain them. `GHARBUILDER_ALLOW_SETTINGS_WRITES=1` enables explicit atomic local writes only for a trusted single-user installation. Never enable it as a substitute for multi-user authorization.

## Drawings, BIM and engineering limits

Plans use room-zone/wall-centre-line coordinates, not final net clear dimensions. Bounds, overlap, counts, door access and continuous stair-zone checks are implemented; these do not certify fire egress, accessibility, stair treads/landings/headroom, structural adequacy, ventilation compliance, detailed MEP or climate performance. Void area without polygon geometry is rejected by the current planner. Detailed irregular/stepped footprints require further professional development.

CAD provides dimensioned PNG/DXF floor plans, site plan, schematic elevation/section, furniture and point/fixture diagrams. Door swings, furniture clearance, electrical circuits and plumbing routes are not final working details. 3D wall strips have real cutouts but may overlap at junctions; mesh volumes are not a measured BOQ. Schematic straight stairs and slab/parapet sizes are accepted modelling assumptions.

IFC4 contains project/site/building/storeys, walls, slabs, doors, windows, openings, stairs and spaces, with deterministic product GUIDs and custom properties. Geometry is metre-based, Z-up in project/OBJ coordinates; GLB exports use glTF Y-up. IFC schema/EXPRESS checks and geometry-engine tests do not establish a certified exchange/model-view deliverable. 4D links are implemented in the schedule/mesh sequence. 5D amounts remain indicative. 6D/7D are MEP allowances and optional sustainability/asset/maintenance metadata; no certified energy engine or live facility integration is claimed.

Final designs require relevant authority approval and review/stamping by a PCATP-registered architect and PEC-registered structural engineer. A site-specific geotechnical investigation and applicable seismic design parameters are required for final structural/foundation design.

## Reports and language

PDFs embed ReportLab's packaged Vera fonts. PDF labels currently require Latin/English text; unsupported scripts fail explicitly rather than producing broken glyphs. Excel preserves Unicode. The language selector translates primary navigation and shared controls; all technical forms/warnings are not fully translated into Urdu. Full Urdu PDF shaping is not implemented.

Excel BOQ detail formulas include cached snapshot amounts and request recalculation on open. Overview values are approved report snapshots; editing the workbook does not revise the app baseline. Native Excel/LibreOffice recalculation was not tested. Sources, effective dates, missing prices and scope limitations are retained. API credentials never belong in report text or source notes.

## Tests and validation

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

Tests include geometry/units, review gates and stale-output detection, NumPy-aware mesh fingerprints, curing/calendar dependencies, cost/allocation reconciliation, ZIP/PDF/Excel/IFC/mesh handling and Streamlit page smoke tests. The synthetic demonstration exercises the complete deterministic pipeline without an API key. Live paid API behavior, Windows-native execution, architectural suitability and construction accuracy are not established by these tests. See `TEST_CHECKLIST.md` and `VALIDATION.md`.

## Main modules

- `app.py`, `ui/`: navigation, shared controls, state, source validation and review gates.
- `agents/`: requirements, compliance, planning, CAD, modeling, structural, MEP, BIM, scheduling, cost, labour, twin, report and function-calling orchestration.
- `tools/`: deterministic geometry, drawing, mesh, IFC, schedule, cost, labour, monitoring, report and pricing functions.
- `pages/`: all workflow pages, engineering controls, settings, workflow chat and demonstration.
- `examples/`: editable synthetic inputs, CLI sample runner and generated sample artifacts.
- `tests/`: repeatable offline tests. System prompts are embedded with their agent classes rather than duplicated in separate prompt files.
