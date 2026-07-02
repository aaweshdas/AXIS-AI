# 🧠 A.X.I.S — Autonomous eXecution & Intelligence System
### Version 2.0 (Agent OS)

A.X.I.S (Autonomous eXecution & Intelligence System) is a fully local, open-source personal AI Agent built with a streaming **FastAPI + Socket.io** backend, persistent **ChromaDB vector memory**, and a premium **dark-mode cybernetic Web UI**. 

Designed to run seamlessly inside **Google Colab** utilizing the free Tesla T4 GPU, A.X.I.S is exposed to the public web with zero configuration using **Cloudflare Tunnels**, turning a Colab notebook into a private, secure, voice-enabled assistant server with a Python code interpreter sandbox and live web search capabilities.

---

## 🔮 Key Core Capabilities

### 1. 🐍 Interactive Python Code Interpreter
A.X.I.S has a sandboxed Python execution engine. If a query requires math, data analysis, file parsing, or charting:
* The agent writes a Python script.
* The backend runs it locally within the Google Colab container in a separate process.
* **Auto-Plot Interceptor**: If the Python code uses libraries like `matplotlib` or `seaborn` and saves a chart (e.g., `plt.savefig()`), the backend automatically catches the generated image and renders it **inline** in the chat bubble.

### 2. 🔍 Live Web Search & Scraping
Equipped with real-time web crawlers, the agent can bypass the LLM's training cutoff date:
* **DDG Scraper**: Autonomously parses DuckDuckGo HTML results for the latest news and links.
* **Content Scraper**: Fetches raw HTML page content, cleans script and CSS style sheets, parses readable text, and feeds it into the LLM's prompt context.

### 3. 🎙️ Bi-Directional Voice Mode
Experience a touchless audio interface directly in your browser:
* **Voice Input (STT)**: Dictate your commands using web-native speech recognition by clicking the microphone button.
* **Voice Output (TTS)**: When enabled, the agent reads its answers back to you in real-time using built-in natural-sounding voice engines.

### 4. 💾 Persistent Vector Memory (ChromaDB)
Unlike basic chat interfaces that forget context once you close the page:
* Every conversation turn is embedded and logged into a persistent local **ChromaDB** vector database.
* When you ask a question, the backend queries the database for semantically similar past exchanges and injects them as `[MEMORY CONTEXT]` to maintain continuity across sessions.

### 5. 📊 Live System Resource HUD
The sidebar features a real-time hardware status monitor pulling directly from `/api/system_stats` to track:
* **CPU Consumption** (via `psutil`)
* **RAM Allocation** (system allocations in GB)
* **GPU Accelerator Status** (displays the active Nvidia GPU, such as `Tesla T4`, queried directly from `nvidia-smi`).

---

## 🛠️ Architecture & Tech Stack

```
   [ Web Browser Client ] 
             │
             ▼ (HTTPS/WSS via Cloudflare Tunnel)
     [ FastAPI Server ] 
      ├── Socket.io (ASGI) ➔ Event Loop / Token Streaming
      ├── ChromaDB ➔ Vector Database (Memory Context)
      ├── System Metrics (psutil + nvidia-smi)
      └── Sandbox execution (subprocess shell)
             │
             ▼ (Port 11434 Local Request)
        [ Ollama Engine ] (Tesla T4 GPU Core)
```

| Layer | Technologies |
| :--- | :--- |
| **LLM Inference** | Ollama (`llama3:8b`, `mistral`, `gemma:2b`) |
| **Vector Memory** | ChromaDB Client (Persistent Store) |
| **Web Server** | FastAPI, Uvicorn, Python-SocketIO, HTTPX |
| **Tunnelling** | Cloudflare Tunnels (TryCloudflare Wrapper) |
| **Frontend** | Vanilla HTML5, CSS3 (Futuristic Cyber Glassmorphism), ES6 JavaScript |
| **Runtime Environment** | Google Colab VM Container (Ubuntu Linux / Python 3.10+ / CUDA) |

---

## 🚀 Google Colab Deployment Guide

Deploying A.X.I.S onto Google Colab takes less than 5 minutes and runs on a free Nvidia T4 GPU:

1. Open [Google Colab](https://colab.research.google.com/).
2. Select the **Upload** tab and upload the [colab_launcher.ipynb](file:///s:/All%20Code/Antigravity/AXIS_AI/colab_launcher.ipynb) file.
3. Make sure GPU is enabled: Go to **Runtime** ➔ **Change runtime type** ➔ Select **T4 GPU**.
4. Run the cells sequentially from top to bottom:
   * **Cell 1**: Downloads the Ollama Linux binary directly, configures system directories, and launches the server.
   * **Cell 2**: Downloads the `llama3:8b` model weights (approx 4.7 GB).
   * **Cell 3**: Installs all required python packages.
   * **Cell 4**: Clones/pulls the web assets from GitHub.
   * **Cell 5**: Launches FastAPI and establishes the secure Cloudflare tunnel.
5. In the output of **Cell 5**, you will see a public link:
   `https://xxxx.trycloudflare.com/ui`
6. Open this link in any browser to start using A.X.I.S!

---

## 📂 File Directory Structure

```
AXIS_AI/
├── colab_launcher.ipynb   # Google Colab notebook script
├── server.py              # FastAPI backend server with Socket.io & ChromaDB
├── requirements.txt       # Python dependencies list
├── .gitignore             # File exclusion settings
├── README.md              # Documentation (This file)
└── static/                # Web UI frontend assets
    ├── index.html         # Cyber glassmorphic layout
    ├── index.css          # Sci-fi themed glowing animations and styles
    ├── index.js           # Socket.io polling, Voice STT/TTS, metrics updater
    └── plots/             # Directory where Python sandbox plots are saved
```

---

## 💻 Local Development (Local Setup)

To run A.X.I.S locally on your machine instead of Google Colab:

### Prerequisites
* Install Python 3.10+
* Install [Ollama](https://ollama.com/) locally.

### Steps
1. **Pull the model**:
   ```bash
   ollama pull llama3:8b
   ```
2. **Clone the Repository**:
   ```bash
   git clone https://github.com/aaweshdas/AXIS-AI.git
   cd AXIS-AI
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Start the Server**:
   ```bash
   uvicorn server:socket_app --reload --port 8000
   ```
5. **Open in Browser**:
   Open `http://localhost:8000/ui` in your browser.
