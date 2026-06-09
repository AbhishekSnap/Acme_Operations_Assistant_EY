# AI Tool Usage Notes

## Overview

Claude Code was used as a coding assistant throughout this project. All architectural decisions, design choices, and trade-offs were made by me. AI was used to accelerate implementation of components where the design was already decided, not to determine what to build or how the system should work.

---

## What I used AI for

**Boilerplate and scaffolding**
I had a clear picture of the component structure before writing any code. Once I had decided on FastAPI + asyncpg + LiteLLM + Redis + Keycloak, I used Claude Code to generate the initial file structure, Dockerfile patterns, and requirements files. These are mechanical tasks that do not require design judgement.

**SQL schema and seed data**
I defined the entities and relationships myself (customers, issues, issue_updates, next_actions, users). I asked Claude Code to translate that into CREATE TABLE statements and generate representative seed rows. I reviewed the schema, added missing constraints, and adjusted the data to ensure it covered all the test scenarios I had in mind.

**FastAPI route and Pydantic patterns**
FastAPI has well-established conventions for dependency injection, bearer token extraction, and response models. I used Claude Code to generate the initial route skeletons following those patterns, then modified the auth middleware, RBAC enforcement, and error handling myself.

**CSS and frontend layout**
The colour palette and dark/light theme requirements were mine. I specified the exact hex values and the behaviour I wanted (sidebar always dark, toggle on login page and topbar). Claude Code generated the CSS custom property structure which I then adjusted and tested in the browser.

---

## What I reviewed and corrected

Every piece of generated code was read before it was used. Several issues required my intervention:

- **JWT validation**: The initial pattern used token introspection (a round-trip to Keycloak per request). I changed it to local JWKS validation, which is the correct production approach for performance and resilience.
- **RBAC enforcement**: The first pass put all access checks in the agent system prompt only. I identified that this is not a real security boundary and added a second enforcement layer in the MCP server, so even direct API calls cannot bypass permissions.
- **Keycloak realm JSON**: Generated users were missing `emailVerified`, `firstName`, and `requiredActions` fields, which caused "account not fully set up" errors. I diagnosed this by reading the Keycloak logs and corrected the realm import file.
- **asyncpg date handling**: The `create_next_action` tool was passing a date string directly to asyncpg, which expects a `datetime.date` object. I caught this from the 500 error in testing and added the `date.fromisoformat()` conversion.
- **Customer search bug**: The initial SQL for customer lookup only queried the `name` column, not the `company` column. I identified this when searching for "TechCorp Ltd" returned no results and fixed the WHERE clause to search both.
- **Agent tool-use loop**: The loop structure, iteration cap, and message format for `tool_result` blocks were written by me. This is the core of the agentic behaviour and I did not delegate it.

---

## What I did not delegate to AI

- The decision to use MCP as a separate container rather than inline function calls. This was a deliberate architectural choice to demonstrate tool/agent decoupling.
- The two-layer RBAC design (system prompt + MCP enforcement). Security-critical logic requires human ownership.
- The Redis usage split: session memory vs tool result cache. The TTL values (1hr session, 2min cache) were chosen based on my own reasoning about the use case.
- The Escalation Skill design: the decision to make it a deterministic multi-step workflow rather than a freeform agent call.
- The evaluation set: I designed the 10 questions, the grounding keywords, and the scoring dimensions.

---

## What I would not trust AI for on a client engagement

- Any code on the authentication or authorisation path, without thorough manual review and penetration testing.
- Database schema migrations on live data.
- Code that processes or stores PII or compliance-sensitive information.
- Infrastructure-as-code for production environments, particularly IAM roles and network policies.
- Anything where the cost of an undetected error is high and the error may not surface immediately in testing.

In all of these areas, AI can assist with drafting, but a human engineer must own, understand, and be accountable for every line.
