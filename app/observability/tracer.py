"""
Observability — dual output:
  1. Arize Phoenix via OpenTelemetry (OTLP HTTP) — visual trace viewer at :6006
  2. JSONL file on disk — backup + eval runner reads tool calls from here

Phoenix shows:
  - Every request as a root span
  - Each tool call as a child span with input/output/latency
  - Each LLM call as a child span
  - RBAC rejections as span events
  - Total request latency

Setup is called once at app startup from main.py.
"""
import json
import time
import uuid
import asyncio
import logging
import os
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

# ── OpenTelemetry setup ────────────────────────────────────────────────────
_tracer = None
_otel_enabled = False


def setup_phoenix():
    """
    Initialise OTEL tracing to Arize Phoenix.
    Called once at startup. Safe to call even if Phoenix is not running
    — falls back to JSONL-only mode silently.
    """
    global _tracer, _otel_enabled

    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "")
    if not endpoint:
        logger.info("PHOENIX_COLLECTOR_ENDPOINT not set — OTEL disabled, using JSONL only")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": "acme-operations-assistant"})
        provider = TracerProvider(resource=resource)

        # Phoenix OTLP endpoint
        otlp_endpoint = endpoint.rstrip("/") + "/v1/traces"
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("acme.agent")
        _otel_enabled = True
        logger.info(f"Phoenix OTEL tracing enabled → {otlp_endpoint}")

    except Exception as e:
        logger.warning(f"Phoenix OTEL setup failed ({e}) — falling back to JSONL only")
        _otel_enabled = False


# ── JSONL file writer ──────────────────────────────────────────────────────
def _trace_path() -> Path:
    p = Path(settings.log_dir) / "traces.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

_lock = asyncio.Lock()

async def _write(event: dict):
    async with _lock:
        with _trace_path().open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")


# ── RequestTrace ───────────────────────────────────────────────────────────
class RequestTrace:
    """
    One instance per /chat request.
    Creates a root OTEL span for the request and child spans for each
    tool call and LLM turn. Also writes every event to JSONL.
    """

    def __init__(self, user: str, query: str):
        self.trace_id  = str(uuid.uuid4())
        self.user      = user
        self.query     = query
        self.start     = time.monotonic()
        self.tool_calls: list[dict] = []

        # Start OTEL root span
        self._root_span = None
        if _otel_enabled and _tracer:
            self._root_span = _tracer.start_span(
                name="chat_request",
                attributes={
                    "acme.trace_id": self.trace_id,
                    "acme.user":     user,
                    "acme.query":    query[:200],
                },
            )

    async def record_tool_call(
        self, tool: str, args: dict, result: dict, latency_ms: float
    ):
        """Record a tool call — OTEL child span + JSONL."""
        event = {
            "trace_id":   self.trace_id,
            "type":       "tool_call",
            "tool":       tool,
            "args":       args,
            "result_keys": list(result.keys()) if isinstance(result, dict) else str(result)[:100],
            "latency_ms": round(latency_ms, 1),
        }
        self.tool_calls.append(event)
        await _write(event)

        # OTEL child span for the tool call
        if _otel_enabled and _tracer and self._root_span:
            from opentelemetry import trace
            ctx = trace.set_span_in_context(self._root_span)
            with _tracer.start_as_current_span(
                name=f"tool.{tool}",
                context=ctx,
                attributes={
                    "tool.name":       tool,
                    "tool.args":       json.dumps(args, default=str)[:500],
                    "tool.result":     json.dumps(result, default=str)[:500],
                    "tool.latency_ms": round(latency_ms, 1),
                },
            ):
                pass  # span closes immediately — latency already measured

    async def record_llm_turn(
        self, role: str, content_summary: str, latency_ms: float
    ):
        """Record an LLM call — OTEL child span + JSONL."""
        event = {
            "trace_id":   self.trace_id,
            "type":       "llm_turn",
            "role":       role,
            "summary":    content_summary[:200],
            "latency_ms": round(latency_ms, 1),
        }
        await _write(event)

        if _otel_enabled and _tracer and self._root_span:
            from opentelemetry import trace
            ctx = trace.set_span_in_context(self._root_span)
            with _tracer.start_as_current_span(
                name="llm.completion",
                context=ctx,
                attributes={
                    "llm.role":       role,
                    "llm.summary":    content_summary[:200],
                    "llm.latency_ms": round(latency_ms, 1),
                },
            ):
                pass

    async def record_rbac_rejection(self, tool: str, role: str):
        """Record a permission denied event."""
        event = {
            "trace_id": self.trace_id,
            "type":     "rbac_rejection",
            "tool":     tool,
            "role":     role,
        }
        await _write(event)

        if _otel_enabled and (_root_span := self._root_span):
            _root_span.add_event(
                "rbac_rejection",
                attributes={"tool": tool, "role": role},
            )

    async def finish(self, response_summary: str, error: str | None = None):
        """Close the trace — write summary event and end root OTEL span."""
        total_ms = round((time.monotonic() - self.start) * 1000, 1)
        event = {
            "trace_id":        self.trace_id,
            "type":            "request_complete",
            "user":            self.user,
            "query_summary":   self.query[:150],
            "tool_calls":      [t["tool"] for t in self.tool_calls],
            "response_summary": response_summary[:200],
            "total_latency_ms": total_ms,
            "error":           error,
        }
        await _write(event)

        if self._root_span:
            self._root_span.set_attribute("acme.total_latency_ms", total_ms)
            self._root_span.set_attribute("acme.tools_called", json.dumps(
                [t["tool"] for t in self.tool_calls]
            ))
            if error:
                self._root_span.set_attribute("acme.error", error)
                from opentelemetry.trace import StatusCode
                self._root_span.set_status(StatusCode.ERROR, error)
            self._root_span.end()
