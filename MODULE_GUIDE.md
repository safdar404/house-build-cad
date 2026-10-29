# GharBuilder input and module guide

The normal workflow now offers choices, custom entries, guided fields and editable tables. A suggested preference or starting pattern is still subject to the user's review. Blank numeric evidence is not converted into a price, bylaw or engineering value.

| Module | Easier controls | Next action |
| --- | --- | --- |
| Connection | Load available models from the user's API account, then select or type an ID. No model-list call occurs on startup. | Connect & continue. The selected model must support the APIs used by the agents. |
| Home | One next-step link and expandable workflow progress. | Open the current required input/review step. |
| Requirements | City, authority, style, stairs and dining dropdowns with custom entries; accessibility/green multi-selects; budget and per-floor room-count patterns. | Review each floor and confirm the normalized brief. |
| Floor Plans | Selectable envelope-source notes and layout improvement priorities, plus custom revision text. | Review constraints, set the envelope, generate/review and select an alternative. |
| 3D Model | Existing geometry controls, colour pickers and visibility options remain available. | Review proposed modelling assumptions, build and approve the model. |
| BIM & IFC | Material and phase choices include explicit Not specified / Not assigned; actual references and dates remain project inputs. | Save relevant element information and generate IFC. |
| Schedule | Workday multi-select, dated exception table and numeric task recipes. Optional starting-value dropdowns fill only missing recipe cells. | Supply the source and review every recipe, especially curing periods. |
| Cost | Friendly benchmark/BOQ method labels, rate-item/basis/category choices, editable fee and payment tables. | Review scope and calculate the indicative estimate. Unknown prices remain unresolved. |
| Labour | Main-trade dropdown in the crew table, bounded worker/wage inputs and selectable source descriptions. | Review crew totals, quotations and contract scope. |
| Digital Twin | Single-task progress form with task and percentage choices, or the original bulk table; budget/scope choices and room/floor selectors. | Save real observations, then generate a reviewed snapshot. Simulation stays separate. |
| Structural | Choose coordination-only mode when section sizes are unknown, guided supplied dimensions, or advanced JSON. | Generate coordination information; supplied sizes do not establish structural adequacy. |
| MEP | Explicit Not supplied mode, guided coefficient fields with previously supplied values, or advanced JSON. | Obtain professional coefficients if absent. Continue other tools without inventing MEP values. |
| Settings | Guided fields, dates, nested-profile editing and flattened quotation/evidence tables; advanced JSON remains available. | Review and apply validated private session settings, then export them. |
| Agent Studio | All-stage links, prepared requests, input authorization and reviewed execution. | Prepare available tools, review their inputs and ask the agent to continue. |
| Reports / demo | Existing date, source-inclusion, export and explicitly labelled synthetic-demo controls were reviewed and remain available. | Download current reviewed outputs or try the isolated demonstration. |

## Important distinctions

- City and authority lists are input conveniences, not verification of jurisdiction or current rules.
- Budget presets are amounts selected by the user, not construction quotations.
- Room patterns are starting counts applied to the listed floors; edit individual floors before confirmation.
- Bulk schedule values are supplied planning scenarios, not measured productivity or recommended engineering curing periods. Existing nonempty cells are preserved.
- Source choices describe the user's information. Independent verification still requires the schema's source, effective date and reviewer information where applicable.
- The account model list is not a guarantee of Responses, structured-output or tool support. Test the connection and use a compatible model.
- Advanced editors remain for custom schemas/new profiles; normal cost, calendar, section, MEP and settings flows no longer require typing JSON.

## Validation

50 automated tests passed with no paid API calls. Tests cover the prior calculation/export workflow, new choice controls, native input navigation, room-count presets, account-model selection with a fake provider, preservation of unknown prices and recipe values, guided settings application and actual estimate generation from the table controls. Live provider access uses the user's key only when explicitly requested inside the application.
