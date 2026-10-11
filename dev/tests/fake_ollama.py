# Minimal Ollama stand-in for testing streaming without a GPU model.
import json, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
app = FastAPI()
@app.get("/api/tags")
def tags(): return {"models": [{"name": "qwen3:8b"}, {"name": "gemma3:4b"}]}
@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    assert body["think"] is False and body["keep_alive"]
    if body["model"] not in ("qwen3:8b", "gemma3:4b"):
        return JSONResponse({"error": f"model '{body['model']}' not found"}, 404)
    last = body["messages"][-1]["content"]
    reply = f"That sounds great! You said: {last}. What else did you do?"
    async def gen():
        for w in reply.split(" "):
            await asyncio.sleep(0.03)
            yield json.dumps({"message": {"role": "assistant", "content": w + " "}, "done": False}) + "\n"
        yield json.dumps({"message": {"content": ""}, "done": True}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")
