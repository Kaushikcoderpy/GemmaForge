/* ---- GemmaForge app.js — shared across all 3 pages ---- */
const API = 'http://127.0.0.1:8000';

// ── Theme ──────────────────────────────────────────────────────
const themeToggle = document.getElementById('themeToggle');
if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const html = document.documentElement;
    const dark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', dark ? 'light' : 'dark');
    themeToggle.textContent = dark ? '☀️' : '🌙';
  });
}

var customPersona = "";

function updateCharCount(id, displayId, max) {
  const el = document.getElementById(id);
  const display = document.getElementById(displayId);
  if (!el || !display) return;
  const len = el.value.length;
  display.textContent = len.toLocaleString();
  if (len >= max) {
    display.style.color = '#ef4444';
  } else if (len > max * 0.7) {
    display.style.color = '#f59e0b';
  } else {
    display.style.color = (displayId === 'topicCharCount' || displayId === 'personaCharCount' || displayId === 'editCharCount') ? 'var(--text3)' : '';
  }
}

// ── Toast ──────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  if (!t) return;
  const colors = { info: '#7c3aed', success: '#10b981', error: '#ef4444' };
  t.textContent = msg;
  t.style.borderColor = colors[type] || colors.info;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

// ── Count-up (landing page stats) ─────────────────────────────
const statsRow = document.querySelector('.stats-row');
if (statsRow) {
  const observer = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting) {
      document.querySelectorAll('.stat-num').forEach(el => {
        let current = 0;
        const target = parseInt(el.dataset.target);
        const step = Math.ceil(target / 40);
        const iv = setInterval(() => {
          current = Math.min(current + step, target);
          el.textContent = current;
          if (current >= target) clearInterval(iv);
        }, 30);
      });
      observer.disconnect();
    }
  });
  observer.observe(statsRow);
}

// ═══════════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════════
function openSettings() {
  document.getElementById('geminiApiKey').value = localStorage.getItem('GEMINI_API_KEY') || '';
  document.getElementById('settingsOverlay').classList.add('open');
}

function closeSettings(e) {
  if (!e || e.target.id === 'settingsOverlay' || e.type === 'click') {
    document.getElementById('settingsOverlay').classList.remove('open');
  }
}

function saveSettings() {
  const key = document.getElementById('geminiApiKey').value.trim();
  if (key) {
    localStorage.setItem('GEMINI_API_KEY', key);
    showToast('API Key saved to local storage.', 'success');
    closeSettings();
  } else {
    showToast('Please enter a valid key.', 'error');
  }
}

function clearSettings() {
  localStorage.removeItem('GEMINI_API_KEY');
  document.getElementById('geminiApiKey').value = '';
  showToast('API Key deleted from local storage.', 'info');
}

// ═══════════════════════════════════════════════
// TOOLS PAGE logic
// ═══════════════════════════════════════════════
// helpers for files and images
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const base64 = reader.result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = error => reject(error);
  });
}

function previewImage(input, previewId) {
  const preview = document.getElementById(previewId);
  const container = document.getElementById(previewId + '-container');
  const btnId = previewId === 'alt-preview' ? 'btn-upload-alt' : 'btn-upload-img-article';
  const btn = document.getElementById(btnId);
  const logEl = document.getElementById(previewId + '-log');
  
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = function(e) {
      if (preview) preview.src = e.target.result;
      if (container) container.style.display = 'block';
      if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
        btn.textContent = '📁 Uploaded';
      }
      if (logEl) {
        logEl.style.display = 'block';
        logEl.textContent = `🟢 Image Uploaded: ${input.files[0].name}`;
      }
    };
    reader.readAsDataURL(input.files[0]);
  }
}

function clearImage(previewId) {
  const preview = document.getElementById(previewId);
  const container = document.getElementById(previewId + '-container');
  const btnId = previewId === 'alt-preview' ? 'btn-upload-alt' : 'btn-upload-img-article';
  const btn = document.getElementById(btnId);
  const logEl = document.getElementById(previewId + '-log');
  const inputId = previewId === 'alt-preview' ? 'input-alt-file' : 'input-img-article-file';
  const input = document.getElementById(inputId);

  if (input) input.value = '';
  if (preview) preview.src = '';
  if (container) container.style.display = 'none';
  if (btn) {
    btn.disabled = false;
    btn.style.opacity = '';
    btn.style.cursor = '';
    btn.textContent = previewId === 'alt-preview' ? '📁 Upload Image' : '📁 Upload Sketch/Plan';
  }
  if (logEl) {
    logEl.style.display = 'none';
    logEl.textContent = '';
  }
}

let selectedFormatImg = 'html';
function setFormatImg(fmt) {
  selectedFormatImg = fmt;
  const display = document.getElementById('format-display-img');
  if (display) display.textContent = fmt;
  document.getElementById('fmt-html-img')?.classList.toggle('active', fmt === 'html');
  document.getElementById('fmt-md-img')?.classList.toggle('active', fmt === 'markdown');
}

