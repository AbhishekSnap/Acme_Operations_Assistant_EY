"""
MCP Server — exposes Acme tools over HTTP+SSE (MCP protocol).
Runs as a separate container; the app container calls it via HTTP.
Keeping tool definitions here means the agent core has no hard-coded SQL.
"""
import json
import asyncio
import os
from typing import AsyncGenerator

import asyncpg
from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="Acme MCP Server")

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def get_conn():
    return await asyncpg.connect(DATABASE_URL)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def tool_list_customers() -> dict:
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            "SELECT id, name, company, tier, account_manager FROM customers ORDER BY company"
        )
        return {"customers": [dict(r) for r in rows], "count": len(rows)}
    finally:
        await conn.close()


async def tool_get_customer_profile(customer_name: str) -> dict:
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM customers WHERE LOWER(name) LIKE LOWER($1) OR LOWER(company) LIKE LOWER($1)",
            f"%{customer_name}%",
        )
        if not row:
            return {"error": f"No customer found matching '{customer_name}'"}
        return dict(row)
    finally:
        await conn.close()


async def tool_get_all_open_issues() -> dict:
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT i.id, i.title, i.status, i.priority, i.created_at,
                   c.name AS contact_name, c.company
            FROM issues i
            JOIN customers c ON c.id = i.customer_id
            WHERE i.status IN ('open', 'in_progress')
            ORDER BY
              CASE i.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                              WHEN 'medium' THEN 3 ELSE 4 END,
              c.company
            """
        )
        return {"issues": [dict(r) for r in rows], "count": len(rows)}
    finally:
        await conn.close()


async def tool_get_open_issues(customer_name: str) -> dict:
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT i.id, i.title, i.status, i.priority, i.created_at, i.updated_at
            FROM issues i
            JOIN customers c ON c.id = i.customer_id
            WHERE (LOWER(c.name) LIKE LOWER($1) OR LOWER(c.company) LIKE LOWER($1))
              AND i.status IN ('open', 'in_progress')
            ORDER BY
              CASE i.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                              WHEN 'medium' THEN 3 ELSE 4 END
            """,
            f"%{customer_name}%",
        )
        return {"issues": [dict(r) for r in rows], "count": len(rows)}
    finally:
        await conn.close()


async def tool_summarise_issue(issue_id: int) -> dict:
    conn = await get_conn()
    try:
        issue = await conn.fetchrow("SELECT * FROM issues WHERE id = $1", issue_id)
        if not issue:
            return {"error": f"Issue {issue_id} not found"}
        updates = await conn.fetch(
            "SELECT author, note, created_at FROM issue_updates WHERE issue_id = $1 ORDER BY created_at",
            issue_id,
        )
        next_acts = await conn.fetch(
            "SELECT action, assigned_to, due_date, status FROM next_actions WHERE issue_id = $1",
            issue_id,
        )
        return {
            "issue": dict(issue),
            "updates": [dict(u) for u in updates],
            "next_actions": [dict(a) for a in next_acts],
        }
    finally:
        await conn.close()


async def tool_update_issue(
    issue_id: int,
    status: str | None = None,
    priority: str | None = None,
    note: str | None = None,
    updated_by: str = "system",
) -> dict:
    conn = await get_conn()
    try:
        issue = await conn.fetchrow("SELECT * FROM issues WHERE id = $1", issue_id)
        if not issue:
            return {"error": f"Issue {issue_id} not found"}

        # Build SET clause dynamically from whichever fields were supplied
        fields, values = [], []
        if status:
            fields.append(f"status = ${len(values)+1}")
            values.append(status)
        if priority:
            fields.append(f"priority = ${len(values)+1}")
            values.append(priority)

        if fields:
            fields.append("updated_at = NOW()")
            values.append(issue_id)
            await conn.execute(
                f"UPDATE issues SET {', '.join(fields)} WHERE id = ${len(values)}",
                *values,
            )

        if note:
            await conn.execute(
                "INSERT INTO issue_updates (issue_id, author, note) VALUES ($1, $2, $3)",
                issue_id, updated_by, note,
            )

        updated = await conn.fetchrow("SELECT * FROM issues WHERE id = $1", issue_id)
        return {"updated": dict(updated), "note_added": bool(note)}
    finally:
        await conn.close()


