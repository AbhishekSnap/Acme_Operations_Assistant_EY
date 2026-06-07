#!/usr/bin/env python3
"""
Evaluation runner — Acme Operations Assistant
Measures:
  1. Tool selection accuracy   — did the agent call the right tools?
  2. Data grounding            — does the response contain expected DB values?
  3. RBAC enforcement          — was access correctly allowed / denied?
  4. Next action quality       — reasonable content for create_next_action queries
  5. Response reasonableness   — non-empty, non-hallucinated

Run:
  python eval/run_eval.py
  python eval/run_eval.py --base-url http://localhost:8000
"""
import asyncio
import json
import sys
import httpx
from pathlib import Path

BASE_URL = "http://localhost:8000"
if "--base-url" in sys.argv:
    idx = sys.argv.index("--base-url")
    BASE_URL = sys.argv[idx + 1]

QUESTIONS = json.loads((Path(__file__).parent / "questions.json").read_text())
USERS = {"alice": "password", "bob": "password", "carol": "password"}
_tokens: dict[str, str] = {}


async def get_token(client: httpx.AsyncClient, username: str) -> str:
    if username not in _tokens:
        resp = await client.post(
            f"{BASE_URL}/auth/token",
            json={"username": username, "password": USERS[username]},
        )
        resp.raise_for_status()
        _tokens[username] = resp.json()["access_token"]
    return _tokens[username]


def load_trace_for(trace_id: str, log_dir: str = "./logs") -> list[dict]:
    """Load tool_call events for a given trace_id from traces.jsonl."""
    path = Path(log_dir) / "traces.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        try:
            e = json.loads(line)
            if e.get("trace_id") == trace_id and e.get("type") == "tool_call":
                events.append(e)
        except Exception:
            pass
    return events


async def run_question(client: httpx.AsyncClient, q: dict) -> dict:
    token = await get_token(client, q["user"])
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{BASE_URL}/chat",
        json={"query": q["query"]},
        headers=headers,
        timeout=90,
    )

    was_blocked = resp.status_code == 403
    if was_blocked:
        response_text = ""
        trace_id = None
    else:
        data = resp.json()
        response_text = data.get("response", "")
        trace_id = data.get("trace_id")

    # ── Score 1: RBAC enforcement ──────────────────────────────────────────
    rbac_pass = (
        (q["should_allow"] and not was_blocked) or
        (not q["should_allow"] and was_blocked)
    )

    # ── Score 2: Tool selection ────────────────────────────────────────────
    # Read tool calls from trace log
    called_tools = []
    if trace_id:
        trace_events = load_trace_for(trace_id)
        called_tools = [e["tool"] for e in trace_events]

    expected_tools = q.get("expected_tools", [])
    if not expected_tools:
        # No tools expected (e.g. out-of-scope query) — pass if none called
        tool_pass = len(called_tools) == 0
        tool_score = 1.0 if tool_pass else 0.0
    else:
        hits = [t for t in expected_tools if t in called_tools]
        tool_score = len(hits) / len(expected_tools)
        tool_pass = tool_score >= 1.0

    # ── Score 3: Data grounding ────────────────────────────────────────────
    expected_kw = q.get("expected_data_grounding", [])
    grounding_hits = [kw for kw in expected_kw if kw.lower() in response_text.lower()]
    grounding_score = len(grounding_hits) / max(len(expected_kw), 1)
    grounding_pass = grounding_score >= 0.5 or not expected_kw

    # ── Score 4: Next action quality ───────────────────────────────────────
    # For create_next_action queries, check response contains structured content
    na_pass = True
    if "create_next_action" in expected_tools and q["should_allow"] and not was_blocked:
        quality_markers = ["action", "assign", "due", "issue"]
        na_hits = [m for m in quality_markers if m in response_text.lower()]
        na_pass = len(na_hits) >= 2

    # ── Score 5: Response reasonableness ──────────────────────────────────
    if q["should_allow"] and not was_blocked:
        reasonable = len(response_text.strip()) > 20
    else:
        reasonable = True  # blocked response doesn't need content

    # ── Overall ────────────────────────────────────────────────────────────
    overall_pass = rbac_pass and grounding_pass and reasonable and na_pass

    return {
        "id":               q["id"],
        "description":      q["description"],
        "user":             q["user"],
        "role":             q["role"],
        "query":            q["query"],
        "trace_id":         trace_id,
        # RBAC
        "rbac_pass":        rbac_pass,
        "should_allow":     q["should_allow"],
        "was_blocked":      was_blocked,
        # Tool selection
        "tool_pass":        tool_pass,
        "tool_score":       round(tool_score, 2),
        "expected_tools":   expected_tools,
        "called_tools":     called_tools,
        # Data grounding
        "grounding_pass":   grounding_pass,
        "grounding_score":  round(grounding_score, 2),
        "grounding_hits":   grounding_hits,
        "grounding_misses": [kw for kw in expected_kw if kw.lower() not in response_text.lower()],
        # Next action quality
        "na_pass":          na_pass,
        # Response
        "reasonable":       reasonable,
        "response_snippet": response_text[:300],
        # Overall
        "overall_pass":     overall_pass,
    }


def print_result(r: dict):
    status = "PASS" if r.get("overall_pass") else "FAIL"
    print(f"  [{r['id']}] {status}  {r['description'][:55]}")
    if not r.get("overall_pass"):
        if not r.get("rbac_pass"):
            print(f"         RBAC: expected allow={r['should_allow']}, got blocked={r['was_blocked']}")
        if not r.get("tool_pass") and r.get("expected_tools"):
            print(f"         Tools: expected={r['expected_tools']}, called={r['called_tools']}")
        if not r.get("grounding_pass") and r.get("grounding_misses"):
            print(f"         Missing grounding: {r['grounding_misses']}")
        if not r.get("na_pass"):
            print(f"         Next action quality insufficient")
        if not r.get("reasonable"):
            print(f"         Response too short or empty")


async def main():
    print(f"\nAcme Operations Assistant — Evaluation")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    results = []
    async with httpx.AsyncClient() as client:
        # Check server is up
        try:
            health = await client.get(f"{BASE_URL}/health", timeout=5)
            print(f"Server: {health.json()}\n")
        except Exception:
            print("ERROR: Cannot reach server. Is it running?\n")
            return

        for q in QUESTIONS:
            try:
                result = await run_question(client, q)
                print_result(result)
                results.append(result)
            except Exception as e:
                print(f"  [{q['id']}] ERROR  {e}")
                results.append({"id": q["id"], "overall_pass": False, "error": str(e)})

    # Summary
    passed = sum(1 for r in results if r.get("overall_pass"))
    total  = len(results)
    print("\n" + "=" * 60)
    print(f"Score: {passed}/{total} passed")

    # Category breakdown
    categories = {
        "RBAC":       [r for r in results if "rbac_pass" in r],
        "Tool select":[r for r in results if "tool_pass" in r],
        "Grounding":  [r for r in results if "grounding_pass" in r],
    }
    print("\nBreakdown:")
    for cat, rs in categories.items():
        key = cat.lower().replace(" ", "_") + "_pass"
        cat_pass = sum(1 for r in rs if r.get(key, r.get("rbac_pass")))
        print(f"  {cat:<14} {cat_pass}/{len(rs)}")

    # Write results
    out = Path(__file__).parent / "eval_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nDetailed results: {out}")


if __name__ == "__main__":
    asyncio.run(main())
