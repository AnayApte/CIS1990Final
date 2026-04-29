/* Penn Academic Co-Pilot — frontend */

'use strict';

// ── Marked config ─────────────────────────────────────────────────────────────
marked.use({ breaks: true, gfm: true });

// ── API helpers ───────────────────────────────────────────────────────────────
const api = {
  state() {
    return fetch('/api/state').then(r => r.json());
  },
  degreeProgress() {
    return fetch('/api/degree-progress').then(r => r.json());
  },
  scheduleDetail() {
    return fetch('/api/schedule-detail').then(r => r.json());
  },
  setup(body) {
    return fetch('/api/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => r.json());
  },
  chat(message) {
    return fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }).then(async r => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      return r.json();
    });
  },
  uploadTranscript(file, applyMode = 'stage') {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('apply_mode', applyMode);
    return fetch('/api/upload-transcript', { method: 'POST', body: fd }).then(r => {
      if (!r.ok) throw new Error('Upload failed');
      return r.json();
    });
  },
  confirmTranscript(add = [], remove = []) {
    return fetch('/api/confirm-transcript', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ add, remove }),
    }).then(r => r.json());
  },
  reset() {
    return fetch('/api/reset', { method: 'DELETE' }).then(r => r.json());
  },
};

// ── Page-level state ──────────────────────────────────────────────────────────
let transcriptUploaded = false;
let chatWired = false;
let setupWired = false;
let transcriptModalWired = false;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const state = await api.state();
    if (state.has_state) {
      showChat(state);
    } else {
      showSetup();
    }
  } catch {
    showSetup(); // network issue — fall through
  }
});

// ── Setup flow ────────────────────────────────────────────────────────────────
function showSetup() {
  const overlay = document.getElementById('setup-overlay');
  const appEl   = document.getElementById('app');

  overlay.classList.remove('hidden');
  appEl.classList.add('hidden');

  if (!setupWired) {
    wireSetup();
    setupWired = true;
  }
}

function wireSetup() {
  const majorSel   = document.getElementById('major-select');
  const startBtn   = document.getElementById('get-started-btn');

  majorSel.addEventListener('change', () => {
    startBtn.disabled = !majorSel.value;
  });

  wireUploadArea({
    areaId: 'upload-area',
    fileId: 'transcript-file',
    onFile: file => handleTranscriptUpload(file, {
      applyMode: 'stage',
      labelId: 'upload-label',
      previewId: 'transcript-preview',
      majorSelectId: 'major-select',
    }),
  });

  startBtn.addEventListener('click', handleGetStarted);
}

function wireUploadArea({ areaId, fileId, onFile }) {
  const uploadArea = document.getElementById(areaId);
  const fileInput = document.getElementById(fileId);
  if (!uploadArea || !fileInput) return;

  uploadArea.addEventListener('click', e => {
    if (e.target.closest('.upload-link')) {
      e.preventDefault();
    }
    fileInput.click();
  });

  uploadArea.addEventListener('dragover', e => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
  });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
  uploadArea.addEventListener('drop', e => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) onFile(fileInput.files[0]);
    fileInput.value = '';
  });
}

async function handleTranscriptUpload(file, {
  applyMode,
  labelId,
  previewId,
  statusId = null,
  majorSelectId = null,
}) {
  const label = document.getElementById(labelId);
  const preview = document.getElementById(previewId);
  const status = statusId ? document.getElementById(statusId) : null;

  label.innerHTML = `<span class="spinner"></span> Uploading…`;
  if (status) {
    status.classList.add('hidden');
    status.textContent = '';
  }

  try {
    const data = await api.uploadTranscript(file, applyMode);
    transcriptUploaded = applyMode === 'stage';
    label.textContent = `✓ ${file.name}`;
    if (majorSelectId) maybePrefillMajor(majorSelectId, data.student_info?.major || '');
    renderTranscriptPreview(data, previewId);
    renderTranscriptStatus(data, statusId);

    if (applyMode === 'merge') {
      await refreshSchedule();
      appendBotMessage(
        `Imported your transcript. Added **${data.added_count || 0}** new course` +
        `${(data.added_count || 0) === 1 ? '' : 's'} to your completed record.`
      );
    }
  } catch (err) {
    label.innerHTML = 'Upload failed — try again';
    preview.classList.add('hidden');
    if (status) {
      status.textContent = `Upload failed: ${err.message}`;
      status.className = 'transcript-status error';
      status.classList.remove('hidden');
    }
  }
}

