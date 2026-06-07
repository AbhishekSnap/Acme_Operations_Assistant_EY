"""
Agent runner — Claude tool-use loop.
1. Build messages from session history + current query
2. Call Claude with available tools (fetched from MCP server)
3. On tool_use blocks: call MCP, append results, loop
4. On end_turn or max_iterations: return final text
"""
import time
import json
from litellm import completion
from typing import AsyncGenerator

from config import settings
from cache.redis_client import get_session, append_session, cache_get, cache_set
from agent.mcp_client import get_tool_schemas, call_tool
from observability.tracer import RequestTrace
from skills.escalation import maybe_invoke_skill

SYSTEM_PROMPT = """You are Acme Operations Assistant, an internal enterprise AI for Acme's
sales, support, and operations staff.

You have access to tools that query live operational data. Always use tools to answer
factual questions; do not fabricate data. When the user asks about a customer, issue,
or next action, call the relevant tool first.

Respect data access based on the user's role:
- sales_user: may read customer profiles and issues only
- support_user: may read and update issues
- admin: full access including creating next actions

Formatting rules (strictly follow these):
- Never use emojis or icons of any kind.
- Never use em dashes (--). Use a comma, colon, or period instead.
- Use markdown tables for structured data.
- Use **bold** for field names and key terms.
- Be concise, professional, and grounded in the data you retrieve.

Current user context will be provided in each message."""

MAX_ITERATIONS = 8


async def run_agent(
    query: str,
    user: dict,
    trace: RequestTrace,
    stream: bool = False,
) -> AsyncGenerator[str, None] | str:
    # Load conversation history from Redis session
    history = await get_session(user["sub"])

    # Check if a skill should handle this query
    skill_result = await maybe_invoke_skill(query, user, trace)
    if skill_result:
        await append_session(user["sub"], "user", query)
        await append_session(user["sub"], "assistant", skill_result)
        await trace.finish(skill_result[:200])
        if stream:
            async def _skill_gen():
                yield skill_result
            return _skill_gen()
        return skill_result

    tools = await get_tool_schemas()
    messages = list(history) + [{"role": "user", "content": query}]
    await append_session(user["sub"], "user", query)

    final_text = ""
    for iteration in range(MAX_ITERATIONS):
        t0 = time.monotonic()
        system_msg = SYSTEM_PROMPT + f"\n\nUser: {user['username']} | Roles: {', '.join(user['roles'])} | Permissions: {', '.join(user['permissions'])}"
        response = completion(
            model=settings.claude_model,
            max_tokens=2048,
            messages=[{"role": "system", "content": system_msg}] + messages,
            tools=tools,
        )
        llm_latency = (time.monotonic() - t0) * 1000
        msg = response.choices[0].message
        await trace.record_llm_turn("assistant", str(msg.content or "")[:200], llm_latency)

        # Collect text and tool_call blocks
        tool_uses = msg.tool_calls or []
        if msg.content:
            final_text = msg.content

        stop_reason = response.choices[0].finish_reason
        if not tool_uses or stop_reason == "end_turn" or stop_reason == "stop":
            break

        # Append assistant turn
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": tool_uses})

        # Execute all tool calls (RBAC enforcement)
        tool_results = []
        for tool_use in tool_uses:
            tool_name = tool_use.function.name
            tool_args = json.loads(tool_use.function.arguments)

            # Enforce write permissions at app layer in addition to agent prompt
            if tool_name == "create_next_action" and "create_next_action" not in user["permissions"]:
                result = {"error": f"Permission denied: role {user['roles']} cannot create next actions"}
                latency_ms = 0.0
                await trace.record_rbac_rejection(tool_name, user["roles"][0] if user["roles"] else "unknown")
            else:
                cache_key = f"tool:{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                cached = await cache_get(cache_key)
                if cached is not None:
                    result, latency_ms = cached, 0.0
                else:
                    result, latency_ms = await call_tool(tool_name, tool_args, role=user["roles"][0] if user["roles"] else "sales_user")
                    if "error" not in result:
                        await cache_set(cache_key, result, ttl=120)

            await trace.record_tool_call(tool_name, tool_args, result, latency_ms)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_use.id,
                "content": json.dumps(result, default=str),
            })

        messages.extend(tool_results)

    await append_session(user["sub"], "assistant", final_text)
    await trace.finish(final_text[:200])
    return final_text