let selectedFormat = window.selectedFormat || 'html';
let lastResult = null;
let lastFormat = 'markdown';
let lastTool = null;

const TOOL_META = {
  'compress-fluff': { title: 'Compressed Signal', model: 'Gemma 2B', icon: '🗜️' },
  'analyse-trends': { title: 'Trend Analysis', model: 'Gemma 4B', icon: '📈' },
  'seo-gap-report': { title: 'SEO Gap Report', model: 'Gemma 26B', icon: '🔬' },
  'plan-content': { title: 'Content Blueprint', model: 'Gemma 26B', icon: '🗺️' },
  'write-content': { title: 'Generated Content', model: 'Gemma 31B', icon: '✍️' },
  'alt-text': { title: 'Image Alt Text', model: 'Gemma 26B', icon: '🖼️' },
  'image-to-article': { title: 'Image to Article', model: 'Gemma 26B/31B', icon: '🎨' },
};

const CHAR_LIMITS = {
  'input-compress': ['count-compress', 20000],
  'input-trends': ['count-trends', 15000],
  'input-seo-my': ['count-seo-my', 20000],
  'input-seo-comp': ['count-seo-comp', 20000],
  'input-plan-gap': ['count-plan-gap', 15000],
  'input-plan-trends': ['count-plan-trends', 5000],
  'input-plan-style': ['count-plan-style', 1000],
  'input-write': ['count-write', 20000],
};

const HISTORY_KEY = 'gemmaforge.atomicHistory.v1';
const DRAFT_KEY = 'gemmaforge.atomicDrafts.v1';

function setFormat(fmt) {
  selectedFormat = fmt;
  const display = document.getElementById('format-display');
  if (display) display.textContent = fmt;
  document.getElementById('fmt-html')?.classList.toggle('active', fmt === 'html');
  document.getElementById('fmt-md')?.classList.toggle('active', fmt === 'markdown');
  saveToolDrafts();
}

function getVal(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function setBtnLoading(id, loading) {
  const btn = document.getElementById(id);
  if (!btn) return;
  btn.disabled = loading;
  btn.textContent = loading ? '⏳ Running...' : 'Run ▶';
}

function toolInputSummary(tool) {
  const sources = {
    'compress-fluff': [['Source', 'input-compress']],
    'analyse-trends': [['Trends JSON', 'input-trends']],
    'seo-gap-report': [['My text', 'input-seo-my'], ['Competitors', 'input-seo-comp']],
    'plan-content': [['Gap', 'input-plan-gap'], ['Trends', 'input-plan-trends'], ['Style', 'input-plan-style']],
    'write-content': [['Blueprint', 'input-write'], ['Format', 'format-display']],
    'alt-text': [['Image', 'input-alt-file']],
    'image-to-article': [['Image', 'input-img-article-file'], ['Prompt', 'input-img-article-prompt']],
  }[tool] || [];

  return sources
    .map(([label, id]) => {
      if (id.endsWith('-file')) {
        const el = document.getElementById(id);
        return `${label}: ${el && el.files && el.files[0] ? el.files[0].name : 'None'}`;
      }
      const value = id === 'format-display' ? (document.getElementById(id)?.textContent || selectedFormat) : getVal(id);
      if (!value) return '';
      const compact = value.replace(/\s+/g, ' ').slice(0, 180);
      return `${label}: ${compact}${value.length > 180 ? '...' : ''}`;
    })
    .filter(Boolean)
    .join(' | ');
}

function toolDraftIds() {
  return [
    'input-compress',
    'input-trends',
    'input-seo-my',
    'input-seo-comp',
    'input-plan-gap',
    'input-plan-trends',
    'input-plan-style',
    'input-write',
  ];
}

function loadToolDrafts() {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function saveToolDrafts() {
  try {
    const payload = { selectedFormat };
    toolDraftIds().forEach(id => {
      const el = document.getElementById(id);
      if (el) payload[id] = el.value;
    });
    localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
  } catch {
    // Draft persistence is a convenience; tool execution should never depend on it.
  }
}

function initToolDraftPersistence() {
  const ids = toolDraftIds();
  if (!ids.some(id => document.getElementById(id))) return;
  const drafts = loadToolDrafts();
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (drafts[id]) el.value = drafts[id];
    
    // Initial count
    if (CHAR_LIMITS[id]) {
      updateCharCount(id, CHAR_LIMITS[id][0], CHAR_LIMITS[id][1]);
    }

    el.addEventListener('input', () => {
      saveToolDrafts();
      if (CHAR_LIMITS[id]) {
        updateCharCount(id, CHAR_LIMITS[id][0], CHAR_LIMITS[id][1]);
      }
    });
  });
  if (drafts.selectedFormat) setFormat(drafts.selectedFormat);
}

