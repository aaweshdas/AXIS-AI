import os
import json
import uuid
import asyncio
import subprocess
import shutil
import re
import psutil
import urllib.parse
import httpx
import chromadb
import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# ─────────────────────────────────────────────
#  CONFIG & PROMPTS
# ─────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = os.getenv("AXIS_MODEL", "llama3:8b")
MEMORY_PATH = "axis_memory_db"
TOP_K       = 5

SYSTEM_PROMPT = """You are A.X.I.S. (Autonomous eXecution & Intelligence System), a personal agent with full capability to execute actions.
You have access to a Python sandbox environment (Google Colab container) and the web.

You can use the following tools when needed:
1. Python Code Interpreter: Run calculations, data analysis, or create plots.
2. Web Search: Look up real-time information or search Google.
3. Web Scraper: Read the text content of a specific web URL.

To run a tool, you must output a special JSON code block exactly as shown below:
```tool
{
  "tool": "python_execute",
  "code": "print('hello world')"
}
```
Or for web search:
```tool
{
  "tool": "web_search",
  "query": "current weather in New York"
}
```
Or for web scraping:
```tool
{
  "tool": "web_scrape",
  "url": "https://example.com"
}
```

Rules:
1. Output ONLY the tool JSON block inside the ```tool code block if you need to run a tool. Do not add any text before or after it in that step.
2. Once the server executes the tool, you will receive the output. You can then analyze the result and give your final answer or execute another tool.
3. When writing Python code that generates a plot or chart, always save it as a file: `plt.savefig('plot.png')`. The system will automatically display the image in the chat.
4. If no tools are required, answer directly using clear markdown formatting."""

# ─────────────────────────────────────────────
#  SOCKET.IO + FASTAPI SETUP
# ─────────────────────────────────────────────
sio       = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app       = FastAPI(title="A.X.I.S Agent OS")
socket_app = socketio.ASGIApp(sio, app)

os.makedirs("static", exist_ok=True)
os.makedirs("static/plots", exist_ok=True)
app.mount("/ui", StaticFiles(directory="static", html=True), name="static")

# ─────────────────────────────────────────────
#  CHROMADB PERSISTENT MEMORY
# ─────────────────────────────────────────────
chroma = chromadb.PersistentClient(path=MEMORY_PATH)
memory = chroma.get_or_create_collection("axis_memory")

def store_memory(role: str, text: str):
    """Store conversation in memory DB."""
    try:
        memory.add(
            documents=[f"[{role.upper()}]: {text}"],
            ids=[str(uuid.uuid4())]
        )
    except Exception as e:
        print(f"Memory store error: {e}")

def retrieve_memory(query: str, top_k: int = TOP_K) -> str:
    """Get context search from ChromaDB."""
    total = len(memory.get()["ids"])
    if total == 0:
        return ""
    try:
        results = memory.query(query_texts=[query], n_results=min(top_k, total))
        docs = results["documents"][0]
        return "\n".join(docs) if docs else ""
    except Exception as e:
        print(f"Memory query error: {e}")
        return ""

# ─────────────────────────────────────────────
#  AGENT TOOLS EXECUTION LAYER (SYNCHRONOUS)
# ─────────────────────────────────────────────
def run_python_code(code: str) -> dict:
    """Executes code in a sandbox process, captures stdout, and detects new plots."""
    import sys
    plot_dir = "static/plots"
    pre_files = set(os.listdir(plot_dir)) if os.path.exists(plot_dir) else set()
    os.makedirs(plot_dir, exist_ok=True)
    
    temp_script = f"temp_{uuid.uuid4().hex}.py"
    with open(temp_script, "w", encoding="utf-8") as f:
        f.write(code)
        
    try:
        res = subprocess.run(
            [sys.executable, temp_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        stdout = res.stdout
        stderr = res.stderr
        exit_code = res.returncode
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = "Execution timed out (30s limit)"
        exit_code = -1
    finally:
        if os.path.exists(temp_script):
            os.remove(temp_script)

    post_files = set(os.listdir("."))
    new_images = []
    
    for file in post_files:
        if file.endswith(".png") and not file.startswith("temp_"):
            dest = os.path.join(plot_dir, file)
            try:
                shutil.move(file, dest)
                new_images.append(f"/ui/plots/{file}")
            except Exception as e:
                print(f"Error moving plot: {e}")
            
    if os.path.exists(plot_dir):
        for file in os.listdir(plot_dir):
            if file.endswith(".png") and file not in pre_files:
                path = f"/ui/plots/{file}"
                if path not in new_images:
                    new_images.append(path)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "images": new_images
    }

def run_web_search(query: str) -> str:
    """Performs a live DuckDuckGo HTML search and returns structured snippet results."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        r = httpx.get(url, headers=headers, timeout=10.0)
        r.raise_for_status()
        snippets = []
        matches = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        titles = re.findall(r'<a class="result__url"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        
        for i in range(min(5, len(matches))):
            clean_snippet = re.sub('<[^<]+?>', '', matches[i]).strip()
            clean_title = re.sub('<[^<]+?>', '', titles[i]).strip()
            snippets.append(f"- **{clean_title}**: {clean_snippet}")
            
        return "\n".join(snippets) if snippets else "No search results found."
    except Exception as e:
        return f"Error searching the web: {e}"

def run_web_scrape(url: str) -> str:
    """Scrapes raw web page text content and strips HTML tags."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = httpx.get(url, headers=headers, timeout=10.0)
        r.raise_for_status()
        text = r.text
        text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^<]+?>', '', text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:60])
    except Exception as e:
        return f"Error scraping website: {e}"