async def tool_create_next_action(
    issue_id: int, action: str, assigned_to: str, due_date: str, created_by: str
) -> dict:
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO next_actions (issue_id, action, assigned_to, due_date, created_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, issue_id, action, assigned_to, due_date, status, created_by, created_at
            """,
            issue_id, action, assigned_to, date.fromisoformat(due_date), created_by,
        )
        return dict(row)
    finally:
        await conn.close()


TOOL_REGISTRY = {
    "list_customers": {
        "fn": tool_list_customers,
        "schema": {
            "name": "list_customers",
            "description": "List all customers with their industry, tier, and account manager.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    "get_customer_profile": {
        "fn": tool_get_customer_profile,
        "schema": {
            "name": "get_customer_profile",
            "description": "Retrieve the profile of a customer by name.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Full or partial customer name"}
                },
                "required": ["customer_name"],
            },
        },
    },
    "get_all_open_issues": {
        "fn": tool_get_all_open_issues,
        "schema": {
            "name": "get_all_open_issues",
            "description": "Retrieve all open or in-progress issues across every customer, ordered by priority.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    "get_open_issues": {
        "fn": tool_get_open_issues,
        "schema": {
            "name": "get_open_issues",
            "description": "Retrieve all open or in-progress issues for a given customer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Full or partial customer name"}
                },
                "required": ["customer_name"],
            },
        },
    },
    "summarise_issue": {
        "fn": tool_summarise_issue,
        "schema": {
            "name": "summarise_issue",
            "description": "Summarise the full history of a specific issue, including all updates and next actions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "integer", "description": "The numeric issue ID"}
                },
                "required": ["issue_id"],
            },
        },
    },
    "update_issue": {
        "fn": tool_update_issue,
        "schema": {
            "name": "update_issue",
            "description": "Update the status and/or priority of an issue, and optionally add a progress note. Requires support_user or admin role.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "issue_id":    {"type": "integer", "description": "The numeric issue ID"},
                    "status":      {"type": "string",  "description": "New status: open | in_progress | resolved | closed"},
                    "priority":    {"type": "string",  "description": "New priority: critical | high | medium | low"},
                    "note":        {"type": "string",  "description": "Progress note to append to the issue history"},
                    "updated_by":  {"type": "string",  "description": "Username of the person making the update"},
                },
                "required": ["issue_id"],
            },
        },
    },
    "create_next_action": {
        "fn": tool_create_next_action,
        "schema": {
            "name": "create_next_action",
            "description": "Create a recommended next action for a specific issue. Requires admin or support_user role.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "integer"},
                    "action": {"type": "string"},
                    "assigned_to": {"type": "string"},
                    "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "created_by": {"type": "string"},
                },
                "required": ["issue_id", "action", "assigned_to", "due_date", "created_by"],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# MCP HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/tools")
async def list_tools():
    return {"tools": [v["schema"] for v in TOOL_REGISTRY.values()]}


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict
    role: str = "sales_user"


RESTRICTED_TOOLS = {
    "update_issue":      {"admin", "support_user"},
    "create_next_action": {"admin"},
}


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest):
    entry = TOOL_REGISTRY.get(req.tool_name)
    if not entry:
        return JSONResponse({"error": f"Unknown tool: {req.tool_name}"}, status_code=404)
    if req.tool_name in RESTRICTED_TOOLS:
        if req.role not in RESTRICTED_TOOLS[req.tool_name]:
            return JSONResponse(
                {"error": f"Permission denied: role '{req.role}' cannot call '{req.tool_name}'"},
                status_code=403,
            )
    try:
        result = await entry["fn"](**req.arguments)
        return {"result": result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# MCP SSE endpoint — streams tool list then keeps connection alive
@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    async def event_stream() -> AsyncGenerator[str, None]:
        tools_payload = json.dumps({"type": "tools_list", "tools": [v["schema"] for v in TOOL_REGISTRY.values()]})
        yield f"data: {tools_payload}\n\n"
        # Keep-alive
        while not await request.is_disconnected():
            await asyncio.sleep(15)
            yield ": keep-alive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
