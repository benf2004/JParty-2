'use strict';

/* ─── Config ───────────────────────────────────────────────── */
const ROUND_CONFIG = {
  jeopardy: { type: 'jeopardy', values: [200, 400, 600, 800, 1000], title: 'Jeopardy' },
  double:   { type: 'doublejeopardy', values: [400, 800, 1200, 1600, 2000], title: 'Double Jeopardy' },
  final:    { type: 'final', values: [], title: 'Final Jeopardy' },
};

const DEFAULT_CATEGORIES = ['Category 1','Category 2','Category 3','Category 4','Category 5','Category 6'];
const STORAGE_KEY = 'jparty_designer_v1';
const DB_NAME = 'jparty_designer';
const DB_VERSION = 1;
const DB_STORE = 'drafts';
const DRAFT_ID = 'current';
const COL_LETTERS = ['A','B','C','D','E','F'];

/* ─── State ────────────────────────────────────────────────── */
const state = {
  selectedRound: 'jeopardy',
  selectedQuestionIndex: 0,
  mediaOpen: false,
  game: {
    date: new Date().toISOString().slice(0, 10),
    title: 'My Custom JParty Game',
    comments: '',
    rounds: [
      { type: 'jeopardy',       categories: [...DEFAULT_CATEGORIES], questions: [] },
      { type: 'doublejeopardy', categories: [...DEFAULT_CATEGORIES], questions: [] },
      {
        type: 'final',
        question: {
          index: [0,0], text: '', answer: '', category: 'Final Jeopardy',
          value: -1, image_link: null, audio_link: null, video_link: null,
          includes_audio: false, image_file: null, audio_file: null, video_file: null,
        },
      },
    ],
  },
};

/* ─── Helpers ──────────────────────────────────────────────── */
const $ = s => document.querySelector(s);
const $all = s => Array.from(document.querySelectorAll(s));

function getActiveRound() {
  return state.game.rounds.find(r => r.type === ROUND_CONFIG[state.selectedRound].type);
}

function isAudioLink(path) {
  return !!path && ['.mp3','.wav','.ogg','.m4a'].some(e => path.toLowerCase().endsWith(e));
}

function getCurrentQuestion() {
  if (state.selectedRound === 'final') {
    return state.game.rounds.find(r => r.type === 'final').question;
  }
  return getActiveRound().questions[state.selectedQuestionIndex];
}

function getMediaItems(q) {
  return [
    { type: 'image', label: 'Image URL', field: 'image_link', value: q.image_link, kind: 'link' },
    { type: 'audio', label: 'Audio URL', field: 'audio_link', value: q.audio_link, kind: 'link' },
    { type: 'video', label: 'Video URL', field: 'video_link', value: q.video_link, kind: 'link' },
    { type: 'image', label: 'Image File', field: 'image_file', value: q.image_file, kind: 'file' },
    { type: 'audio', label: 'Audio File', field: 'audio_file', value: q.audio_file, kind: 'file' },
    { type: 'video', label: 'Video File', field: 'video_file', value: q.video_file, kind: 'file' },
  ].filter(item => !!item.value);
}

function getMediaCount(q) {
  return getMediaItems(q).length;
}

function mediaDisplayName(item) {
  if (item.kind === 'file') return item.value.name || `${item.type} file`;
  return item.value;
}

function getMediaTypeFromField(field) {
  if (field.startsWith('image_')) return 'image';
  if (field.startsWith('audio_')) return 'audio';
  if (field.startsWith('video_')) return 'video';
  return 'link';
}

