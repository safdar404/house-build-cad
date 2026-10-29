# Connection and input-flow fixes

- The sidebar puts the API key, model ID and Connect & continue action first. A key without a model ID gives a specific prompt. A successful explicit connection check routes into Requirements Chat; repeated continuation reuses the successful check for the same key/model.
- A separate Enter project details without AI action opens the input form without an API call.
- Home shows one next required action and a reviewed-stage progress bar. The detailed stage strip is collapsed so an empty project is not dominated by pending cards. Entering a key enables AI; it does not fabricate a house brief or silently generate outputs.
- The project form has a floor-count control, editable room rows, blank initial budget and field-specific completion messages. Save a draft before changing the floor count to preserve entered rows.
- The agent mark is rendered through native Streamlit image, app-logo and favicon APIs rather than an HTML data URI.
- Light/dark styles include the top header/navigation, secondary buttons, menus, dropdowns, inputs, expanders and tabs. Primary actions retain white text on their coloured background.
- Switching appearance no longer discards prepared agent tools or recreates the API client. A new workspace still receives its own runtime.

Existing review gates remain: confirm the brief, review constraints, set the envelope, generate/review alternatives, select a layout and continue through the specialist tools. Missing rates, engineering assumptions and observations still require real user input.

Validation: existing 34 tests passed after the main changes. Six additional UI/journey tests check the next action, key-without-model feedback, connection-to-form routing with a mocked API probe, native logo/dark styles, floor rows/blank budget, and preservation of prepared tools when switching appearance. No real API credential was used for validation. Live API calls and Cloud deployment must still be verified in the user's session.
