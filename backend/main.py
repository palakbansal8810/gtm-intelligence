import json
import time
import logging
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchaesterator import Orchestrator
from memory import vector_memory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gtm_backend")
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW = 60  # seconds
_rate_windows: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(client_ip: str):
    now = time.time()
    window = _rate_windows[client_ip]
    # Remove old entries
    _rate_windows[client_ip] = [t for t in window if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_windows[client_ip]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")
    _rate_windows[client_ip].append(now)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GTM Intelligence System starting up")
    yield
    logger.info("GTM Intelligence System shutting down")
    
app = FastAPI(title="GTM Intelligence API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "memory": vector_memory.summary(),
        "timestamp": time.time(),
    }

@app.get("/api/memory")
async def get_memory():
    return {
        "summary": vector_memory.summary(),
        "entry_ids": vector_memory.get_all_ids(),
    }
@app.post("/api/run")
async def run_pipeline(request: Request, body: QueryRequest):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if len(query) > 500:
        raise HTTPException(status_code=400, detail="Query too long (max 500 chars)")

    logger.info(f"Pipeline triggered: '{query}' from {client_ip}")

    async def event_stream():
        orchestrator = Orchestrator()
        try:
            async for event in orchestrator.run(query):
                event_type = event.get("event", "update")
                yield sse_format(event_type, event)
                await asyncio.sleep(0)  
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            yield sse_format("error", {
                "event": "error",
                "agent": "orchestrator",
                "message": f"Pipeline error: {str(e)}",
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)