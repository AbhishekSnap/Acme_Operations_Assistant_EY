"""
Customer Escalation Summary Skill.

A Skill is a reusable, structured LLM workflow - distinct from a single prompt call.
This one:
  1. Detects escalation intent in the user query
  2. Fetches customer profile + open issues via MCP tools
  3. Feeds the structured data into a focused summarisation prompt
  4. Returns a formatted escalation brief

It is invoked transparently by the agent runner when the query matches;
it can also be called directly via the /skills/escalation endpoint.
"""
import re
import json
from litellm import completion
from config import settings
from agent.mcp_client import call_tool
from observability.tracer import RequestTrace

ESCALATION_KEYWORDS = re.compile(
    r"\b(escalat|escalation brief|executive summary|executive brief|status report)\w*\b",
    re.IGNORECASE,
)

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

ESCALATION_PROMPT = """You are preparing a concise escalation brief for a senior manager at Acme Operations.

Customer profile:
{profile}

Open issues:
{issues}

Issue histories:
{histories}

Rules:
- If the customer profile contains an "error" key, state clearly that the customer was not found and stop.
- If there are no open issues, state "No open issues found for this customer" under Active Issues and omit Key Risks and Recommended Immediate Actions.
- If any field in the profile is missing or null, note it as "Not recorded" rather than omitting it.
- Never invent data that is not present above.

Produce a structured escalation brief with these sections:
1. **Customer Overview** - tier, account manager, contact
2. **Active Issues** - table: Issue | Priority | Status | Age (or "No open issues" if none)
3. **Key Risks** - top 2-3 risks from the open issues (omit section if no issues)
4. **Recommended Immediate Actions** - bullet list, ordered by priority (omit section if no issues)
5. **Missing Information** - list any data gaps that would be needed for a complete assessment (omit if none)

Be factual, grounded in the data above, and keep the brief under 400 words."""


async def run_escalation_skill(customer_name: str, user: dict, trace: RequestTrace) -> str:
    # Step 1: customer profile
    profile, p_lat = await call_tool("get_customer_profile", {"customer_name": customer_name})
    await trace.record_tool_call("get_customer_profile", {"customer_name": customer_name}, profile, p_lat)

    if "error" in profile:
        return f"Could not generate escalation brief: {profile['error']}"

    # Step 2: open issues
    issues, i_lat = await call_tool("get_open_issues", {"customer_name": customer_name})
    await trace.record_tool_call("get_open_issues", {"customer_name": customer_name}, issues, i_lat)

    # Step 3: per-issue history
    raw_issues = issues.get("issues", [])
    histories: dict[int, dict] = {}
    for issue in raw_issues:
        issue_id = issue["id"]
        history, h_lat = await call_tool("summarise_issue", {"issue_id": issue_id})
        await trace.record_tool_call("summarise_issue", {"issue_id": issue_id}, history, h_lat)
        histories[issue_id] = history

    # Step 4: rank issues by priority in Python
    ranked_issues = sorted(
        raw_issues,
        key=lambda i: PRIORITY_ORDER.get(i.get("priority", "low"), 3),
    )

    # Step 5: single LLM call with all collected data
    prompt = ESCALATION_PROMPT.format(
        profile=json.dumps(profile, indent=2, default=str),
        issues=json.dumps({"issues": ranked_issues, "count": len(ranked_issues)}, indent=2, default=str),
        histories=json.dumps(histories, indent=2, default=str),
    )

    response = completion(
        model=settings.claude_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


_STRIP_PREFIXES = re.compile(r"^(client|account|customer|the)\s+", re.IGNORECASE)

def _extract_customer(query: str) -> str | None:
    """Simple heuristic: look for 'for <Name>' or 'about <Name>'."""
    m = re.search(r"(?:for|about|on|regarding)\s+([A-Z][a-zA-Z\s]{2,30}?)(?:\s+customer|\s+account|[,.]|$)", query)
    if m:
        name = _STRIP_PREFIXES.sub("", m.group(1).strip())
        return name or None
    # Fallback: capitalised two-word sequence
    m = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", query)
    return m.group(1) if m else None


async def maybe_invoke_skill(query: str, user: dict, trace: RequestTrace) -> str | None:
    if not ESCALATION_KEYWORDS.search(query):
        return None
    customer = _extract_customer(query)
    if not customer:
        return None
    return await run_escalation_skill(customer, user, trace)
