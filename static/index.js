/* ─────────────────────────────────────────────────
   A.X.I.S Frontend — Socket.io Chat Client
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

// ── SOCKET.IO CONNECTION ────────────────────────
// In Colab, the server rewrites this URL with the ngrok public address.
// Locally, it connects to window.location (same origin).
const SOCKET_URL = window.AXIS_SERVER_URL || window.location.origin;
const socket = io(SOCKET_URL, { transports: ['websocket', 'polling'] });

// ── SOCKET EVENTS ────────────────────────────────
socket.on('connect', () => {
  setStatus('online', 'A.X.I.S online');
  fetchHealth();
});

socket.on('disconnect', () => {
  setStatus('error', 'Disconnected');
  topbarModel.textContent = 'Offline';
});

socket.on('connect_error', () => {
  setStatus('error', 'Cannot reach server');
});

socket.on('status', (data) => {
  setStatus('online', data.msg);
});

// ── STREAMING TOKENS ─────────────────────────────
let streamBubble = null;

socket.on('stream_start', () => {
  removeTypingDots();
  streamBubble = createBubble('ai', '');
  chatFeed.appendChild(streamBubble.wrapper);
  scrollToBottom();
  lockInput(true);
});

socket.on('token', (data) => {
  if (streamBubble) {
    streamBubble.bubble.textContent += data.text;
    scrollToBottom();
  }
});

socket.on('stream_end', () => {
  // Render markdown code blocks
  if (streamBubble) {
    const raw = streamBubble.bubble.textContent;
    streamBubble.bubble.innerHTML = renderMarkdown(raw);
  }
  streamBubble = null;
  lockInput(false);
  userInput.focus();
  scrollToBottom();
});

// ── SEND MESSAGE ─────────────────────────────────
function sendMessage() {
  const text = userInput.value.trim();
  if (!text || sendBtn.disabled) return;

  // Remove intro card on first message
  const introCard = chatFeed.querySelector('.intro-card');
  if (introCard) introCard.remove();

  // Render user bubble
  const { wrapper } = createBubble('user', text);
  chatFeed.appendChild(wrapper);
  scrollToBottom();

  // Show typing indicator
  showTypingDots();

  // Send to server
  socket.emit('chat', { message: text });

  // Clear input
  userInput.value = '';
  userInput.style.height = 'auto';
  lockInput(true);
}

// ── CLEAR MEMORY ─────────────────────────────────
clearBtn.addEventListener('click', () => {
  socket.emit('clear_memory', {});
  memoryPanel.innerHTML = '<p class="memory-empty">Memory cleared.</p>';
});

// ── KEYBOARD SHORTCUTS ───────────────────────────
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);

// Auto-resize textarea
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
});

// Sidebar toggle
sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('open');
});

// ── HELPERS ───────────────────────────────────────

function createBubble(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = role === 'user' ? 'You' : 'A.X.I.S';

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
  label.textContent = 'A.X.I.S';

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

// Basic markdown: bold, code, pre blocks
function renderMarkdown(text) {
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Code blocks
    .replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${code.trim()}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold & italic
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Line breaks
    .replace(/\n/g, '<br/>');
  return html;
}

// ── HEALTH CHECK → Update model label ────────────
async function fetchHealth() {
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    topbarModel.textContent = `${d.model} · ${d.memory_entries} memories`;
  } catch {
    topbarModel.textContent = 'API unreachable';
  }
}