function maybePrefillMajor(selectId, parsedMajor) {
  if (!parsedMajor) return;
  const select = document.getElementById(selectId);
  if (!select || select.value) return;

  const normalized = parsedMajor.trim().toLowerCase();
  const match = [...select.options].find(option =>
    option.value && option.value.trim().toLowerCase() === normalized
  );
  if (match) {
    select.value = match.value;
    select.dispatchEvent(new Event('change'));
  }
}

function renderTranscriptStatus(data, statusId) {
  if (!statusId) return;
  const status = document.getElementById(statusId);
  if (!status) return;

  let text = data.summary;
  if (data.apply_mode === 'merge') {
    text += ` Added ${data.added_count || 0} new course${(data.added_count || 0) === 1 ? '' : 's'}`;
    if (typeof data.existing_count === 'number') {
      text += `, skipped ${data.existing_count} already on record`;
    }
    if (typeof data.total_on_record === 'number') {
      text += `. You now have ${data.total_on_record} completed course${data.total_on_record === 1 ? '' : 's'} on file.`;
    } else {
      text += '.';
    }
    status.className = 'transcript-status success';
  } else {
    text += ' It will be added to your record when you start your session.';
    status.className = 'transcript-status pending';
  }

  status.textContent = text;
  status.classList.remove('hidden');
}

function renderTranscriptPreview(data, previewId = 'transcript-preview') {
  const preview = document.getElementById(previewId);

  let html = `<div class="tp-header">
    <span>${escHtml(data.summary || '')}</span>
    <span style="font-weight:400;color:#999">${data.applied ? 'saved to record' : 'review below'}</span>
  </div>`;

  for (const [sem, courses] of Object.entries(data.by_semester)) {
    html += `<div class="tp-semester">${escHtml(sem)}</div>`;
    for (const c of courses) {
      const rawTitle = c.title || '';
      const truncated = rawTitle.length > 38 ? rawTitle.slice(0, 38) + '…' : rawTitle;
      html += `<div class="tp-course">
        <span class="tp-code">${escHtml(c.code || '')}</span>
        <span class="tp-title" title="${escHtml(rawTitle)}">${escHtml(truncated)}</span>
        ${c.source === 'ap_credit' ? '<span class="tp-source">AP</span>' : ''}
        <span class="tp-grade">${escHtml(c.grade || '')}</span>
      </div>`;
    }
  }

  preview.innerHTML = html;
  preview.classList.remove('hidden');
}

async function handleGetStarted() {
  const btn   = document.getElementById('get-started-btn');
  const major = document.getElementById('major-select').value;
  if (!major) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Setting up…';

  try {
    if (transcriptUploaded) {
      await api.confirmTranscript();
    }
    const result = await api.setup({ major, classes_taken: [], preferences: {} });
    showChat(result.state);
  } catch (err) {
    console.error('Setup failed:', err);
    btn.disabled = false;
    btn.textContent = 'Get started →';
  }
}

