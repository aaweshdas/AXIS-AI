import os
import requests
import json
import uuid
import asyncio
import threading
import chromadb
import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = os.getenv("AXIS_MODEL", "llama3:8b")
MEMORY_PATH = "axis_memory_db"
TOP_K       = 5           # how many memory chunks to inject per turn

SYSTEM_PROMPT = """You are A.X.I.S. (Autonomous eXecution & Intelligence System), an advanced, highly capable personal AI assistant.
You are brilliant, concise, and deeply loyal to the user.
You have access to a persistent memory database that stores past conversations and lets you recall context across sessions.
When relevant past context is provided at the start of a message (under [MEMORY CONTEXT]), use it naturally to give continuity to the conversation.
Keep replies sharp and clear. Use markdown formatting when explaining code or complex topics."""

# ─────────────────────────────────────────────
#  SOCKET.IO + FASTAPI SETUP
# ─────────────────────────────────────────────
sio       = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app       = FastAPI(title="A.X.I.S API")
socket_app = socketio.ASGIApp(sio, app)

os.makedirs("static", exist_ok=True)
app.mount("/ui", StaticFiles(directory="static", html=True), name="static")

# ─────────────────────────────────────────────
#  CHROMADB PERSISTENT MEMORY
# ─────────────────────────────────────────────
chroma = chromadb.PersistentClient(path=MEMORY_PATH)
memory = chroma.get_or_create_collection("axis_memory")

def store_memory(role: str, text: str):
    """Store a single conversation turn in ChromaDB."""
    memory.add(
        documents=[f"[{role.upper()}]: {text}"],
        ids=[str(uuid.uuid4())]
    )

def retrieve_memory(query: str, top_k: int = TOP_K) -> str:
    """Retrieve semantically relevant past turns for context injection."""
    total = len(memory.get()["ids"])
    if total == 0:
        return ""
    results = memory.query(
        query_texts=[query],
        n_results=min(top_k, total)
    )
    docs = results["documents"][0]
    if not docs:
        return ""
    return "\n".join(docs)

# ─────────────────────────────────────────────
#  OLLAMA STREAMING HELPER
# ─────────────────────────────────────────────
async def stream_ollama(sid: str, messages: list):
    """
    Sends messages to Ollama with streaming=True.
    Emits each token chunk to the browser via Socket.io.
    Returns the full reply as a string.
    """
    full_reply = []
    try:
        with requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "stream": True},
            stream=True,
            timeout=180
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    full_reply.append(token)
                    await sio.emit("token", {"text": token}, to=sid)
                if chunk.get("done"):
                    break
    except Exception as e:
        err = f"\n\n[A.X.I.S ERROR]: {e}"
        await sio.emit("token", {"text": err}, to=sid)
        return err

    return "".join(full_reply)

# ─────────────────────────────────────────────
#  SOCKET.IO EVENTS
# ─────────────────────────────────────────────
@sio.event
async def connect(sid, environ):
    print(f"[AXIS] Client connected: {sid}")
    await sio.emit("status", {"msg": "A.X.I.S online. Ready."}, to=sid)

@sio.event
async def disconnect(sid):
    print(f"[AXIS] Client disconnected: {sid}")

@sio.event
async def chat(sid, data):
    """
    Receives: { "message": "user text" }
    Streams AI tokens back. Stores both user and AI turns in memory.
    """
    user_text = data.get("message", "").strip()
    if not user_text:
        return

    # Retrieve relevant past context
    past_context = retrieve_memory(user_text)
    context_block = ""
    if past_context:
        context_block = f"\n\n[MEMORY CONTEXT — relevant past exchanges]:\n{past_context}\n\n"

    # Build message list
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if context_block:
        messages.append({
            "role": "user",
            "content": context_block + user_text
        })
    else:
        messages.append({"role": "user", "content": user_text})

    # Signal start of stream
    await sio.emit("stream_start", {}, to=sid)

    # Stream Ollama response
    reply = await stream_ollama(sid, messages)

    # Signal end of stream
    await sio.emit("stream_end", {}, to=sid)

    # Persist this turn in ChromaDB
    store_memory("user", user_text)
    if reply:
        store_memory("axis", reply)

@sio.event
async def clear_memory(sid, data):
    """Wipe the entire memory collection and recreate it."""
    global memory
    try:
        chroma.delete_collection("axis_memory")
        memory = chroma.get_or_create_collection("axis_memory")
        await sio.emit("status", {"msg": "Memory cleared. Starting fresh."}, to=sid)
    except Exception as e:
        await sio.emit("status", {"msg": f"Error clearing memory: {e}"}, to=sid)

# ─────────────────────────────────────────────
#  REST ENDPOINTS
# ─────────────────────────────────────────────
@app.get("/api/health")
def health():
    """Simple liveness check for Colab startup validation."""
    mem_count = len(memory.get()["ids"])
    return {"status": "online", "model": MODEL, "memory_entries": mem_count}

@app.post("/api/clear")
def clear_memory_rest():
    """REST endpoint to clear memory (for debugging)."""
    global memory
    try:
        chroma.delete_collection("axis_memory")
        memory = chroma.get_or_create_collection("axis_memory")
        return {"status": "memory cleared"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
