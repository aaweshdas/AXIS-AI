# 🧠 A.X.I.S — Autonomous eXecution & Intelligence System

A fully local, open-source personal AI assistant with **persistent vector memory**, a premium **dark-mode Web UI**, and a streaming **FastAPI + Socket.io** backend — designed to run entirely inside **Google Colab** (free T4 GPU) and be accessed from any browser via a **public ngrok URL**.

---

## ✨ Features

* 🤖 **Ollama LLM Integration**: Runs `llama3:8b` (or `mistral`, `gemma:2b`) locally on Colab's free GPU — fully offline after model download.
* 💾 **Persistent ChromaDB Memory**: All conversation turns are stored as vector embeddings and retrieved semantically on each new message, giving the AI long-term contextual memory.
* ⚡ **Real-time Streaming**: Responses stream token-by-token to the browser via Socket.io — no waiting for the full reply.
* 🌐 **Public ngrok URL**: Exposes the local FastAPI server via a public HTTPS URL, accessible from any device.
* 💅 **Premium Dark-Mode UI**: A glassmorphism-styled chat interface with typing indicators, message history, and a memory panel in the sidebar.
* 🗑️ **Memory Management**: One-click "Clear Memory" button resets the ChromaDB collection for a fresh session.

---

## 🚀 How to Run in Google Colab

1. Open [Google Colab](https://colab.research.google.com/) and make sure **Runtime → Change runtime type → T4 GPU** is selected.
2. Upload `colab_launcher.ipynb` or open it directly from GitHub.
3. In **Cell 4**, update `REPO_URL` to point to your GitHub fork.
4. Run all 6 cells **from top to bottom**.
5. After Cell 5, a live URL like `https://xxxx.ngrok.io/ui` will be printed. Open it in any browser!

> ⏱️ **First run takes ~5 minutes** (Ollama install + `llama3:8b` download, ~4.7 GB).  
> Subsequent Colab sessions are faster if you use Google Drive mounting to persist model weights.

---

## 📂 File Structure

```
AXIS_AI/
├── colab_launcher.ipynb   # 6-cell Colab notebook — run top-to-bottom
├── server.py              # FastAPI + Socket.io + Ollama + ChromaDB backend
├── static/
│   ├── index.html         # Premium dark-mode Web UI
│   ├── index.css          # Glassmorphism styles & animations
│   └── index.js           # Socket.io client + markdown renderer
├── requirements.txt       # Python dependencies
├── .gitignore             # Excludes memory DBs, pycaches, logs
└── README.md              # This file
```

---

## 🛠️ Tech Stack

| Component | Technology |
| :--- | :--- |
| **LLM** | Ollama (llama3, mistral, gemma) |
| **Memory** | ChromaDB persistent vector DB |
| **Backend** | FastAPI + Uvicorn |
| **Realtime** | Socket.io (python-socketio) |
| **Tunnel** | pyngrok → free public HTTPS |
| **Frontend** | Vanilla HTML/CSS/JS |
| **Runtime** | Google Colab (free T4 GPU) |

---

## 🔧 Local Development (non-Colab)

1. Install [Ollama](https://ollama.com/) locally and run: `ollama pull llama3:8b`
2. Install dependencies: `pip install -r requirements.txt`
3. Start the server: `uvicorn server:socket_app --reload --port 8000`
4. Open `http://localhost:8000/ui` in your browser.