async function callTool(tool) {
  let inputSummary = toolInputSummary(tool);
  const btnId = { 
    'compress-fluff': 'btn-compress', 
    'analyse-trends': 'btn-trends', 
    'seo-gap-report': 'btn-seo', 
    'plan-content': 'btn-plan', 
    'write-content': 'btn-write',
    'alt-text': 'btn-alt',
    'image-to-article': 'btn-img-article'
  }[tool];
  let resultText = '';
  let format = 'markdown';

  try {
    if (!window.aiEngine) {
      throw new Error("AI Engine not loaded.");
    }
    
    setBtnLoading(btnId, true);

    if (tool === 'compress-fluff') {
      const v = getVal('input-compress'); if (!v) throw new Error('Paste text first.');
      resultText = await window.aiEngine.compressCompetitorFluff(v);
    } else if (tool === 'analyse-trends') {
      const v = getVal('input-trends'); if (!v) throw new Error('Paste JSON first.');
      resultText = await window.aiEngine.analyseTrends(v);
    } else if (tool === 'seo-gap-report') {
      const v1 = getVal('input-seo-my'), v2 = getVal('input-seo-comp');
      if (!v1) throw new Error('Provide your text first.');
      resultText = await window.aiEngine.generateSeoGapReport(v1, v2);
    } else if (tool === 'plan-content') {
      const v1 = getVal('input-plan-gap'), v2 = getVal('input-plan-trends'), v3 = getVal('input-plan-style');
      if (!v1) throw new Error('Provide gap report first.');
      resultText = await window.aiEngine.planTheContent(v1, v2, v3 || 'technical, code-heavy, no fluff');
    } else if (tool === 'write-content') {
      const v = getVal('input-write'); if (!v) throw new Error('Provide blueprint first.');
      resultText = await window.aiEngine.writeTheContent(v, selectedFormat);
      format = selectedFormat;
    } else if (tool === 'alt-text') {
      const fileInput = document.getElementById('input-alt-file');
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        throw new Error('Please select an image first.');
      }
      const file = fileInput.files[0];
      const base64 = await fileToBase64(file);
      const mimeType = file.type || "image/jpeg";
      resultText = await window.aiEngine.generateAltText(base64, mimeType);
      format = 'markdown';
    } else if (tool === 'image-to-article') {
      const fileInput = document.getElementById('input-img-article-file');
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        throw new Error('Please select an image first.');
      }
      const file = fileInput.files[0];
      const base64 = await fileToBase64(file);
      const mimeType = file.type || "image/jpeg";
      const extraPrompt = getVal('input-img-article-prompt');
      resultText = await window.aiEngine.imageToArticle(base64, mimeType, extraPrompt, selectedFormatImg);
      format = selectedFormatImg;
    }

    setBtnLoading(btnId, false);
    lastResult = resultText;
    lastFormat = format;
    lastTool = tool;
    saveHistoryItem(tool, resultText, format, inputSummary);
    openPreview(tool, resultText, format);
    showToast('✅ Done! Preview is open.', 'success');

  } catch (err) {
    setBtnLoading(btnId, false);
    if (err.message.includes("GEMINI_API_KEY")) {
       openSettings();
    }
    showToast(err.message, 'error');
  }
}

