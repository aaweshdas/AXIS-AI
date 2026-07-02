/* ─────────────────────────────────────────────────
   A.X.I.S Client — Realtime OS Controller & Voice AI
   ───────────────────────────────────────────────── */

// ── DOM REFERENCES ──────────────────────────────
const chatFeed      = document.getElementById('chatFeed');
const userInput     = document.getElementById('userInput');
const sendBtn       = document.getElementById('sendBtn');
const clearBtn      = document.getElementById('clearBtn');
const statusDot     = document.getElementById('statusDot');
const statusText    = document.getElementById('statusText');
const memoryPanel   = document.getElementById('memoryPanel');
const topbarModel   = document.getElementById('topbarModel');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar       = document.getElementById('sidebar');

// Voice DOM
const micBtn          = document.getElementById('micBtn');
const voiceSynthBtn   = document.getElementById('voiceSynthBtn');
const speakerOnIcon   = document.getElementById('speakerOnIcon');
const speakerOffIcon  = document.getElementById('speakerOffIcon');

// Metrics DOM
const cpuVal  = document.getElementById('cpuVal');
const cpuBar  = document.getElementById('cpuBar');
const ramVal  = document.getElementById('ramVal');
const ramBar  = document.getElementById('ramBar');
const gpuVal  = document.getElementById('gpuVal');

// ── APP STATE ────────────────────────────────────
let isVoiceOutput = false;
let isDictating   = false;
let recognition   = null;
let currentAgentText = ""; // Accumulator for Speech Synthesis

// ── SOCKET.IO CONNECTION ────────────────────────
// In Colab, the server rewrites this URL with the ngrok/cloudflare public address.
// Locally, it connects to window.location (same origin).
const SOCKET_URL = window.AXIS_SERVER_URL || window.location.origin;
const socket = io(SOCKET_URL, { transports: ['polling'] });

// ── CONNECTION HANDLERS ─────────────────────────
socket.on('connect', () => {
  setStatus('online', 'A.X.I.S online');
  fetchHealth();
  startMetricsPolling();
});

socket.on('disconnect', () => {
  setStatus('error', 'Disconnected from Core');
  topbarModel.textContent = 'Core offline';
});

socket.on('connect_error', () => {
  setStatus('error', 'Core unreachable');
});

socket.on('status', (data) => {
  setStatus('online', data.msg);
});

// ── CHAT ENGINE & STREAMING ─────────────────────
let streamBubble = null;

socket.on('stream_start', () => {
  removeTypingDots();
  currentAgentText = "";
  streamBubble = createBubble('ai', '');
  chatFeed.appendChild(streamBubble.wrapper);
  scrollToBottom();
  lockInput(true);
});

socket.on('token', (data) => {
  if (streamBubble) {
    streamBubble.bubble.textContent += data.text;
    currentAgentText += data.text;
    scrollToBottom();
  }
});

socket.on('stream_end', () => {
  if (streamBubble) {
    const raw = streamBubble.bubble.textContent;
    streamBubble.bubble.innerHTML = renderMarkdown(raw);
    
    // Speak out agent's response if voice mode enabled
    if (isVoiceOutput && currentAgentText.trim()) {
      speakResponse(currentAgentText);
    }
  }
  streamBubble = null;
  lockInput(false);
  userInput.focus();
  scrollToBottom();
  fetchHealth(); // refresh stats/memory counts
});

// ── AGENT TOOL EXECUTION CHANNELS ───────────────
let activeToolCard = null;

socket.on('tool_start', () => {
  // Agent is preparing/writing a tool block
  showTypingDots();
});

socket.on('tool_executing', (data) => {
  removeTypingDots();
  
  // Create tool execution visual card
  activeToolCard = document.createElement('div');
  activeToolCard.className = 'tool-exec-card';
  
  const title = document.createElement('div');
  title.className = 'tool-title';
  title.innerHTML = `<span class="tool-status"></span> Active Tool: ${data.tool}`;
  
  const codeBlock = document.createElement('pre');
  codeBlock.className = 'tool-code';
  
  // Format code based on tool type
  if (data.tool === 'python_execute') {
    codeBlock.textContent = data.args.code || "";
  } else if (data.tool === 'web_search') {
    codeBlock.textContent = `Search Query: "${data.args.query || ""}"`;
  } else if (data.tool === 'web_scrape') {
    codeBlock.textContent = `Scrape URL: ${data.args.url || ""}`;
  }
  
  activeToolCard.appendChild(title);
  activeToolCard.appendChild(codeBlock);
  chatFeed.appendChild(activeToolCard);
  scrollToBottom();
});

socket.on('tool_result', (data) => {
  if (activeToolCard) {
    // Add result output
    const outputBlock = document.createElement('pre');
    outputBlock.className = 'tool-output';
    outputBlock.textContent = data.result;
    activeToolCard.appendChild(outputBlock);
    
    // Draw plots/images if returned by code interpreter
    if (data.images && data.images.length > 0) {
      data.images.forEach(imgUrl => {
        const img = document.createElement('img');
        img.className = 'tool-image';
        img.src = imgUrl;
        img.alt = 'Python Plot Output';
        activeToolCard.appendChild(img);
      });
    }
    
    // Add memory context indicator into Sidebar Memory Panel
    addMemoryChip(data.tool, data.result);
  }
  activeToolCard = null;
  showTypingDots(); // continue waiting for next step
});

// ── SEND ENGINE ──────────────────────────────────
function sendMessage() {
  const text = userInput.value.trim();
  if (!text || sendBtn.disabled) return;

  // Stop current dictation / reading
  stopSpeaking();

  const introCard = chatFeed.querySelector('.intro-card');
  if (introCard) introCard.remove();

  // User bubble
  const { wrapper } = createBubble('user', text);
  chatFeed.appendChild(wrapper);
  scrollToBottom();

  showTypingDots();
  socket.emit('chat', { message: text });

  userInput.value = '';
  userInput.style.height = 'auto';
  lockInput(true);
}