# ─────────────────────────────────────────────
#  OLLAMA STREAMING AGENT CORE (NON-BLOCKING)
# ─────────────────────────────────────────────
async def get_ollama_reply_async(sid: str, messages: list) -> str:
    """Handles async communications with Ollama, preventing event loop blocking."""
    full_text = []
    in_tool_block = False
    
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST", 
                OLLAMA_URL, 
                json={"model": MODEL, "messages": messages, "stream": True}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_text.append(token)
                        current_accumulation = "".join(full_text)
                        if "```tool" in current_accumulation:
                            if not in_tool_block:
                                in_tool_block = True
                                await sio.emit("tool_start", {}, to=sid)
                        else:
                            await sio.emit("token", {"text": token}, to=sid)
                    if chunk.get("done"):
                        break
    except Exception as e:
        err = f"\n\n[A.X.I.S Server Error]: {e}"
        await sio.emit("token", {"text": err}, to=sid)
        return err

    return "".join(full_text)

async def agent_loop(sid: str, user_text: str):
    """Core reasoning loop of A.X.I.S. Supports multiple tool execution loops per turn."""
    past_context = await asyncio.to_thread(retrieve_memory, user_text)
    context_block = f"\n\n[MEMORY CONTEXT]:\n{past_context}\n\n" if past_context else ""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context_block + user_text}
    ]

    await sio.emit("stream_start", {}, to=sid)

    max_loops = 5
    loop_count = 0
    
    while loop_count < max_loops:
        loop_count += 1
        reply = await get_ollama_reply_async(sid, messages)
        
        tool_match = re.search(r'```tool\s*(\{.*?\})\s*```', reply, re.DOTALL)
        
        if tool_match:
            tool_json_str = tool_match.group(1)
            try:
                tool_data = json.loads(tool_json_str)
                tool_name = tool_data.get("tool")
                
                await sio.emit("tool_executing", {"tool": tool_name, "args": tool_data}, to=sid)
                
                tool_result = ""
                images = []
                
                if tool_name == "python_execute":
                    code = tool_data.get("code", "")
                    # Run CPU-bound subprocess in a thread pool to avoid blocking async event loop
                    exec_result = await asyncio.to_thread(run_python_code, code)
                    tool_result = f"STDOUT:\n{exec_result['stdout']}\nSTDERR:\n{exec_result['stderr']}\nExit Code: {exec_result['exit_code']}"
                    images = exec_result["images"]
                elif tool_name == "web_search":
                    query = tool_data.get("query", "")
                    # Run IO-bound scraping in a thread pool
                    tool_result = await asyncio.to_thread(run_web_search, query)
                elif tool_name == "web_scrape":
                    url = tool_data.get("url", "")
                    tool_result = await asyncio.to_thread(run_web_scrape, url)
                else:
                    tool_result = f"Unknown tool: {tool_name}"
                
                await sio.emit("tool_result", {
                    "tool": tool_name,
                    "result": tool_result,
                    "images": images
                }, to=sid)
                
                messages.append({"role": "assistant", "content": reply})
                messages.append({
                    "role": "user",
                    "content": f"[TOOL RESULT ({tool_name})]:\n{tool_result}\n\nPlease proceed to analyze this result and continue."
                })
                
            except Exception as parse_err:
                err_msg = f"Failed to parse tool JSON: {parse_err}"
                await sio.emit("tool_result", {"tool": "error", "result": err_msg}, to=sid)
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": f"[SYSTEM ERROR]: {err_msg}"})
        else:
            await asyncio.to_thread(store_memory, "user", user_text)
            await asyncio.to_thread(store_memory, "axis", reply)
            break

    await sio.emit("stream_end", {}, to=sid)

# ─────────────────────────────────────────────
#  SOCKET.IO EVENTS
# ─────────────────────────────────────────────
@sio.event
async def connect(sid, environ):
    print(f"[AXIS Agent] Connected: {sid}")
    await sio.emit("status", {"msg": "A.X.I.S. Core online. Sandbox tools loaded."}, to=sid)

@sio.event
async def disconnect(sid):
    print(f"[AXIS Agent] Disconnected: {sid}")

@sio.event
async def chat(sid, data):
    user_text = data.get("message", "").strip()
    if user_text:
        asyncio.create_task(agent_loop(sid, user_text))

@sio.event
async def clear_memory(sid, data):
    global memory
    try:
        chroma.delete_collection("axis_memory")
        memory = chroma.get_or_create_collection("axis_memory")
        await sio.emit("status", {"msg": "Core memory collection cleared."}, to=sid)
    except Exception as e:
        await sio.emit("status", {"msg": f"Failed to clear memory: {e}"}, to=sid)

# ─────────────────────────────────────────────
#  SYSTEM STATS & APIS
# ─────────────────────────────────────────────
@app.get("/api/system_stats")
def system_stats():
    cpu_percent = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    
    gpu_info = "N/A"
    try:
        gpu_raw = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True
        )
        gpu_info = gpu_raw.strip()
    except Exception:
        pass

    return {
        "cpu": cpu_percent,
        "ram_used": round(vm.used / (1024 ** 3), 2),
        "ram_total": round(vm.total / (1024 ** 3), 2),
        "ram_percent": vm.percent,
        "disk_free": round(disk.free / (1024 ** 3), 2),
        "disk_total": round(disk.total / (1024 ** 3), 2),
        "gpu": gpu_info
    }

@app.get("/api/health")
def health():
    mem_count = len(memory.get()["ids"])
    return {"status": "online", "model": MODEL, "memory_entries": mem_count}
