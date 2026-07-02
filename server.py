import os
import requests
import json
import uuid
import asyncio
import threading
import sys
import shutil
import re
import psutil
import urllib.parse
import chromadb
import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ─────────────────────────────────────────────
#  CONFIG & PROMPTS
# ─────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = os.getenv("AXIS_MODEL", "llama3:8b")
MEMORY_PATH = "axis_memory_db"
TOP_K       = 5

# Custom system prompt explaining tool-calling syntax
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
os.makedirs("static/plots", exist_ok=True) # Directory to host generated plots
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
#  AGENT TOOLS EXECUTION LAYER
# ─────────────────────────────────────────────
def run_python_code(code: str) -> dict:
    """Executes code in a sandbox process, captures stdout, and detects new plots."""
    plot_dir = "static/plots"
    # Find files in plots directory before run
    pre_files = set(os.listdir(plot_dir))
    
    # Exec the Python code in a subprocess
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

    # Detect if any new png image was saved in current workspace or plot_dir
    post_files = set(os.listdir("."))
    new_images = []
    
    # Check current directory for new pngs and move them to static/plots
    for file in post_files:
        if file.endswith(".png") and not file.startswith("temp_"):
            dest = os.path.join(plot_dir, file)
            shutil.move(file, dest)
            new_images.append(f"/ui/plots/{file}")
            
    # Check static/plots directory for new files
    for file in os.listdir(plot_dir):
        if file.endswith(".png") and file not in pre_files:
            new_images.append(f"/ui/plots/{file}")

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
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        # Extract title and snippets via regex (minimal parsing without bs4 to stay package independent)
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
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        text = r.text
        # Strip script, style, and HTML elements
        text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^<]+?>', '', text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:60]) # return first 60 lines
    except Exception as e:
        return f"Error scraping website: {e}"

# ─────────────────────────────────────────────
#  OLLAMA STREAMING AGENT CORE
# ─────────────────────────────────────────────
async def get_ollama_reply(sid: str, messages: list) -> str:
    """Handles communications with Ollama, streaming standard tokens, and parsing tool requests."""
    full_text = []
    in_tool_block = False
    
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
                    full_text.append(token)
                    # Check if token is beginning of a tool block
                    current_accumulation = "".join(full_text)
                    if "```tool" in current_accumulation:
                        if not in_tool_block:
                            in_tool_block = True
                            await sio.emit("tool_start", {}, to=sid)
                    else:
                        # Stream standard text token to frontend
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
    # Retrieve memories
    past_context = retrieve_memory(user_text)
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
        reply = await get_ollama_reply(sid, messages)
        
        # Check for tool call blocks: ```tool { ... } ```
        tool_match = re.search(r'```tool\s*(\{.*?\})\s*```', reply, re.DOTALL)
        
        if tool_match:
            # We found a tool call!
            tool_json_str = tool_match.group(1)
            try:
                tool_data = json.loads(tool_json_str)
                tool_name = tool_data.get("tool")
                
                await sio.emit("tool_executing", {"tool": tool_name, "args": tool_data}, to=sid)
                
                tool_result = ""
                images = []
                
                # Execute specific tool
                if tool_name == "python_execute":
                    code = tool_data.get("code", "")
                    exec_result = run_python_code(code)
                    tool_result = f"STDOUT:\n{exec_result['stdout']}\nSTDERR:\n{exec_result['stderr']}\nExit Code: {exec_result['exit_code']}"
                    images = exec_result["images"]
                elif tool_name == "web_search":
                    query = tool_data.get("query", "")
                    tool_result = run_web_search(query)
                elif tool_name == "web_scrape":
                    url = tool_data.get("url", "")
                    tool_result = run_web_scrape(url)
                else:
                    tool_result = f"Unknown tool: {tool_name}"
                
                # Send tool results to user UI
                await sio.emit("tool_result", {
                    "tool": tool_name,
                    "result": tool_result,
                    "images": images
                }, to=sid)
                
                # Feed tool execution result back to LLM context
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
            # No tool call was requested. We are done!
            store_memory("user", user_text)
            store_memory("axis", reply)
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
        # Start reasoning loop in background
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
    """Gets CPU, RAM, Disk, and general system health (vital for Colab profiling)."""
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=None)
    # Virtual Memory
    vm = psutil.virtual_memory()
    # Disk Usage
    disk = psutil.disk_usage("/")
    
    # Try to resolve GPU VRAM usage if NVIDIA GPU is present
    gpu_info = "N/A"
    try:
        import subprocess
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