// ── MEMORY LOGGING ──────────────────────────────
function addMemoryChip(tool, text) {
  // Wipe empty label
  const empty = memoryPanel.querySelector('.memory-empty');
  if (empty) empty.remove();
  
  const chip = document.createElement('div');
  chip.className = 'memory-chip';
  const cleanSnippet = text.length > 100 ? text.substring(0, 100) + '…' : text;
  chip.innerHTML = `<strong>${tool}</strong>: ${cleanSnippet}`;
  memoryPanel.prepend(chip);
  
  // Cap sidebar display list to 8 entries
  if (memoryPanel.children.length > 8) {
    memoryPanel.lastChild.remove();
  }
}

// ── SPEECH RECOGNITION (DICTATION) ─────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isDictating = true;
    micBtn.classList.add('active');
  };

  recognition.onend = () => {
    isDictating = false;
    micBtn.classList.remove('active');
  };

  recognition.onerror = () => {
    isDictating = false;
    micBtn.classList.remove('active');
  };

  recognition.onresult = (event) => {
    const speechResult = event.results[0][0].transcript;
    userInput.value = speechResult;
    userInput.style.height = userInput.scrollHeight + 'px';
  };
} else {
  micBtn.style.display = 'none'; // Speech dictation unsupported
}

micBtn.addEventListener('click', () => {
  if (isDictating) {
    recognition.stop();
  } else {
    userInput.value = "";
    recognition.start();
  }
});

// ── SPEECH SYNTHESIS (OUTPUT READER) ───────────────
voiceSynthBtn.addEventListener('click', () => {
  isVoiceOutput = !isVoiceOutput;
  if (isVoiceOutput) {
    voiceSynthBtn.classList.add('active');
    speakerOnIcon.classList.remove('hidden');
    speakerOffIcon.classList.add('hidden');
  } else {
    voiceSynthBtn.classList.remove('active');
    speakerOnIcon.classList.add('hidden');
    speakerOffIcon.classList.remove('hidden');
    stopSpeaking();
  }
});

function speakResponse(text) {
  if (!window.speechSynthesis) return;
  // Clean markdown tags for clear speech output
  const spokenText = text.replace(/[*#`_\-]/g, '').trim();
  const utterance = new SpeechSynthesisUtterance(spokenText);
  
  // Try to pick a premium natural sounding voice
  const voices = window.speechSynthesis.getVoices();
  const premiumVoice = voices.find(v => v.name.includes('Google') || v.name.includes('Natural'));
  if (premiumVoice) utterance.voice = premiumVoice;
  
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
}

// ── SUGGESTIONS & UI BINDINGS ─────────────────────
window.fillInput = function(promptText) {
  userInput.value = promptText;
  userInput.focus();
  userInput.style.height = userInput.scrollHeight + 'px';
};

userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);

clearBtn.addEventListener('click', () => {
  socket.emit('clear_memory', {});
  memoryPanel.innerHTML = '<p class="memory-empty">Memory cleared.</p>';
});

sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('open');
});

// Auto-expand textarea
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 180) + 'px';
});

// ── SIDEBAR SYSTEM MONITOR (POLLING) ────────────────
let metricsInterval = null;

function startMetricsPolling() {
  if (metricsInterval) clearInterval(metricsInterval);
  updateMetrics();
  metricsInterval = setInterval(updateMetrics, 4000);
}

async function updateMetrics() {
  try {
    const r = await fetch('/api/system_stats');
    const d = await r.json();
    
    // CPU
    cpuVal.textContent = `${d.cpu}%`;
    cpuBar.style.width = `${d.cpu}%`;
    
    // RAM
    ramVal.textContent = `${d.ram_used} / ${d.ram_total} GB`;
    ramBar.style.width = `${d.ram_percent}%`;
    
    // GPU
    if (d.gpu && d.gpu !== 'N/A') {
      // Show GPU Name
      gpuVal.textContent = d.gpu.split(',')[0];
    } else {
      gpuVal.textContent = 'None (CPU Execution)';
    }
  } catch (err) {
    console.log("Metrics fetch failed: " + err);
  }
}

// ── COMPONENT BUILDERS ────────────────────────────
function createBubble(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = role === 'user' ? 'You' : 'A.X.I.S Agent';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  if (text) bubble.textContent = text;

  wrapper.appendChild(label);
  wrapper.appendChild(bubble);
  return { wrapper, bubble };
}

function showTypingDots() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message ai';
  wrapper.id = 'typingDots';

  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = 'A.X.I.S Agent';

  const dots = document.createElement('div');
  dots.className = 'typing-dots';
  dots.innerHTML = '<span></span><span></span><span></span>';

  wrapper.appendChild(label);
  wrapper.appendChild(dots);
  chatFeed.appendChild(wrapper);
  scrollToBottom();
}

function removeTypingDots() {
  const el = document.getElementById('typingDots');
  if (el) el.remove();
}

function lockInput(locked) {
  sendBtn.disabled   = locked;
  userInput.disabled = locked;
}

function setStatus(state, msg) {
  statusDot.className = `status-dot ${state}`;
  statusText.textContent = msg;
}

function scrollToBottom() {
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

// Basic markdown helper
function renderMarkdown(text) {
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Multi line code
    .replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${code.trim()}</code></pre>`)
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Lines
    .replace(/\n/g, '<br/>');
  return html;
}

async function fetchHealth() {
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    topbarModel.textContent = `${d.model} (${d.memory_entries} memories stored)`;
  } catch {
    topbarModel.textContent = 'Connecting…';
  }
}
