from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from auth.keycloak import get_current_user, require_permission
from agent.runner import run_agent
from cache.redis_client import clear_session, get_session
from observability.tracer import RequestTrace
from skills.escalation import run_escalation_skill

router = APIRouter()


class ChatRequest(BaseModel):
    query: str


class EscalationRequest(BaseModel):
    customer_name: str


@router.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    trace = RequestTrace(user=user["username"], query=req.query)
    result = await run_agent(req.query, user, trace)
    return {"response": result, "trace_id": trace.trace_id}


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(get_current_user)):
    trace = RequestTrace(user=user["username"], query=req.query)

    async def generator():
        result = await run_agent(req.query, user, trace)
        # Emit in chunks to simulate streaming (full streaming requires async Claude)
        chunk_size = 80
        for i in range(0, len(result), chunk_size):
            yield f"data: {json.dumps({'delta': result[i:i+chunk_size]})}\n\n"
        yield f"data: {json.dumps({'done': True, 'trace_id': trace.trace_id})}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/session/clear")
async def clear_chat_session(user: dict = Depends(get_current_user)):
    await clear_session(user["sub"])
    return {"status": "cleared"}


@router.get("/session/history")
async def get_history(user: dict = Depends(get_current_user)):
    history = await get_session(user["sub"])
    return {"history": history}


@router.post("/skills/escalation")
async def escalation_skill(
    req: EscalationRequest,
    user: dict = Depends(get_current_user),
):
    trace = RequestTrace(user=user["username"], query=f"escalation:{req.customer_name}")
    result = await run_escalation_skill(req.customer_name, user, trace)
    await trace.finish(result[:200])
    return {"brief": result, "trace_id": trace.trace_id}


@router.get("/me")
async def whoami(user: dict = Depends(get_current_user)):
    return user


@router.get("/admin/traces")
async def get_traces(
    limit: int = 50,
    user: dict = Depends(require_permission("read")),
):
    from pathlib import Path
    from config import settings
    trace_file = Path(settings.log_dir) / "traces.jsonl"
    if not trace_file.exists():
        return {"traces": []}
    lines = trace_file.read_text().strip().split("\n")
    traces = [json.loads(l) for l in lines if l]
    return {"traces": traces[-limit:]}
