# Actionable workflow update

The screenshot showed Home with descriptive HTML cards and pending metrics. Those cards had no controls, and empty downstream pages only explained missing prerequisites. This update adds:

- Clickable Home links for starting/editing a project and opening every main feature group.
- A direct prerequisite link on each workflow page.
- An API-free project form with editable floor rows, plot dimensions, household, budget and design preferences. Save a draft, review it and confirm it to enter planning. Existing advanced JSON and AI interview options remain available.
- Wrapping workflow status cards so stages are not clipped into a horizontal strip.
- Action tests that submit/confirm requirements and navigate into planning, and rebuild an actual 3D mesh while checking downstream invalidation.

## Start

1. Extract into a new folder. Stop the old Streamlit terminal with Ctrl+C.
2. Run run_windows.bat from this new folder with 64-bit Python 3.12 installed.
3. On Home, choose Start / edit my house project. Fill the form, save, review and confirm.
4. Follow Floor Plans to review bylaw evidence and enter the concept envelope. AI-generated alternatives require an API key and model ID in the sidebar.
5. For a complete no-key trial, choose the demonstration from Home, build it, then explicitly load it into workflow pages. You can edit and regenerate the deterministic stages there.

The 3D, IFC, schedule, cost, labour, monitoring and download tools already contain generation/review/export controls. Their required upstream stages must be reviewed first. This update does not replace real project data with demonstration assumptions, or claim that AI design generation works without an API key.

Native Windows and live OpenAI calls remain untested. See README.md and VALIDATION.md for scope.