// ── Result Previewer ──────────────────────────────────────────
function previewDocument(result, format) {
  const renderedBody = format === 'html'
    ? result
    : (typeof marked !== 'undefined' ? marked.parse(result) : `<pre>${escapeHtml(result)}</pre>`);
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<base target="_blank">
<style>
  body { margin: 0; padding: 24px; color: #e2e8f0; background: #0a0a0f; font: 15px/1.75 Inter, system-ui, sans-serif; }
  h1, h2, h3 { color: #a855f7; line-height: 1.25; margin: 1.2em 0 .45em; }
  p { margin: 0 0 1em; }
  code { font-family: "JetBrains Mono", Consolas, monospace; background: #111118; padding: .12rem .32rem; border-radius: 4px; }
  pre { background: #111118; border: 1px solid rgba(139, 92, 246, .25); border-radius: 10px; padding: 16px; overflow: auto; }
  pre code { background: transparent; padding: 0; }
  a { color: #06b6d4; }
</style>
</head>
<body>${renderedBody}</body>
</html>`;
}

function openPreview(tool, result, format) {
  const overlay = document.getElementById('previewOverlay');
  if (!overlay) return;
  const meta = TOOL_META[tool] || { title: 'Result', model: 'Gemma', icon: '✨' };
  document.getElementById('previewTitle').textContent = `${meta.icon} ${meta.title} — ${meta.model}`;
  document.getElementById('previewChars').textContent = `${result.length.toLocaleString()} chars`;

  // Raw pane
  document.getElementById('pane-raw').textContent = result;

  const rendered = document.getElementById('pane-rendered');
  rendered.textContent = '';
  const frame = document.createElement('iframe');
  frame.className = 'preview-frame';
  frame.setAttribute('sandbox', '');
  frame.srcdoc = previewDocument(result, format);
  rendered.appendChild(frame);

  overlay.classList.add('open');
  switchTab('rendered');
}

function closePreview(event) {
  if (!event || event.target.id === 'previewOverlay') {
    document.getElementById('previewOverlay')?.classList.remove('open');
  }
}

function switchTab(tab) {
  const rendered = document.getElementById('pane-rendered');
  const raw = document.getElementById('pane-raw');
  const tabR = document.getElementById('tab-rendered');
  const tabRaw = document.getElementById('tab-raw');
  if (!rendered) return;
  if (tab === 'rendered') {
    rendered.classList.remove('hidden'); raw.classList.add('hidden');
    tabR.classList.add('active'); tabRaw.classList.remove('active');
  } else {
    raw.classList.remove('hidden'); rendered.classList.add('hidden');
    tabRaw.classList.add('active'); tabR.classList.remove('active');
  }
}

function copyResult() {
  if (!lastResult) return;
  navigator.clipboard.writeText(lastResult).then(() => showToast('Copied to clipboard!', 'success'));
}

// ── Persistent Atomic Tool History ─────────────────────────────
function loadHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function storeHistory(items) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 50)));
    renderHistory();
  } catch (err) {
    showToast('History could not be saved in this browser.', 'error');
  }
}

function saveHistoryItem(tool, result, format, inputSummary) {
  try {
    if (!window.localStorage) return;
  } catch {
    return;
  }
  const meta = TOOL_META[tool] || { title: 'Result', model: 'Gemma', icon: '✨' };
  const item = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    tool,
    title: meta.title,
    model: meta.model,
    icon: meta.icon,
    format,
    chars: result.length,
    inputSummary,
    result,
    createdAt: new Date().toISOString(),
  };
  storeHistory([item, ...loadHistory()]);
}

function renderHistory() {
  const list = document.getElementById('historyList');
  const count = document.getElementById('historyCount');
  const items = loadHistory();
  if (count) count.textContent = items.length;
  if (!list) return;

  list.textContent = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'history-empty';
    empty.textContent = 'No generated outputs yet.';
    list.appendChild(empty);
    return;
  }

  items.forEach(item => {
    const row = document.createElement('article');
    row.className = 'history-item';

    const top = document.createElement('div');
    top.className = 'history-item-top';
    const title = document.createElement('div');
    title.className = 'history-item-title';
    title.textContent = `${item.icon || '✨'} ${item.title || 'Result'}`;
    const meta = document.createElement('div');
    meta.className = 'history-item-meta';
    meta.textContent = `${item.model || 'Gemma'} · ${item.format || 'markdown'} · ${(item.chars || 0).toLocaleString()} chars · ${new Date(item.createdAt).toLocaleString()}`;
    top.append(title, meta);

    const summary = document.createElement('p');
    summary.className = 'history-summary';
    summary.textContent = item.inputSummary || 'No input summary captured.';

    const actions = document.createElement('div');
    actions.className = 'history-actions';
    const openBtn = document.createElement('button');
    openBtn.className = 'copy-btn';
    openBtn.textContent = 'Open';
    openBtn.onclick = () => {
      lastResult = item.result;
      lastFormat = item.format;
      lastTool = item.tool;
      closeHistory();
      openPreview(item.tool, item.result, item.format);
    };
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = 'Copy';
    copyBtn.onclick = () => navigator.clipboard.writeText(item.result).then(() => showToast('Copied history item.', 'success'));
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'copy-btn danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.onclick = () => deleteHistoryItem(item.id);
    actions.append(openBtn, copyBtn, deleteBtn);

    row.append(top, summary, actions);
    list.appendChild(row);
  });
}

function openHistory() {
  renderHistory();
  document.getElementById('historyOverlay')?.classList.add('open');
}

function closeHistory(event) {
  if (!event || event.target.id === 'historyOverlay') {
    document.getElementById('historyOverlay')?.classList.remove('open');
  }
}

function deleteHistoryItem(id) {
  storeHistory(loadHistory().filter(item => item.id !== id));
  showToast('History item deleted.', 'info');
}

function clearHistory() {
  if (!loadHistory().length) return;
  if (!confirm('Clear all generated output history?')) return;
  storeHistory([]);
  showToast('History cleared.', 'info');
}

renderHistory();
initToolDraftPersistence();

// ═══════════════════════════════════════════════
// ENGINE PAGE logic
// ═══════════════════════════════════════════════
let currentMode = 'full';
let sseSource = null;
let engineRunning = false;
let startTime = null;
let logCount = 0;

function selectMode(mode) {
  currentMode = mode;
  document.getElementById('mode-full')?.classList.toggle('active', mode === 'full');
  document.getElementById('mode-content')?.classList.toggle('active', mode === 'content');
  const modeChip = document.getElementById('m-mode');
  if (modeChip) modeChip.innerHTML = `Mode: <strong>${mode === 'full' ? 'Full Pipeline' : 'Content Only'}</strong>`;
}

function connectSSE() {
  if (sseSource) sseSource.close();
  sseSource = new EventSource(`${API}/logs/stream`);
  const dot = document.getElementById('sseIndicator');

  sseSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    appendLog(data.msg, data.level);
    if (data.msg.includes('Distribution Complete') || data.msg.includes('pipeline complete') || data.msg.includes('No posts were made')) {
      setStatus('done', '✅ Complete');
      showSuccess(); engineRunning = false;
      document.getElementById('fireBtn').disabled = false;
      fetchLatestReport();
    }
    if (data.msg.includes('ERROR IN MAIN') || data.msg.includes('All retries failed')) {
      setStatus('error', '❌ Failed'); engineRunning = false;
      document.getElementById('fireBtn').disabled = false;
    }
  };
  sseSource.onerror = () => {
    if (dot) dot.style.background = '#ef4444';
    setTimeout(connectSSE, 3000);
  };
  sseSource.onopen = () => { if (dot) dot.style.background = '#10b981'; };
}

function appendLog(msg, level = 'INFO') {
  const body = document.getElementById('logBody');
  if (!body) return;
  logCount++;
  const countEl = document.getElementById('logCount');
  if (countEl) countEl.textContent = `${logCount} lines`;
  const line = document.createElement('span');
  let cls = 'log-line log-info';
  if (level === 'WARNING') cls = 'log-line log-WARNING';
  else if (level === 'ERROR') cls = 'log-line log-ERROR';
  else if (msg.includes('✅') || msg.includes('success') || msg.includes('Success')) cls = 'log-line log-SUCCESS';
  line.className = cls;
  line.textContent = msg;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
  // Update elapsed
  if (startTime) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const timeEl = document.getElementById('m-time');
    if (timeEl) timeEl.innerHTML = `Elapsed: <strong>${elapsed}s</strong>`;
  }
}

function clearLogs() {
  const body = document.getElementById('logBody');
  if (body) body.innerHTML = '';
  logCount = 0;
  const countEl = document.getElementById('logCount');
  if (countEl) countEl.textContent = '0 lines';
}

function setStatus(state, text) {
  const el = document.getElementById('engineStatus');
  if (!el) return;
  el.className = `engine-status ${state}`;
  el.textContent = text;
}

function showSuccess() {
  const s = document.getElementById('m-success');
  if (s) s.style.display = 'inline-flex';
  showToast('🎉 Engine run complete!', 'success');
}

async function fireEngine() {
  if (engineRunning) return;
  engineRunning = true; startTime = Date.now();
  document.getElementById('fireBtn').disabled = true;
  const s = document.getElementById('m-success');
  if (s) s.style.display = 'none';
  clearLogs();
  setStatus('running', '⏳ Running...');
  appendLog('🔥 Firing GemmaForge Engine...', 'INFO');

  const topicInput = document.getElementById('engineTopicInput');
  const topic = topicInput ? encodeURIComponent(topicInput.value.trim()) : '';

  if (!topic) {
    appendLog('⚠️ No topic provided. The engine will run with default test payload.', 'WARNING');
  }

  try {
    let url;
    const personaParam = `&persona=${encodeURIComponent(customPersona)}`;
    if (currentMode === 'full') {
      const qc  = document.getElementById('flag-qc')?.checked ?? true;
      const se  = document.getElementById('flag-se')?.checked ?? true;
      const syn = document.getElementById('flag-syn')?.checked ?? true;
      url = `${API}/engine/run?run_quality_checks=${qc}&ping_search_engines=${se}&syndicate_content=${syn}&topic=${topic}${personaParam}`;
    } else {
      url = `${API}/engine/content-only?topic=${topic}${personaParam}`;
    }
    const resp = await fetch(url, { method: 'POST' });
    const data = await resp.json();
    appendLog(`📡 Response: ${JSON.stringify(data)}`, 'INFO');
    showToast('Engine started — watch logs below.', 'info');
  } catch (err) {
    appendLog(`❌ Server unreachable: ${err.message}`, 'ERROR');
    setStatus('error', '❌ Server Unreachable');
    document.getElementById('fireBtn').disabled = false;
    engineRunning = false;
    showToast('Cannot reach server at ' + API, 'error');
  }
}

async function fetchLatestReport() {
  const section = document.getElementById('forgedContentSection');
  const display = document.getElementById('forgedDisplay');
  if (!section || !display) return;

  try {
    // Add cache buster to ensure we get the fresh file
    const resp = await fetch(`${API}/engine/latest-report?t=${Date.now()}`);
    const data = await resp.json();
    
    console.log('Forge: Fetched report data:', data);

    if (data.content && data.content.trim().length > 0) {
      // Render as Markdown using marked.js
      if (typeof marked !== 'undefined') {
        display.innerHTML = '<div class="markdown-body">' + marked.parse(data.content) + '</div>';
      } else {
        // Fallback if CDN fails
        display.innerHTML = '<pre style="white-space: pre-wrap; margin:0; font-family: inherit; color: var(--text);">' + data.content + '</pre>';
      }
      // Enable edit controls
      const editControls = document.getElementById('editControls');
      if (editControls) {
        editControls.style.opacity = '1';
        editControls.style.pointerEvents = 'auto';
      }
    } else {
      display.innerHTML = '<div style="color: #666; font-style: italic; text-align: center; margin-top: 100px;">No content forged yet. Fire the engine to begin...</div>';
      const editControls = document.getElementById('editControls');
      if (editControls) {
        editControls.style.opacity = '0.5';
        editControls.style.pointerEvents = 'none';
      }
    }
  } catch (err) {
    console.error('Forge: Failed to fetch report:', err);
    display.innerHTML = '<div style="color: var(--red); text-align: center; margin-top: 100px;">⚠️ Connection Error: Could not reach forge server.</div>';
  }
}

function copyForgedContent() {
  const display = document.getElementById('forgedDisplay');
  if (!display) return;
  const text = display.innerText;
  navigator.clipboard.writeText(text).then(() => {
    showToast('Markdown copied to clipboard!', 'success');
  }).catch(err => {
    showToast('Failed to copy text.', 'error');
  });
}

async function requestEdit() {
  const instruction = document.getElementById('editInstructionInput').value.trim();
  const model = document.getElementById('editModelSelect').value;
  const btn = document.getElementById('submitEditBtn');
  
  if (!instruction) {
    showToast('Please enter an edit instruction.', 'warning');
    return;
  }
  
  btn.disabled = true;
  btn.textContent = 'Editing...';
  appendLog(`🧠 Requesting edit using ${model}: "${instruction}"`, 'INFO');
  
  try {
    const resp = await fetch(`${API}/engine/edit-content`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction, model })
    });
    const data = await resp.json();
    
    if (data.status === 'success') {
      showToast('Edit complete!', 'success');
      appendLog('✅ Edit applied successfully.', 'SUCCESS');
      document.getElementById('editInstructionInput').value = '';
      const charCount = document.getElementById('editCharCount');
      if (charCount) charCount.textContent = '0';
      fetchLatestReport();
    } else {
      showToast(`Edit failed: ${data.error}`, 'error');
      appendLog(`❌ Edit failed: ${data.error}`, 'ERROR');
    }
  } catch (err) {
    showToast('Edit request failed.', 'error');
    appendLog(`❌ Edit request failed: ${err.message}`, 'ERROR');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Edit';
  }
}

// ── Persona Modal Logic ─────────────────────────────────────────

function openPersonaModal() {
    const modal = document.getElementById('personaModal');
    if (modal) modal.style.display = 'flex';
}

function closePersonaModal() {
    const modal = document.getElementById('personaModal');
    if (modal) modal.style.display = 'none';
}

function savePersona() {
    const input = document.getElementById('personaInput');
    if (input) {
        customPersona = input.value;
        showToast(`Persona saved! (${customPersona.length} chars)`, 'success');
    }
    closePersonaModal();
}

// ── Convenience Fill Test Inputs ──────────────────────────────
function fillTestInputs() {
  // Page 1: Atomic Tools
  const inputCompress = document.getElementById('input-compress');
  if (inputCompress) {
    inputCompress.value = "Hello everyone! Welcome back to my engineering channel. Before we begin, don't forget to hit the like button, subscribe, and follow me on Twitter and GitHub! In today's highly requested, deep-dive article, we are going to explore Next.js 15 and the newly introduced React Server Components (RSC) and Partial Pre-rendering (PPR).\n\n" +
      "Honestly, this is absolutely mind-blowing and represents a paradigm shift that will literally redefine how modern web applications are built.\n\n" +
      "When I first started building websites, we used to use PHP and everything was simple. Then we migrated to client-side single page applications (SPAs) with React, which was awesome but had huge bundle sizes and terrible SEO. Now, Next.js 15 bridges the gap by letting components render on the server!\n\n" +
      "To demonstrate this groundbreaking capability, let's write a standard server component. Here is the actual implementation detail:\n\n" +
      "// Next.js 15 Server Component Example\n" +
      "export default async function ProductCatalog({ categoryId }) {\n" +
      "  const res = await fetch('https://api.myplatform.io/v1/products?category=' + categoryId, {\n" +
      "    next: { revalidate: 3600, tags: ['products'] }\n" +
      "  });\n" +
      "  \n" +
      "  if (!res.ok) {\n" +
      "    throw new Error('Database connection failed to return products collection.');\n" +
      "  }\n" +
      "  \n" +
      "  const products = await res.json();\n" +
      "  \n" +
      "  return (\n" +
      "    <div className='product-grid'>\n" +
      "      {products.map(p => (\n" +
      "        <div key={p.uuid} className='product-card'>\n" +
      "          <h3>{p.title}</h3>\n" +
      "          <span className='price'>${p.price.toFixed(2)}</span>\n" +
      "        </div>\n" +
      "      ))}\n" +
      "    </div>\n" +
      "  );\n" +
      "}\n\n" +
      "Now, in traditional SSR, the user had to wait for the entire data fetch before receiving any HTML. Next.js 15 solves this with Partial Pre-rendering (PPR). PPR statically renders the shell of the page (like layout headers, sidebar grids, and search bar placeholders) using Suspense, while leaving dynamic holes that are streamed incrementally from the edge runtime.\n\n" +
      "To wrap up: this is literally the future! Be sure to subscribe to my newsletter to download the full cheat sheet!";
    updateCharCount('input-compress', 'count-compress', 20000);
  }

  const inputTrends = document.getElementById('input-trends');
  if (inputTrends) {
    inputTrends.value = JSON.stringify([
      {
        term: "React Server Components",
        category: "Software Development",
        global_interest_index: 88,
        quarterly_growth_percent: 142.5,
        top_regions: ["United States", "Germany", "India", "United Kingdom", "Canada"],
        related_queries: ["Next.js 15 PPR", "React Suspense data fetching", "RSC Server Actions", "rsc client boundary"],
        growth_velocity: "Exponential",
        market_adoption_phase: "Early Adopters"
      },
      {
        term: "Bun Runtime",
        category: "Javascript Runtimes",
        global_interest_index: 76,
        quarterly_growth_percent: 210.8,
        top_regions: ["United States", "Japan", "South Korea", "Brazil", "Germany"],
        related_queries: ["Bun vs Node.js throughput", "Bun Elysia performance", "Bun mock testing", "Bun package manager caching"],
        growth_velocity: "High Velocity",
        market_adoption_phase: "Innovators"
      },
      {
        term: "Drizzle ORM",
        category: "Database Engineering",
        global_interest_index: 68,
        quarterly_growth_percent: 115.4,
        top_regions: ["United States", "Ukraine", "United Kingdom", "France", "Australia"],
        related_queries: ["Drizzle SQL schema generation", "Drizzle vs Prisma benchmark", "Drizzle dynamic joins", "drizzle-kit push postgres"],
        growth_velocity: "Steady Growth",
        market_adoption_phase: "Early Majority"
      },
      {
        term: "Vector Databases",
        category: "Artificial Intelligence",
        global_interest_index: 94,
        quarterly_growth_percent: 340.2,
        top_regions: ["United States", "China", "Singapore", "United Kingdom", "Israel"],
        related_queries: ["Qdrant HNSW indexing", "Pinecone serverless scaling", "pgvector cosine similarity", "vector embedding semantic search"],
        growth_velocity: "Hyper-growth",
        market_adoption_phase: "Early Adopters"
      }
    ], null, 2);
    updateCharCount('input-trends', 'count-trends', 15000);
  }

  const inputSeoMy = document.getElementById('input-seo-my');
  if (inputSeoMy) {
    inputSeoMy.value = "We implemented an asynchronous parser in Python using the standard 'asyncio' library. The basic architecture uses a simple loop with asyncio.sleep to fetch from a single endpoint sequentially. It is clean, written in standard Python, and uses standard try-except blocks to catch general exceptions and print them to stdout. It runs fast on a local machine for single requests.";
    updateCharCount('input-seo-my', 'count-seo-my', 20000);
  }

  const inputSeoComp = document.getElementById('input-seo-comp');
  if (inputSeoComp) {
    inputSeoComp.value = "To scale an asynchronous data parsing pipeline in Python to handle millions of records daily, engineers must design beyond basic asyncio syntax.\n\n" +
      "First, connection pooling is critical. Using aiohttp.ClientSession with a custom configured aiohttp.TCPConnector (setting limit=100 and limit_per_host=20) prevents socket exhaustion (TIME_WAIT states) and cuts handshake latencies by reusing established TCP connections.\n\n" +
      "Second, the ingestion engine must be decoupled from the processing engine. Using a queue-based consumer pattern with asyncio.Queue(maxsize=500) ensures that slow database writes or downstream processing lags do not bottleneck the rapid HTTP data ingestion.\n\n" +
      "Third, resilient rate limit handling is mandatory. When scraping or accessing third-party APIs, the parser must intercept HTTP 429 (Too Many Requests) responses, parse the Retry-After header dynamically, and invoke an exponential backoff retry strategy with jitter to avoid thrashing the host.\n\n" +
      "Finally, memory management is key. Spawning thousands of un-awaited coroutines simultaneously leads to massive RAM spikes. Instead, utilize asyncio.Semaphore(value=50) to strictly cap the concurrency window of active network requests.";
    updateCharCount('input-seo-comp', 'count-seo-comp', 20000);
  }

  const inputPlanGap = document.getElementById('input-plan-gap');
  if (inputPlanGap) {
    inputPlanGap.value = "- Deficit 1: Totally missing TCP connection pooling via aiohttp TCPConnector to mitigate socket exhaustion.\n" +
      "- Deficit 2: Lack of dynamic rate limit interception (HTTP 429) and exponential backoff retry logic.\n" +
      "- Deficit 3: No producer-consumer decoupling via asyncio.Queue to manage downstream database backpressure.\n" +
      "- Deficit 4: Missing active concurrency capping using asyncio.Semaphore to prevent out-of-memory crashes under heavy loads.";
    updateCharCount('input-plan-gap', 'count-plan-gap', 15000);
  }

  const inputPlanTrends = document.getElementById('input-plan-trends');
  if (inputPlanTrends) {
    inputPlanTrends.value = "- Exploding interest in high-throughput network engineering, asynchronous queue design, and memory footprint optimization.\n" +
      "- Bun/Go-like throughput performance demands on Python microservices.\n" +
      "- Increasing adoption of pgvector and semantic search systems.";
    updateCharCount('input-plan-trends', 'count-plan-trends', 5000);
  }

  const inputPlanStyle = document.getElementById('input-plan-style');
  if (inputPlanStyle) {
    inputPlanStyle.value = "Pragmatic, engineer-to-engineer, code-heavy, no high-level fluff, visceral opening focusing on raw socket failure, conversational but technically rigorous.";
    updateCharCount('input-plan-style', 'count-plan-style', 1000);
  }

  const inputWrite = document.getElementById('input-write');
  if (inputWrite) {
    inputWrite.value = "# CONTENT ARCHITECT BLUEPRINT: ENTERPRISE ASYNC PYTHON\n\n" +
      "## 1. THE OPENING (THE CRISIS)\n" +
      "- Hook: Describe the visceral feeling of a production python scraper crashing with a 'Socket Error: Connection reset by peer' or 'Too many open files' exception at 3 AM.\n" +
      "- Contrast: The naive asyncio.gather loop vs an enterprise-grade resilient system.\n\n" +
      "## 2. THE INFRASTRUCTURE (TCP CONNECTION POOLING)\n" +
      "- Core concept: Socket exhaustion and how TCP handshakes destroy throughput.\n" +
      "- Code implementation: aiohttp.ClientSession paired with custom TCPConnector limits.\n" +
      "- Show code:\n" +
      "```python\n" +
      "connector = aiohttp.TCPConnector(limit=100, limit_per_host=20, enable_cleanup_closed=True)\n" +
      "async with aiohttp.ClientSession(connector=connector) as session:\n" +
      "    ...\n" +
      "```\n\n" +
      "## 3. THE RATE LIMIT GATEKEEPER (EXPONENTIAL BACKOFF WITH JITTER)\n" +
      "- Core concept: Dynamic interception of HTTP 429 responses.\n" +
      "- Strategy: Read 'Retry-After' header, default to exponential backoff (base * 2^attempt) + random float (jitter) to prevent synchronization thundering herd problems.\n\n" +
      "## 4. THE COUPLING DECOUPLING (ASYNC PRODUCER-CONSUMER QUEUES)\n" +
      "- Core concept: Downstream write latency (e.g. database transactions taking 50ms) holding up rapid network ingestion (taking 5ms).\n" +
      "- Code implementation: asyncio.Queue with fixed maxsize to act as a buffer.\n" +
      "- Pattern: 1 Producer coroutine putting items into the queue, 5 Consumer coroutines concurrently processing them.\n\n" +
      "## 5. CONCURRENCY CAPPING (SEMAPHORES)\n" +
      "- Code implementation: asyncio.Semaphore to cap active connections and control RAM utilization.";
    updateCharCount('input-write', 'count-write', 20000);
  }

  // Page 2: Distribution Engine
  const engineTopicInput = document.getElementById('engineTopicInput');
  if (engineTopicInput) {
    engineTopicInput.value = "Thermodynamic capacity limits of freshwater networks: Hydrological closed-loop models and capacity constraints in urban municipal infrastructure under climate stressors";
    updateCharCount('engineTopicInput', 'topicCharCount', 2000);
  }

  const personaInput = document.getElementById('personaInput');
  if (personaInput) {
    personaInput.value = "You are a Principal Systems Engineer specializing in hydrological resource modeling. Write in a direct, engineer-to-engineer, pragmatic style. Focus on thermodynamic capacity limits, closed-loop water loop optimization, and freshwater as a finite systemic input variable.";
    updateCharCount('personaInput', 'personaCharCount', 4000);
    customPersona = personaInput.value;
  }

  showToast('🧪 Test inputs filled successfully!', 'success');
  saveToolDrafts();
}

// ── Init SSE and Content Preview on engine page ─────────────────
if (document.getElementById('logBody')) {
  connectSSE();
  fetchLatestReport(); // Pull existing content if it exists
}