function getYoutubeEmbedUrl(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    let videoId = null;
    if (host.includes('youtu.be')) {
      videoId = u.pathname.replace(/^\/+/, '');
    } else if (host.includes('youtube.com')) {
      videoId = u.searchParams.get('v');
    }
    if (!videoId) return null;
    const start = u.searchParams.get('t');
    const params = new URLSearchParams({ autoplay: '1' });
    if (start && /^\d+$/.test(start)) params.set('start', start);
    return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}?${params.toString()}`;
  } catch (e) {
    return null;
  }
}

function buildMediaStatus(q) {
  const items = getMediaItems(q);
  if (!items.length) {
    return `
      <div class="media-status empty">
        <span>No media attached</span>
      </div>
    `;
  }

  return `
    <div class="media-status">
      ${items.map(item => `
        <div class="media-status-row">
          <div class="media-status-copy">
            <span class="media-status-type">${escHtml(item.label)}</span>
            <span class="media-status-name">${escHtml(mediaDisplayName(item))}</span>
          </div>
          <div class="media-status-actions">
            <button type="button" class="media-mini-btn" data-media-view="${item.field}">
              ${item.kind === 'file' ? 'View' : 'Open'}
            </button>
            <button type="button" class="media-mini-btn danger" data-media-remove="${item.field}">Remove</button>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

/* ─── Question Initialization ──────────────────────────────── */
function initializeQuestions() {
  ['jeopardy','double'].forEach(key => {
    const config = ROUND_CONFIG[key];
    const round  = state.game.rounds.find(r => r.type === config.type);
    if (round.questions.length === 0) {
      round.questions = [];
      for (let col = 0; col < 6; col++) {
        for (let row = 0; row < config.values.length; row++) {
          round.questions.push({
            index: [col, row],
            text: '', answer: '',
            category: round.categories[col],
            value: config.values[row],
            dd: false,
            image_link: null, audio_link: null, video_link: null,
            includes_audio: false,
            image_file: null, audio_file: null, video_file: null,
          });
        }
      }
    }
  });
}

/* ─── Browser Storage ──────────────────────────────────────── */
let saveTimer = null;
let dbPromise = null;

function openDesignerDB() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        request.result.createObjectStore(DB_STORE, { keyPath: 'id' });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  return dbPromise;
}

async function writeDraft() {
  const db = await openDesignerDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readwrite');
    tx.objectStore(DB_STORE).put({
      id: DRAFT_ID,
      selectedRound: state.selectedRound,
      selectedQuestionIndex: state.selectedQuestionIndex,
      game: state.game,
      savedAt: new Date().toISOString(),
    });
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function readDraft() {
  const db = await openDesignerDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readonly');
    const request = tx.objectStore(DB_STORE).get(DRAFT_ID);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

function scheduleSave() {
  clearTimeout(saveTimer);
  const dot  = document.querySelector('.autosave-dot');
  const text = document.querySelector('.autosave-text');
  if (dot)  dot.classList.add('saving');
  if (text) text.textContent = 'Saving…';

  saveTimer = setTimeout(async () => {
    let saved = false;
    try {
      await writeDraft();
      saved = true;
    } catch (e) { /* quota exceeded, blocked storage, or private mode */ }

    if (dot)  dot.classList.remove('saving');
    if (text) text.textContent = saved ? 'Saved' : 'Save failed';
  }, 600);
}

async function loadFromStorage() {
  try {
    let saved = null;
    try {
      saved = await readDraft();
    } catch (e) {
      saved = null;
    }
    if (!saved) {
      const raw = localStorage.getItem(STORAGE_KEY);
      saved = raw ? JSON.parse(raw) : null;
    }
    if (!saved?.game?.rounds) return false;

    Object.assign(state.game, saved.game);
    if (saved.selectedRound) state.selectedRound = saved.selectedRound;
    if (typeof saved.selectedQuestionIndex === 'number') state.selectedQuestionIndex = saved.selectedQuestionIndex;
    return true;
  } catch (e) { return false; }
}

/* ─── Progress ─────────────────────────────────────────────── */
function countFilled(questions) {
  return questions.filter(q => q.text.trim() !== '').length;
}

function updateProgress() {
  const jeo   = state.game.rounds.find(r => r.type === 'jeopardy');
  const djo   = state.game.rounds.find(r => r.type === 'doublejeopardy');
  const fin   = state.game.rounds.find(r => r.type === 'final');

  const jFill = countFilled(jeo.questions);
  const dFill = countFilled(djo.questions);
  const fFill = fin.question.text.trim() ? 1 : 0;
  const total = jFill + dFill + fFill;
  const max   = 61;

  const bJ = document.getElementById('badge-jeopardy');
  const bD = document.getElementById('badge-double');
  const bF = document.getElementById('badge-final');
  if (bJ) bJ.textContent = `${jFill}/30`;
  if (bD) bD.textContent = `${dFill}/30`;
  if (bF) bF.textContent = `${fFill}/1`;

  const fill = document.getElementById('progress-fill');
  if (fill) fill.style.width = `${(total / max) * 100}%`;
}

/* ─── Render ───────────────────────────────────────────────── */
function render() {
  const body = $('#designer-body');
  body.innerHTML = '';

  const key = state.selectedRound;
  const config = ROUND_CONFIG[key];

  if (key === 'final') {
    body.appendChild(buildFinalEditor());
  } else {
    body.appendChild(buildBoardPanel(config));
    body.appendChild(buildEditorPanel(config));
  }

  bindEditorEvents();
  updateProgress();
}

/* ─── Board Panel ──────────────────────────────────────────── */
function buildBoardPanel(config) {
  const activeRound = getActiveRound();

  const panel = document.createElement('div');
  panel.className = 'panel';

  // Header
  const header = document.createElement('div');
  header.className = 'panel-header';
  header.innerHTML = `<span class="panel-title">${config.title} Board</span>`;
  panel.appendChild(header);

  const body = document.createElement('div');
  body.className = 'panel-body';

  // Categories
  const catGrid = document.createElement('div');
  catGrid.className = 'category-grid';
  activeRound.categories.forEach((cat, i) => {
    const slot = document.createElement('div');
    slot.className = 'category-slot';
    slot.innerHTML = `<span class="category-num">Column ${COL_LETTERS[i]}</span>`;
    const inp = document.createElement('input');
    inp.className = 'category-input';
    inp.value = cat;
    inp.placeholder = `Category ${i+1}`;
    inp.dataset.categoryIndex = i;
    slot.appendChild(inp);
    catGrid.appendChild(slot);
  });
  body.appendChild(catGrid);

  // Clue board
  const sectionTitle = document.createElement('div');
  sectionTitle.className = 'clue-section-title';
  sectionTitle.textContent = 'Select a clue to edit';
  body.appendChild(sectionTitle);

  const board = document.createElement('div');
  board.className = 'clue-board';

  // Column headers
  COL_LETTERS.forEach(l => {
    const h = document.createElement('div');
    h.className = 'clue-col-header';
    h.textContent = l;
    board.appendChild(h);
  });

  // Cells arranged by row
  for (let row = 0; row < config.values.length; row++) {
    for (let col = 0; col < 6; col++) {
      const qIndex = activeRound.questions.findIndex(q => q.index[0] === col && q.index[1] === row);
      const q = activeRound.questions[qIndex];

      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'clue-cell' +
        (qIndex === state.selectedQuestionIndex ? ' selected' : '') +
        (q?.text?.trim() ? ' filled' : '') +
        (q?.dd ? ' has-dd' : '') +
        (getMediaCount(q) ? ' has-media' : '');
      cell.dataset.qindex = qIndex;

      cell.innerHTML = `
        <div class="clue-value">$${config.values[row]}</div>
        <div class="clue-preview">${q?.text?.slice(0, 50) || ''}</div>
        ${getMediaCount(q) ? '<span class="media-badge">MEDIA</span>' : ''}
      `;
      cell.addEventListener('click', () => {
        state.selectedQuestionIndex = qIndex;
        state.mediaOpen = false;
        render();
      });
      board.appendChild(cell);
    }
  }
  body.appendChild(board);
  panel.appendChild(body);
  return panel;
}

/* ─── Editor Panel ─────────────────────────────────────────── */
function buildEditorPanel(config) {
  const activeRound = getActiveRound();
  const q = activeRound.questions[state.selectedQuestionIndex];
  const crumb = `${COL_LETTERS[q.index[0]]}${q.index[1]+1} — ${config.title} — $${q.value}`;

  const panel = document.createElement('div');
  panel.className = 'panel editor-panel';

  const header = document.createElement('div');
  header.className = 'panel-header';
  header.innerHTML = `
    <span class="panel-title">Edit Clue</span>
    <span class="editor-crumb">${crumb}</span>
  `;
  panel.appendChild(header);

  const body = document.createElement('div');
  body.className = 'panel-body';

  body.innerHTML = `
    <div class="field-stack">
      <div class="field-row">
        <label class="field-label" for="editor-category">Category</label>
        <input class="field-input" id="editor-category" value="${escHtml(q.category)}" placeholder="Category name" />
      </div>
      <div class="field-row">
        <label class="field-label" for="editor-text">Clue (Question)</label>
        <textarea class="field-textarea" id="editor-text" placeholder="Enter the clue text shown to players…">${escHtml(q.text)}</textarea>
      </div>
      <div class="field-row">
        <label class="field-label" for="editor-answer">Answer</label>
        <textarea class="field-textarea" id="editor-answer" placeholder="What is…">${escHtml(q.answer)}</textarea>
      </div>
      <div class="field-inline">
        <div class="field-row">
          <label class="field-label" for="editor-value">Point Value</label>
          <input class="field-input" id="editor-value" type="number" value="${q.value}" min="0" step="200" />
        </div>
        <label class="dd-toggle${q.dd ? ' active' : ''}" id="dd-toggle-label" role="switch" aria-checked="${q.dd ? 'true' : 'false'}" tabindex="0">
          <input type="checkbox" id="editor-dd" ${q.dd ? 'checked' : ''} />
          <span class="dd-switch" aria-hidden="true"><span class="dd-switch-knob"></span></span>
          <span class="dd-label">Daily Double</span>
        </label>
      </div>

      <div class="media-collapsible">
        <button type="button" class="media-toggle-btn${state.mediaOpen ? ' open' : ''}" id="media-toggle">
          <span>Media / Links${getMediaCount(q) ? ` (${getMediaCount(q)})` : ''}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="media-fields${state.mediaOpen ? ' open' : ''}">
          ${buildMediaStatus(q)}
          <div class="field-row">
            <label class="field-label" for="editor-image-url">Image URL</label>
            <input class="field-input" id="editor-image-url" value="${escHtml(q.image_link||'')}" placeholder="https://…" />
          </div>
          <div class="field-row">
            <label class="field-label" for="editor-audio-url">Audio URL</label>
            <input class="field-input" id="editor-audio-url" value="${escHtml(q.audio_link||'')}" placeholder="https://…" />
          </div>
          <div class="field-row">
            <label class="field-label" for="editor-video-url">Video URL</label>
            <input class="field-input" id="editor-video-url" value="${escHtml(q.video_link||'')}" placeholder="https://… or YouTube" />
          </div>
          <div class="field-row">
            <label class="field-label" for="editor-image-file">Local Image File</label>
            <input class="field-input--file" id="editor-image-file" type="file" accept="image/*" />
          </div>
          <div class="field-row">
            <label class="field-label" for="editor-audio-file">Local Audio File</label>
            <input class="field-input--file" id="editor-audio-file" type="file" accept="audio/*" />
          </div>
          <div class="field-row">
            <label class="field-label" for="editor-video-file">Local Video File</label>
            <input class="field-input--file" id="editor-video-file" type="file" accept="video/*" />
          </div>
        </div>
      </div>
    </div>
  `;

  panel.appendChild(body);
  return panel;
}

/* ─── Final Jeopardy Editor ────────────────────────────────── */
function buildFinalEditor() {
  const finalRound = state.game.rounds.find(r => r.type === 'final');
  const q = finalRound.question;

  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'grid-column: 1 / -1;';

  const panel = document.createElement('div');
  panel.className = 'panel final-layout';

  panel.innerHTML = `
    <div class="panel-header">
      <span class="panel-title">Final Jeopardy</span>
    </div>
    <div class="panel-body">
      <div class="field-stack">
        <div class="field-row">
          <label class="field-label" for="editor-category">Category</label>
          <input class="field-input" id="editor-category" value="${escHtml(q.category)}" placeholder="Final Jeopardy" />
        </div>
        <div class="field-row">
          <label class="field-label" for="editor-text">Clue</label>
          <textarea class="field-textarea" id="editor-text" placeholder="The final clue…" style="min-height:120px">${escHtml(q.text)}</textarea>
        </div>
        <div class="field-row">
          <label class="field-label" for="editor-answer">Answer</label>
          <textarea class="field-textarea" id="editor-answer" placeholder="What is…">${escHtml(q.answer)}</textarea>
        </div>

        <div class="media-collapsible">
          <button type="button" class="media-toggle-btn${state.mediaOpen ? ' open' : ''}" id="media-toggle">
            <span>Media / Links${getMediaCount(q) ? ` (${getMediaCount(q)})` : ''}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div class="media-fields${state.mediaOpen ? ' open' : ''}">
            ${buildMediaStatus(q)}
            <div class="field-row">
              <label class="field-label" for="editor-image-url">Image URL</label>
              <input class="field-input" id="editor-image-url" value="${escHtml(q.image_link||'')}" placeholder="https://…" />
            </div>
            <div class="field-row">
              <label class="field-label" for="editor-audio-url">Audio URL</label>
              <input class="field-input" id="editor-audio-url" value="${escHtml(q.audio_link||'')}" placeholder="https://…" />
            </div>
            <div class="field-row">
              <label class="field-label" for="editor-video-url">Video URL</label>
              <input class="field-input" id="editor-video-url" value="${escHtml(q.video_link||'')}" placeholder="https://… or YouTube" />
            </div>
            <div class="field-row">
              <label class="field-label" for="editor-image-file">Local Image File</label>
              <input class="field-input--file" id="editor-image-file" type="file" accept="image/*" />
            </div>
            <div class="field-row">
              <label class="field-label" for="editor-audio-file">Local Audio File</label>
              <input class="field-input--file" id="editor-audio-file" type="file" accept="audio/*" />
            </div>
            <div class="field-row">
              <label class="field-label" for="editor-video-file">Local Video File</label>
              <input class="field-input--file" id="editor-video-file" type="file" accept="video/*" />
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  wrapper.appendChild(panel);
  return wrapper;
}

/* ─── Bind Events ──────────────────────────────────────────── */
function bindEditorEvents() {
  const isFinal = state.selectedRound === 'final';

  function updateField(field, value) {
    if (isFinal) {
      const q = state.game.rounds[2].question;
      q[field] = value;
      if (field === 'audio_link') q.includes_audio = !!(value || q.audio_file);
    } else {
      const q = getActiveRound().questions[state.selectedQuestionIndex];
      q[field] = value;
      if (field === 'category') {
        // Sync category input back to round categories
        const activeRound = getActiveRound();
        const col = q.index[0];
        activeRound.categories[col] = value;
        const catInput = document.querySelector(`[data-category-index="${col}"]`);
        if (catInput) catInput.value = value;
      }
      if (field === 'audio_link') q.includes_audio = !!(value || q.audio_file);
    }
    scheduleSave();
  }

  function setFile(field, file) {
    if (isFinal) {
      const q = state.game.rounds[2].question;
      q[field] = file;
      if (file && field === 'audio_file') q.includes_audio = true;
    } else {
      const q = getActiveRound().questions[state.selectedQuestionIndex];
      q[field] = file;
      if (file && field === 'audio_file') q.includes_audio = true;
    }
    scheduleSave();
  }

  function clearMedia(field) {
    const q = getCurrentQuestion();
    q[field] = null;
    if (field === 'audio_link' || field === 'audio_file') {
      q.includes_audio = !!(q.audio_link || q.audio_file);
    }
    scheduleSave();
    state.mediaOpen = true;
    render();
  }

  function viewMedia(field) {
    const value = getCurrentQuestion()[field];
    if (!value) return;
    const type = getMediaTypeFromField(field);
    if (value instanceof Blob) {
      const url = URL.createObjectURL(value);
      openMediaModal({ type, title: value.name || `${type} file`, url, revokeUrl: url });
      return;
    }
    openMediaModal({ type, title: value, url: value });
  }

  // Category inputs (board panel)
  $all('[data-category-index]').forEach(inp => {
    inp.oninput = () => {
      const i = Number(inp.dataset.categoryIndex);
      const activeRound = getActiveRound();
      activeRound.categories[i] = inp.value;
      activeRound.questions?.forEach(q => { if (q.index[0] === i) q.category = inp.value; });
      scheduleSave();
      // Lightweight re-render of board only
      const board = document.querySelector('.clue-board');
      if (board) refreshBoardCells();
    };
  });

  // Media toggle
  const mediaToggle = $('#media-toggle');
  if (mediaToggle) {
    mediaToggle.onclick = () => {
      state.mediaOpen = !state.mediaOpen;
      mediaToggle.classList.toggle('open', state.mediaOpen);
      const mf = mediaToggle.nextElementSibling;
      if (mf) mf.classList.toggle('open', state.mediaOpen);
    };
  }

  $all('[data-media-remove]').forEach(btn => {
    btn.onclick = () => clearMedia(btn.dataset.mediaRemove);
  });

  $all('[data-media-view]').forEach(btn => {
    btn.onclick = () => viewMedia(btn.dataset.mediaView);
  });

  // DD toggle
  const ddLabel = $('#dd-toggle-label');
  const ddCheck = $('#editor-dd');
  if (ddLabel && ddCheck) {
    ddLabel.onclick = (e) => {
      e.preventDefault();
      ddCheck.checked = !ddCheck.checked;
      ddCheck.dispatchEvent(new Event('change'));
    };
    ddLabel.onkeydown = (e) => {
      if (e.key !== ' ' && e.key !== 'Enter') return;
      e.preventDefault();
      ddCheck.checked = !ddCheck.checked;
      ddCheck.dispatchEvent(new Event('change'));
    };
    ddCheck.onchange = () => {
      ddLabel.classList.toggle('active', ddCheck.checked);
      ddLabel.setAttribute('aria-checked', ddCheck.checked ? 'true' : 'false');
      updateField('dd', ddCheck.checked);
      refreshBoardCells();
    };
  }

  // Text fields
  bind('#editor-category',  'oninput', e => updateField('category',    e.target.value));
  bind('#editor-text',      'oninput', e => { updateField('text', e.target.value); refreshBoardCells(); });
  bind('#editor-answer',    'oninput', e => updateField('answer',      e.target.value));
  bind('#editor-value',     'oninput', e => updateField('value',       Number(e.target.value)));
  bind('#editor-image-url', 'oninput', e => updateField('image_link',  e.target.value || null));
  bind('#editor-audio-url', 'oninput', e => updateField('audio_link',  e.target.value || null));
  bind('#editor-video-url', 'oninput', e => updateField('video_link',  e.target.value || null));
  bind('#editor-image-url', 'onchange', e => { updateField('image_link',  e.target.value || null); state.mediaOpen = true; render(); });
  bind('#editor-audio-url', 'onchange', e => { updateField('audio_link',  e.target.value || null); state.mediaOpen = true; render(); });
  bind('#editor-video-url', 'onchange', e => { updateField('video_link',  e.target.value || null); state.mediaOpen = true; render(); });
  bind('#editor-image-file','onchange',e => { setFile('image_file', e.target.files[0]); state.mediaOpen = true; render(); });
  bind('#editor-audio-file','onchange',e => { setFile('audio_file', e.target.files[0]); state.mediaOpen = true; render(); });
  bind('#editor-video-file','onchange',e => { setFile('video_file', e.target.files[0]); state.mediaOpen = true; render(); });
}

function bind(selector, event, handler) {
  const el = $(selector);
  if (el) el[event] = handler;
}

function refreshBoardCells() {
  // Refresh clue cells without a full re-render
  const activeRound = getActiveRound();
  if (!activeRound?.questions) return;
  document.querySelectorAll('.clue-cell').forEach(cell => {
    const qi = Number(cell.dataset.qindex);
    const q = activeRound.questions[qi];
    if (!q) return;
    cell.classList.toggle('selected', qi === state.selectedQuestionIndex);
    cell.classList.toggle('filled',   !!q.text?.trim());
    cell.classList.toggle('has-dd',   !!q.dd);
    cell.classList.toggle('has-media', !!getMediaCount(q));
    const prev = cell.querySelector('.clue-preview');
    if (prev) prev.textContent = q.text?.slice(0, 50) || '';
    let badge = cell.querySelector('.media-badge');
    if (getMediaCount(q) && !badge) {
      badge = document.createElement('span');
      badge.className = 'media-badge';
      badge.textContent = 'MEDIA';
      cell.appendChild(badge);
    } else if (!getMediaCount(q) && badge) {
      badge.remove();
    }
  });
  updateProgress();
}

function escHtml(str) {
  return String(str || '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function openMediaModal({ type, title, url, revokeUrl = null }) {
  const modal = $('#media-modal');
  const body = $('#media-modal-body');
  const titleEl = $('#media-modal-title');
  const kicker = $('#media-modal-kicker');
  if (!modal || !body || !titleEl || !kicker) return;

  closeMediaModal();
  modal.dataset.revokeUrl = revokeUrl || '';
  titleEl.textContent = title || 'Preview';
  kicker.textContent = `${type.charAt(0).toUpperCase()}${type.slice(1)} Preview`;

  if (type === 'image') {
    body.innerHTML = `<img class="media-modal-asset" src="${escHtml(url)}" alt="">`;
  } else if (type === 'audio') {
    body.innerHTML = `<audio class="media-modal-asset" src="${escHtml(url)}" controls autoplay></audio>`;
  } else if (type === 'video') {
    const youtubeUrl = getYoutubeEmbedUrl(url);
    body.innerHTML = youtubeUrl
      ? `<iframe class="media-modal-asset" src="${escHtml(youtubeUrl)}" title="Video preview" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>`
      : `<video class="media-modal-asset" src="${escHtml(url)}" controls autoplay></video>`;
  } else {
    body.innerHTML = `<a class="media-modal-link" href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(url)}</a>`;
  }

  modal.classList.add('open');
  modal.setAttribute('aria-hidden', 'false');
}

function closeMediaModal() {
  const modal = $('#media-modal');
  const body = $('#media-modal-body');
  if (!modal || !body) return;
  const revokeUrl = modal.dataset.revokeUrl;
  body.innerHTML = '';
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden', 'true');
  if (revokeUrl) URL.revokeObjectURL(revokeUrl);
  modal.dataset.revokeUrl = '';
}

/* ─── Export Data ──────────────────────────────────────────── */
function buildExportData() {
  const rounds = state.game.rounds.map(r => {
    if (r.type === 'final') {
      const q = r.question;
      return {
        type: 'final',
        question: {
          index: q.index, text: q.text, answer: q.answer, category: q.category,
          value: q.value, image_link: q.image_link, audio_link: q.audio_link,
          video_link: q.video_link, includes_audio: q.includes_audio,
        },
      };
    }
    return {
      type: r.type,
      categories: r.categories,
      questions: r.questions.map(q => ({
        index: q.index, text: q.text, answer: q.answer, category: q.category,
        value: q.value, dd: q.dd,
        image_link: q.image_link, audio_link: q.audio_link, video_link: q.video_link,
        includes_audio: q.includes_audio,
      })),
    };
  });
  return {
    rounds,
    date:     $('#game-date')?.value     || state.game.date,
    title:    $('#game-title')?.value    || state.game.title,
    comments: $('#game-comments')?.value || state.game.comments,
  };
}

/* ─── Export: ZIP ──────────────────────────────────────────── */
function downloadZIP() {
  const zip = new JSZip();
  const used = new Set();

  function uniqueName(file, type) {
    const fallbackExt = { image: 'bin', audio: 'mp3', video: 'mp4' }[type] || 'bin';
    const fileName = file.name || `${type}.${fallbackExt}`;
    const dotIndex = fileName.lastIndexOf('.');
    const base = dotIndex > 0 ? fileName.slice(0, dotIndex) : fileName;
    const ext = dotIndex > 0 ? fileName.slice(dotIndex + 1) : fallbackExt;
    let name = `media/${base}.${ext}`;
    let i = 1;
    while (used.has(name)) {
      name = `media/${base}_${i}.${ext}`;
      i++;
    }
    used.add(name);
    return name;
  }

  function processQuestion(sourceQuestion, exportQuestion) {
    ['image','audio','video'].forEach(type => {
      const f = sourceQuestion[`${type}_file`];
      if (f) {
        const name = uniqueName(f, type);
        zip.file(name, f);
        exportQuestion[`${type}_link`] = name;
        if (type === 'audio') exportQuestion.includes_audio = true;
      }
    });
  }

  const exportData = buildExportData();

  state.game.rounds.forEach((round, roundIndex) => {
    const exportRound = exportData.rounds[roundIndex];
    if (round.type === 'final') {
      processQuestion(round.question, exportRound.question);
    } else {
      round.questions.forEach((q, questionIndex) => {
        processQuestion(q, exportRound.questions[questionIndex]);
      });
    }
  });

  zip.file('game.json', JSON.stringify(exportData, null, 2));
  zip.generateAsync({ type: 'blob' }).then(content => saveAs(content, 'jparty-game.zip'));
}

/* ─── Meta Fields ──────────────────────────────────────────── */
function bindMetaFields() {
  const title    = $('#game-title');
  const date     = $('#game-date');
  const comments = $('#game-comments');

  if (title)    title.oninput    = () => { state.game.title    = title.value;    scheduleSave(); };
  if (date)     date.oninput     = () => { state.game.date     = date.value;     scheduleSave(); };
  if (comments) comments.oninput = () => { state.game.comments = comments.value; scheduleSave(); };
}

/* ─── Round Tabs ───────────────────────────────────────────── */
function bindTabs() {
  $all('.round-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      state.selectedRound = tab.dataset.round;
      state.selectedQuestionIndex = 0;
      state.mediaOpen = false;
      $all('.round-tab').forEach(t => t.classList.toggle('active', t === tab));
      render();
    });
  });
}

function bindMediaModal() {
  $all('[data-media-modal-close]').forEach(el => {
    el.addEventListener('click', closeMediaModal);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeMediaModal();
  });
}

/* ─── Init ─────────────────────────────────────────────────── */
async function init() {
  await loadFromStorage();
  initializeQuestions();

  // Sync active tab
  $all('.round-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.round === state.selectedRound);
  });

  // Populate meta fields
  const titleEl = $('#game-title');
  const dateEl  = $('#game-date');
  const commEl  = $('#game-comments');
  if (titleEl) titleEl.value = state.game.title;
  if (dateEl)  dateEl.value  = state.game.date;
  if (commEl)  commEl.value  = state.game.comments;

  bindMetaFields();
  bindTabs();
  bindMediaModal();

  $('#download-zip')?.addEventListener('click',  downloadZIP);

  render();
}

window.addEventListener('DOMContentLoaded', init);