// ── Chat flow ─────────────────────────────────────────────────────────────────
function showChat(state) {
  // Fade out overlay
  const overlay = document.getElementById('setup-overlay');
  overlay.style.opacity = '0';
  overlay.style.transition = 'opacity .3s';
  setTimeout(() => overlay.classList.add('hidden'), 280);

  const appEl = document.getElementById('app');
  appEl.classList.remove('hidden');
  appEl.classList.add('fade-in');

  updateHeaderBadges(state);
  if (!chatWired) {
    wireChatInput();
    wireTabs();
    chatWired = true;
  }
  if (!transcriptModalWired) {
    wireTranscriptModal();
    transcriptModalWired = true;
  }
  document.getElementById('chat-input').focus();

  // Contextual welcome message
  const courseCount = (state.classes_taken || []).length;
  const major = state.major || '';
  if (courseCount > 0) {
    appendBotMessage(
      `Welcome back! I have **${courseCount} course${courseCount !== 1 ? 's' : ''}** on record for you.` +
      (major ? ` Ready to keep planning your **${major}** degree.` : '') +
      ` What would you like to explore?`
    );
  } else if (major) {
    appendBotMessage(
      `Hi! I'm ready to help you plan your **${major}** courses at Penn. ` +
      `You can tell me which courses you've already taken, ask about requirements, ` +
      `or just ask what you should take next.`
    );
  }
}

function updateHeaderBadges(state) {
  const majorEl   = document.getElementById('header-major');
  const coursesEl = document.getElementById('header-courses');

  if (state.major) {
    majorEl.textContent = state.major;
    majorEl.classList.remove('hidden');
  } else {
    majorEl.classList.add('hidden');
  }

  const n = (state.classes_taken || []).length;
  if (n > 0) {
    coursesEl.textContent = `${n} course${n !== 1 ? 's' : ''}`;
    coursesEl.classList.remove('hidden');
  } else {
    coursesEl.classList.add('hidden');
  }
}

function wireChatInput() {
  const input    = document.getElementById('chat-input');
  const sendBtn  = document.getElementById('send-btn');
  const resetBtn = document.getElementById('reset-btn');
  const transcriptBtn = document.getElementById('transcript-btn');

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    sendBtn.disabled = !input.value.trim();
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) sendMessage();
    }
  });

  sendBtn.addEventListener('click', sendMessage);

  // Quick-start chips
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.msg;
      input.dispatchEvent(new Event('input'));
      sendMessage();
    });
  });

  resetBtn.addEventListener('click', async () => {
    if (!confirm('Start a new session? This will clear all saved courses and preferences.')) return;
    await api.reset();
    location.reload();
  });

  transcriptBtn.addEventListener('click', () => openTranscriptModal());
}

function wireTranscriptModal() {
  wireUploadArea({
    areaId: 'transcript-modal-area',
    fileId: 'transcript-modal-file',
    onFile: file => handleTranscriptUpload(file, {
      applyMode: 'merge',
      labelId: 'transcript-modal-label',
      previewId: 'transcript-modal-preview',
      statusId: 'transcript-modal-status',
    }),
  });

  document.getElementById('transcript-modal-close').addEventListener('click', closeTranscriptModal);
  document.getElementById('transcript-modal').addEventListener('click', e => {
    if (e.target.id === 'transcript-modal') closeTranscriptModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeTranscriptModal();
  });
}

