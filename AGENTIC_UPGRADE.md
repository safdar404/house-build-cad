# Agentic design workspace

This edition centres GharBuilder around Agent Studio, using your own OpenAI key and a Responses/function-calling capable model ID. API billing belongs to your API account. No real API credential was available during development; LLM tests use an offline fake service.

## Use the agent

1. Enter your key in the sidebar password field and your model ID. Test the connection explicitly if desired. The key is not included in project or conversation exports. Cloud secrets may provide OPENAI_API_KEY instead.
2. Create and confirm a project brief through the form or AI interview. AI extraction and floor-plan synthesis use the configured LLM; deterministic geometry and estimation tools calculate their outputs in Python.
3. Open Agent Studio. Select Prepare available project tools. Open Tools & automation, inspect the exact prepared inputs and authorize the stage you want. Preparation alone makes no API call and grants no approval.
4. Ask the agent to inspect your project, plan the next steps or continue the workflow. It can inspect confirmed facts and room summaries, run a ready authorized specialist tool, or record a requested revision and invalidate affected outputs. It stops after one generated output for user review.
5. Review output before continuing. When a plan is approved, select a layout in Floor Plans. Prepare available tools again after upstream revisions or approvals. Revisions change the plan only after generation and review.

## Scope of automation

Automatic preparation can derive bylaw-review, AI-planning, CAD, 3D and IFC requests from approved project sources. Proposed 3D modelling sizes remain visible for explicit input review. No statutory rule, market price, engineering design or sensor observation is invented to make a stage look complete.

Structural, MEP, schedule, cost, labour, digital twin and report tools are available through their existing pages. They require the user's evidence, coefficients, productive durations, crew data, dated rates or monitoring observations. Visiting their generation forms registers prepared requests in Agent Studio. All 13 stages are visible with readiness, status and direct input-page links.

The LLM has four bounded function tools: inspect_project, plan_next_steps, run_stage and request_revision. It cannot approve an output, invoke arbitrary code, read arbitrary files, install packages, contact authorities or run unattended construction operations. History is session-local, restricted to the last 12 text messages per LLM request and can be exported or cleared. API usage and configured price estimates appear in the sidebar.

## Interface

Grouped top navigation frees the sidebar for API/model and session settings. A compact gradient brand header uses a native SVG house-and-agent mark. Cards, typography, stage status and controls use reduced spacing, responsive wrapping and visible keyboard focus. All prior CAD, 3D, IFC, schedule, cost, workforce, monitoring and report pages remain available.

## Verification

The existing 29-test suite passed after the agent changes. All 16 navigation and action tests passed again after the final top-navigation change. Five additional agent tests cover project-inspection function calls, conversation retention, secret-history rejection, automatic preparation without authorization an Agent Studio prepare/authorize/run sequence with no API call, and LLM-directed tool execution that pauses for review. Live OpenAI execution and the Streamlit Cloud rebuild require verification in the deployed environment.