function openTranscriptModal() {
  const modal = document.getElementById('transcript-modal');
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeTranscriptModal() {
  const modal = document.getElementById('transcript-modal');
  if (!modal || modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

async function sendMessage() {
  const input   = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const text    = input.value.trim();
  if (!text) return;

  // Dismiss welcome screen
  document.getElementById('welcome-msg')?.remove();

  // Post user message immediately
  appendUserMessage(text);
  input.value = '';
  input.style.height = 'auto';
  sendBtn.disabled = true;

  const typingId = showTyping();

  try {
    const data = await api.chat(text);
    hideTyping(typingId);
    appendBotMessage(data.response);
    await refreshSchedule();
  } catch (err) {
    hideTyping(typingId);
    appendBotMessage(`⚠️ Something went wrong: ${err.message}. Please try again.`);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

// ── Message rendering ─────────────────────────────────────────────────────────
function appendUserMessage(text) {
  const row = document.createElement('div');
  row.className = 'message-row user';
  row.innerHTML = `
    <div class="avatar user">You</div>
    <div class="bubble">${escHtml(text).replace(/\n/g, '<br>')}</div>
  `;
  appendRow(row);
}

function appendBotMessage(markdown) {
  const row = document.createElement('div');
  row.className = 'message-row agent';
  row.innerHTML = `
    <div class="avatar agent">P</div>
    <div class="bubble">${DOMPurify.sanitize(marked.parse(markdown))}</div>
  `;
  appendRow(row);
}

function showTyping() {
  const id  = `typing-${Date.now()}`;
  const row = document.createElement('div');
  row.className = 'message-row agent';
  row.id = id;
  row.innerHTML = `
    <div class="avatar agent">P</div>
    <div class="bubble typing-bubble">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>
  `;
  appendRow(row);
  return id;
}

function hideTyping(id) {
  document.getElementById(id)?.remove();
}

function appendRow(el) {
  const area = document.getElementById('messages');
  area.appendChild(el);
  area.scrollTop = area.scrollHeight;
}

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function wireTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  document.getElementById('refresh-grid-btn').addEventListener('click', loadScheduleTab);
}

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab)
  );
  const toChat     = tab === 'chat';
  const chatView   = document.getElementById('chat-view');
  const schedView  = document.getElementById('schedule-view');
  chatView.classList.toggle('hidden', !toChat);
  schedView.classList.toggle('hidden', toChat);
  if (!toChat) loadScheduleTab();
}

// ── Schedule tab ──────────────────────────────────────────────────────────────
async function loadScheduleTab() {
  await refreshSchedule({ showLoading: true });
}

function setProgressLoading() {
  document.getElementById('progress-content').innerHTML =
    '<div class="data-loading"><span class="spinner-dark"></span> Loading…</div>';
}

function setGridLoading() {
  document.getElementById('time-grid').innerHTML =
    '<div class="data-loading"><span class="spinner-dark"></span> Loading schedule…</div>';
}

async function refreshSchedule({ showLoading = false } = {}) {
  const progressEl = document.getElementById('progress-content');
  const gridEl = document.getElementById('time-grid');
  const gridScroll = document.querySelector('.grid-scroll');
  if (!progressEl || !gridEl) return;

  const progressScrollTop = progressEl.scrollTop;
  const gridScrollTop = gridScroll?.scrollTop || 0;

  if (showLoading) {
    setProgressLoading();
    setGridLoading();
  }

  try {
    const [state, progressData, scheduleData] = await Promise.all([
      api.state(),
      api.degreeProgress(),
      api.scheduleDetail(),
    ]);
    updateHeaderBadges(state);
    renderProgressSidebar(progressData);
    renderTimeGrid(scheduleData);
    progressEl.scrollTop = progressScrollTop;
    if (gridScroll) gridScroll.scrollTop = gridScrollTop;
  } catch (err) {
    progressEl.innerHTML = `<div class="data-loading">Failed to load — ${err.message}</div>`;
    gridEl.innerHTML = `<div class="data-loading">Failed to load — ${err.message}</div>`;
  }
}

// ── Degree progress sidebar ───────────────────────────────────────────────────

// Maps section name → { dot, fill } colors
const SECTION_COLORS = {
  engineering:    { dot: '#1d4ed8', fill: '#3b82f6' },
  math:           { dot: '#15803d', fill: '#22c55e' },
  naturalscience: { dot: '#0f766e', fill: '#14b8a6' },
  social:         { dot: '#7c3aed', fill: '#a855f7' },
  elective:       { dot: '#c2410c', fill: '#f97316' },
  writing:        { dot: '#0369a1', fill: '#38bdf8' },
  default:        { dot: '#6b7280', fill: '#9ca3af' },
};

function sectionColorKey(name) {
  const n = name.toLowerCase();
  if (n.includes('engineer'))              return 'engineering';
  if (n.includes('math'))                  return 'math';
  if (n.includes('natural') || n.includes('science') || n.includes('phys')) return 'naturalscience';
  if (n.includes('social') || n.includes('humanit') || n.includes('ssh'))   return 'social';
  if (n.includes('elective') || n.includes('general')) return 'elective';
  if (n.includes('writ') || n.includes('english') || n.includes('comm'))    return 'writing';
  return 'default';
}

function renderProgressSidebar(data) {
  if (data.error) {
    document.getElementById('progress-content').innerHTML =
      `<div class="data-loading">${data.error}</div>`;
    return;
  }

  const pct = data.total_count > 0
    ? ((data.satisfied_count / data.total_count) * 100).toFixed(1)
    : 0;

  let html = `
    <div class="prog-summary">
      <div class="prog-program">${escHtml(data.program || '')}</div>
      <div class="prog-total-label">${data.satisfied_count} / ${data.total_count} requirements met</div>
      <div class="prog-bar-outer">
        <div class="prog-bar-inner" style="width:${pct}%"></div>
      </div>
    </div>
  `;

  for (const section of (data.sections || [])) {
    const key    = sectionColorKey(section.name);
    const colors = SECTION_COLORS[key];
    const spct   = section.total > 0 ? (section.done / section.total * 100).toFixed(1) : 0;

    html += `<div class="prog-section">
      <div class="prog-section-head">
        <span class="prog-dot" style="background:${colors.dot}"></span>
        <span class="prog-section-name" title="${escHtml(section.name)}">${escHtml(section.name)}</span>
        <span class="prog-section-count">${section.done}/${section.total}</span>
      </div>
      <div class="prog-mini-bar">
        <div class="prog-mini-fill" style="width:${spct}%; background:${colors.fill}"></div>
      </div>
      <div class="prog-items">`;

    for (const req of section.satisfied) {
      const label = req.codes[0] || req.label;
      html += `<div class="prog-item done">
        <span class="prog-icon">✓</span>
        <span title="${escHtml(req.label)}">${escHtml(label)}</span>
      </div>`;
    }

    const shown = section.unsatisfied.slice(0, 4);
    for (const req of shown) {
      const label = req.missing[0] || req.codes[0] || req.label;
      html += `<div class="prog-item miss">
        <span class="prog-icon">○</span>
        <span title="${escHtml(req.label)}">${escHtml(label)}</span>
      </div>`;
    }
    if (section.unsatisfied.length > 4) {
      html += `<div class="prog-item more">+${section.unsatisfied.length - 4} more</div>`;
    }

    html += `</div></div>`;
  }

  document.getElementById('progress-content').innerHTML = html;
}

// ── Time grid ─────────────────────────────────────────────────────────────────

// Penn PCR times are HH.MM floats (not decimal hours)
function hhmm(t) {
  const h = Math.floor(t);
  const m = Math.round((t - h) * 100);
  return h + m / 60;   // convert to decimal hours
}

function formatTimeLabel(decimalHour) {
  const totalMinutes = Math.round(decimalHour * 60);
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? 'PM' : 'AM';
  const hour12 = hour24 % 12 || 12;
  return `${hour12}:${String(minutes).padStart(2, '0')} ${suffix}`;
}

function formatMeetingRange(start, end) {
  return `${formatTimeLabel(hhmm(start))} - ${formatTimeLabel(hhmm(end))}`;
}

const GRID_START = 8;          // 8:00 AM
const GRID_END   = 21;         // 9:00 PM
const SLOT_STEP  = 0.5;        // 30 minutes
const SLOT_PX    = 34;         // pixels per 30-minute row
const HOUR_PX    = SLOT_PX / SLOT_STEP;
const TOTAL_SLOTS = Math.round((GRID_END - GRID_START) / SLOT_STEP);
const TOTAL_H    = TOTAL_SLOTS * SLOT_PX;

// Requirement section → block color { bg, text, border }
const BLOCK_COLORS = {
  engineering:    { bg: '#dbeafe', text: '#1e3a8a', border: '#3b82f6' },
  math:           { bg: '#dcfce7', text: '#14532d', border: '#22c55e' },
  naturalscience: { bg: '#d1fae5', text: '#065f46', border: '#10b981' },
  social:         { bg: '#ede9fe', text: '#4c1d95', border: '#8b5cf6' },
  elective:       { bg: '#ffedd5', text: '#7c2d12', border: '#fb923c' },
  writing:        { bg: '#e0f2fe', text: '#0c4a6e', border: '#38bdf8' },
  default:        { bg: '#f1f5f9', text: '#334155', border: '#94a3b8' },
};

function blockColors(reqSection) {
  return BLOCK_COLORS[sectionColorKey(reqSection)] || BLOCK_COLORS.default;
}

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
const DAY_CODES  = ['M',   'T',   'W',   'R',   'F'];

function computeDayBlockLayout(blocks) {
  const sorted = [...blocks].sort((a, b) => {
    if (a.startDec !== b.startDec) return a.startDec - b.startDec;
    if (a.endDec !== b.endDec) return a.endDec - b.endDec;
    return a.id.localeCompare(b.id);
  });

  let cluster = [];
  let clusterEnd = -Infinity;

  function finalizeCluster(items) {
    if (!items.length) return;
    const lanes = [];
    items.forEach(item => {
      let laneIndex = lanes.findIndex(lastEnd => lastEnd <= item.startDec);
      if (laneIndex === -1) {
        laneIndex = lanes.length;
        lanes.push(item.endDec);
      } else {
        lanes[laneIndex] = item.endDec;
      }
      item.lane = laneIndex;
      item.laneCount = 0;
    });
    const laneCount = lanes.length || 1;
    items.forEach(item => {
      item.laneCount = laneCount;
    });
  }

  sorted.forEach(item => {
    if (!cluster.length || item.startDec < clusterEnd) {
      cluster.push(item);
      clusterEnd = Math.max(clusterEnd, item.endDec);
      return;
    }
    finalizeCluster(cluster);
    cluster = [item];
    clusterEnd = item.endDec;
  });
  finalizeCluster(cluster);
  return sorted;
}

function renderTimeGrid(scheduleData) {
  const courses = (scheduleData.courses || []);
  const gridEl = document.getElementById('time-grid');

  if (courses.length === 0) {
    gridEl.innerHTML = `
      <div class="grid-empty">
        <div class="empty-icon">📅</div>
        <p>No courses in your schedule yet.</p>
        <p style="font-size:.82rem">Add courses via chat — try "add CIS-1210 to my schedule"</p>
      </div>`;
    return;
  }

  // Check if any course has meeting data
  const hasMeetings = courses.some(c => c.lec_sections?.some(s => s.meetings?.length));

  if (!hasMeetings) {
    // Show as a simple list instead of the time grid
    let listHtml = `<div style="padding:1rem;width:100%">
      <p style="color:var(--text-muted);font-size:.85rem;margin-bottom:.75rem">
        No live meeting times found — courses shown below.</p>`;
    for (const c of courses) {
      const colors = blockColors(c.requirement_section);
      listHtml += `<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.4rem">
        <span style="width:10px;height:10px;border-radius:50%;background:${colors.border};flex-shrink:0"></span>
        <span style="font-weight:700;font-size:.88rem">${escHtml(c.code)}</span>
        ${c.requirement_section ? `<span style="font-size:.78rem;color:var(--text-muted)">${escHtml(c.requirement_section)}</span>` : ''}
      </div>`;
    }
    listHtml += '</div>';
    gridEl.innerHTML = listHtml;
    return;
  }

  // Build time ruler
  let rulerHTML = `<div class="tr-ruler">
    <div class="tr-ruler-header"></div>
    <div class="tr-ruler-slots" style="height:${TOTAL_H}px">`;
  for (let slot = 0; slot <= TOTAL_SLOTS; slot++) {
    const time = GRID_START + slot * SLOT_STEP;
    const y = slot * SLOT_PX;
    const transform = slot === 0 ? 'translateY(0)' : slot === TOTAL_SLOTS ? 'translateY(-100%)' : 'translateY(-50%)';
    rulerHTML += `<div class="tr-tick" style="top:${y}px;transform:${transform}">${formatTimeLabel(time)}</div>`;
  }
  rulerHTML += '</div></div>';

  // Collect all block specs for conflict detection
  const blockSpecs = [];

  // Build day columns
  let daysHTML = '<div class="tr-days">';
  DAY_CODES.forEach((dayCode, idx) => {
    let slotsHTML = `<div class="tr-slots" style="height:${TOTAL_H}px">`;

    // 30-minute grid lines
    for (let slot = 0; slot <= TOTAL_SLOTS; slot++) {
      const y = slot * SLOT_PX;
      const lineClass = slot % 2 === 0 ? 'tr-hline-hour' : 'tr-hline-half';
      slotsHTML += `<div class="tr-hline ${lineClass}" style="top:${y}px"></div>`;
    }

    // Course blocks for this day
    const dayBlocks = [];
    courses.forEach(course => {
      const colors = blockColors(course.requirement_section);
      (course.lec_sections || []).forEach(section => {
        (section.meetings || []).forEach(meeting => {
          if (meeting.day !== dayCode) return;

          const startDec = hhmm(meeting.start);
          const endDec   = hhmm(meeting.end);

          // Clamp to grid bounds
          if (endDec <= GRID_START || startDec >= GRID_END) return;
          const clampedStart = Math.max(startDec, GRID_START);
          const clampedEnd   = Math.min(endDec,   GRID_END);

          const top    = (clampedStart - GRID_START) * HOUR_PX;
          const height = Math.max((clampedEnd - clampedStart) * HOUR_PX, 18);
          const blockId = `blk-${course.code}-${dayCode}-${meeting.start}`.replace(/[^a-z0-9-]/gi, '_');

          dayBlocks.push({
            id: blockId,
            dayCode,
            startDec,
            endDec,
            top,
            height,
            colors,
            courseCode: course.code,
            meetingTime: formatMeetingRange(meeting.start, meeting.end),
          });
        });
      });
    });

    const laidOutBlocks = computeDayBlockLayout(dayBlocks);
    laidOutBlocks.forEach(block => {
      const widthPct = 100 / (block.laneCount || 1);
      const leftPct = block.lane * widthPct;
      blockSpecs.push({
        dayCode: block.dayCode,
        startDec: block.startDec,
        endDec: block.endDec,
        id: block.id,
      });

      slotsHTML += `<div class="tr-block" id="${block.id}"
        style="top:${block.top}px; height:${block.height}px;
               left:calc(${leftPct}% + 4px); width:calc(${widthPct}% - 8px);
               background:${block.colors.bg}; color:${block.colors.text};
               border-left-color:${block.colors.border}">
        <div class="tr-block-code">${escHtml(block.courseCode)}</div>
        <div class="tr-block-time">${escHtml(block.meetingTime)}</div>
      </div>`;
    });

    slotsHTML += '</div>';
    daysHTML += `<div class="tr-day">
      <div class="tr-day-header">${DAY_LABELS[idx]}</div>
      ${slotsHTML}
    </div>`;
  });
  daysHTML += '</div>';

  gridEl.innerHTML = rulerHTML + daysHTML;

  // Conflict detection — runs after HTML is set so IDs exist
  detectConflicts(blockSpecs);
}

function detectConflicts(specs) {
  for (let i = 0; i < specs.length; i++) {
    for (let j = i + 1; j < specs.length; j++) {
      if (specs[i].dayCode !== specs[j].dayCode) continue;
      const overlaps = specs[i].startDec < specs[j].endDec &&
                       specs[j].startDec < specs[i].endDec;
      if (overlaps) {
        document.getElementById(specs[i].id)?.classList.add('conflict');
        document.getElementById(specs[j].id)?.classList.add('conflict');
      }
    }
  }
}
