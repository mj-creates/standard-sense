/**
 * StandardSense — SIH 2026
 * app.js — Full-stack integration layer
 *
 * Sections:
 *   A. Configuration
 *   B. Application state
 *   C. Role / login UI
 *   D. Dropzone (drag-drop + file-input)
 *   E. Fetch bridge — POST /process-tender
 *   F. Pipeline tracker animation
 *   G. DOM rendering engine (extraction summary + compliance cards)
 *   H. Utility helpers
 *   I. Keyboard accessibility + DOMContentLoaded boot
 */

// ═══════════════════════════════════════════════════════════════════════════
// A. CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Base URL of the FastAPI backend.
 * Change this to your deployed URL before going to production.
 * No trailing slash.
 */
const API_BASE = 'http://localhost:8000';
const PROCESS_TENDER_ENDPOINT = `${API_BASE}/process-tender`;
const AUTO_FIX_ENDPOINT = `${API_BASE}/auto-fix`;

// ═══════════════════════════════════════════════════════════════════════════
// B. APPLICATION STATE
// ═══════════════════════════════════════════════════════════════════════════

let selectedRole  = 'officer';   // 'officer' | 'vendor'
let selectedFile  = null;        // File object currently staged for upload
let isProcessing  = false;       // True while a fetch is in-flight
let currentTenderData = null;    // Stores the last successful analysis result

const ROLE_CONFIG = {
  officer: {
    label:       'GeM Nodal Officer',
    email:       'officer@nic.in',
    description: 'Access tender management, compliance reports & BIS standard mappings.',
    initials:    'NO',
    bannerTitle: 'GeM Nodal Officer Portal',
    welcome:     'Welcome to the GeM Nodal Officer Portal',
  },
  vendor: {
    label:       'MSME / OEM Vendor',
    email:       'vendor@msme.gov.in',
    description: 'Upload product specs, check BIS compliance status & manage certifications.',
    initials:    'MV',
    bannerTitle: 'MSME / OEM Vendor Portal',
    welcome:     'Welcome to the MSME / OEM Vendor Portal',
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// C. ROLE / LOGIN UI
// ═══════════════════════════════════════════════════════════════════════════

function selectTab(role) {
  selectedRole = role;
  const config     = ROLE_CONFIG[role];
  const tabOfficer = document.getElementById('tab-officer');
  const tabVendor  = document.getElementById('tab-vendor');
  const emailInput = document.getElementById('email-input');
  const roleDesc   = document.getElementById('role-description');

  const ACTIVE   = 'tab-active flex-1 py-3.5 px-4 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2';
  const INACTIVE = 'tab-inactive flex-1 py-3.5 px-4 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2';

  tabOfficer.className = role === 'officer' ? ACTIVE : INACTIVE;
  tabVendor.className  = role === 'vendor'  ? ACTIVE : INACTIVE;

  if (emailInput) emailInput.value = config.email;
  if (roleDesc)   roleDesc.textContent = config.description;
}

function handleLogin(event) {
  event.preventDefault();
  const config      = ROLE_CONFIG[selectedRole];
  const loginPage   = document.getElementById('login-page');
  const dashPage    = document.getElementById('dashboard-page');
  const dashTitle   = document.getElementById('dashboard-title');
  const bannerTitle = document.getElementById('banner-title');
  const avatarEl    = document.getElementById('avatar-initials');
  const subtitleEl  = document.getElementById('dashboard-subtitle');
  const emailInput  = document.getElementById('email-input');

  const submitBtn = event.target.closest('button') || event.target.querySelector('button[type="submit"]');
  if (submitBtn) {
    const orig = submitBtn.innerHTML;
    submitBtn.innerHTML = `
      <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Authenticating…`;
    submitBtn.disabled = true;
    setTimeout(() => {
      submitBtn.innerHTML = orig;
      submitBtn.disabled  = false;
      _showDashboard(config, loginPage, dashPage, dashTitle, bannerTitle, avatarEl, subtitleEl, emailInput);
    }, 900);
    return;
  }
  _showDashboard(config, loginPage, dashPage, dashTitle, bannerTitle, avatarEl, subtitleEl, emailInput);
}

function _showDashboard(config, loginPage, dashPage, dashTitle, bannerTitle, avatarEl, subtitleEl, emailInput) {
  if (dashTitle)   dashTitle.textContent   = config.welcome;
  if (bannerTitle) bannerTitle.textContent = config.bannerTitle;
  if (avatarEl)    avatarEl.textContent    = config.initials;
  if (subtitleEl)  subtitleEl.textContent  = `${emailInput ? emailInput.value : config.email}  ·  Session active`;

  loginPage.classList.add('hidden');
  loginPage.classList.remove('flex');
  dashPage.classList.remove('hidden');
  dashPage.classList.add('flex');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function handleLogout() {
  const loginPage = document.getElementById('login-page');
  const dashPage  = document.getElementById('dashboard-page');

  // Reset upload state when logging out
  clearFile();
  _resetResults();

  dashPage.classList.add('hidden');
  dashPage.classList.remove('flex');
  loginPage.classList.remove('hidden');
  loginPage.classList.add('flex');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function togglePassword() {
  const pwInput = document.getElementById('password-input');
  const eyeIcon = document.getElementById('eye-icon');
  if (!pwInput) return;
  if (pwInput.type === 'password') {
    pwInput.type = 'text';
    eyeIcon.innerHTML = `
      <path stroke-linecap="round" stroke-linejoin="round"
        d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7
           a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878
           l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59
           3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025
           10.025 0 01-4.132 5.411m0 0L21 21"/>`;
  } else {
    pwInput.type = 'password';
    eyeIcon.innerHTML = `
      <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
      <path stroke-linecap="round" stroke-linejoin="round"
        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943
           9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// D. DROPZONE
// ═══════════════════════════════════════════════════════════════════════════

function _initDropzone() {
  const dz        = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  if (!dz || !fileInput) return;

  // Drag events on the dropzone div
  dz.addEventListener('dragover', (e) => {
    e.preventDefault();
    dz.classList.add('drag-over');
  });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('drag-over');
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) _handleFileSelection(files[0]);
  });

  // Native file picker
  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files.length > 0) {
      _handleFileSelection(fileInput.files[0]);
    }
  });
}

/**
 * Validate and stage a file for upload.
 * @param {File} file
 */
function _handleFileSelection(file) {
  _hideError();

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    _showError('Only PDF files are supported. Please select a .pdf file.');
    return;
  }

  const MAX_MB = 20;
  if (file.size > MAX_MB * 1024 * 1024) {
    _showError(`File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum allowed size is ${MAX_MB} MB.`);
    return;
  }

  selectedFile = file;

  // Update dropzone UI to "file selected" state
  const dz       = document.getElementById('dropzone');
  const chip     = document.getElementById('dz-file-chip');
  const fname    = document.getElementById('dz-filename');
  const primary  = document.getElementById('dz-primary');
  const secondary = document.getElementById('dz-secondary');

  dz.classList.add('file-selected');
  primary.textContent  = 'File ready for analysis';
  secondary.textContent = 'Click "Analyse Tender" to start, or drop a different file to replace.';
  fname.textContent    = file.name;
  chip.classList.remove('hidden');
  chip.classList.add('flex');

  // Enable the analyse button
  const btn = document.getElementById('analyse-btn');
  if (btn) {
    btn.disabled = false;
    btn.classList.remove('opacity-40', 'cursor-not-allowed');
  }
}

/**
 * Clear the currently staged file and reset the dropzone.
 * @param {Event} [event]  — if called from the ✕ button, stop propagation
 */
function clearFile(event) {
  if (event) event.stopPropagation();

  selectedFile = null;

  const dz        = document.getElementById('dropzone');
  const chip      = document.getElementById('dz-file-chip');
  const primary   = document.getElementById('dz-primary');
  const secondary = document.getElementById('dz-secondary');
  const fileInput = document.getElementById('file-input');

  if (dz) {
    dz.classList.remove('file-selected', 'drag-over');
  }
  if (primary)   primary.textContent   = 'Drag & drop your tender PDF here';
  if (secondary) secondary.innerHTML   = 'or <span class="text-blue-600 underline cursor-pointer">click to browse</span> — max 20 MB';
  if (chip) {
    chip.classList.add('hidden');
    chip.classList.remove('flex');
  }
  if (fileInput) fileInput.value = '';

  // Disable analyse button
  const btn = document.getElementById('analyse-btn');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('opacity-40', 'cursor-not-allowed');
  }

  _hideError();
}

// ═══════════════════════════════════════════════════════════════════════════
// E. FETCH BRIDGE — POST /process-tender
// ═══════════════════════════════════════════════════════════════════════════

async function submitTender() {
  if (!selectedFile || isProcessing) return;
  isProcessing = true;

  _hideError();
  _resetResults();
  _showPipelineTracker();
  _setAnalyseButtonLoading(true);

  // Animate step 1 (NLP) as active immediately — the backend will be doing
  // NLP extraction while the HTTP round-trip is happening.
  _setStep('nlp', 'active');
  _setPipelineStatus('Extracting specifications from PDF…');

  // Build multipart/form-data payload
  // Field name MUST be "file" — matches `file: UploadFile = File(...)` in main.py
  const formData = new FormData();
  formData.append('file', selectedFile, selectedFile.name);

  // Staggered step animations while we wait for the (slow) pipeline
  // NLP → ~1s → Semantic → ~2s → Rank → ~3s → RAG → response
  const stepTimers = [
    setTimeout(() => { _setStep('nlp', 'done'); _setStep('search', 'active'); _setPipelineStatus('Running FAISS semantic search…'); },      1200),
    setTimeout(() => { _setStep('search', 'done'); _setStep('rank', 'active'); _setPipelineStatus('Evaluating BIS compliance…'); },           3000),
    setTimeout(() => { _setStep('rank', 'done'); _setStep('rag', 'active'); _setPipelineStatus('Generating Groq RAG explanations…'); },       5000),
  ];

  let data;
  try {
    const response = await fetch(PROCESS_TENDER_ENDPOINT, {
      method:  'POST',
      body:    formData,
      // NOTE: Do NOT set credentials:'include' — backend uses allow_origins=["*"]
      //       with allow_credentials=True which is a server misconfiguration;
      //       credentialed requests to wildcard origins are rejected by browsers.
    });

    // Flush any pending step timers — we have a real result now
    stepTimers.forEach(clearTimeout);

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const errBody = await response.json();
        detail = errBody.detail || detail;
      } catch (_) { /* non-JSON error body */ }
      throw new Error(detail);
    }

    data = await response.json();

  } catch (err) {
    stepTimers.forEach(clearTimeout);
    _hidePipelineTracker();
    _setAnalyseButtonLoading(false);
    isProcessing = false;

    const msg = err.message.includes('Failed to fetch')
      ? `Could not connect to the backend at ${PROCESS_TENDER_ENDPOINT}. Make sure the FastAPI server is running:\n\nvenv\\Scripts\\uvicorn backend.app.main:app --reload --port 8000`
      : err.message;
    _showError(msg);
    return;
  }

  // ── All pipeline steps complete ──
  _setStep('rag', 'done');
  _setPipelineStatus('Analysis complete.');
  _setAnalyseButtonLoading(false);
  isProcessing = false;

  // Small pause so the user sees "Analysis complete." before results appear
  await _sleep(400);
  _hidePipelineTracker();
  _renderResults(data);
}

// ═══════════════════════════════════════════════════════════════════════════
// F. PIPELINE TRACKER ANIMATION
// ═══════════════════════════════════════════════════════════════════════════

const STEP_IDS = { nlp: 'step-nlp', search: 'step-search', rank: 'step-rank', rag: 'step-rag' };

function _showPipelineTracker() {
  const tracker = document.getElementById('pipeline-tracker');
  const empty   = document.getElementById('empty-state');
  if (tracker) tracker.classList.remove('hidden');
  if (empty)   empty.classList.add('hidden');
  // Reset all steps
  Object.values(STEP_IDS).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.className = el.className.replace(/\bactive\b|\bdone\b/g, '').trim() + ' pipeline-step';
  });
}

function _hidePipelineTracker() {
  const tracker = document.getElementById('pipeline-tracker');
  if (tracker) tracker.classList.add('hidden');
}

/**
 * @param {'nlp'|'search'|'rank'|'rag'} step
 * @param {'active'|'done'} state
 */
function _setStep(step, state) {
  const el = document.getElementById(STEP_IDS[step]);
  if (!el) return;
  // Remove both possible state classes, then add the new one
  el.classList.remove('active', 'done');
  el.classList.add(state);
}

function _setPipelineStatus(text) {
  const el = document.getElementById('pipeline-status-text');
  if (el) el.textContent = text;
}

function _setAnalyseButtonLoading(loading) {
  const btn = document.getElementById('analyse-btn');
  if (!btn) return;
  if (loading) {
    btn.innerHTML = `
      <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Analysing…`;
    btn.disabled = true;
    btn.classList.add('opacity-70', 'cursor-not-allowed');
  } else {
    btn.innerHTML = `
      <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
      </svg>
      Analyse Tender`;
    btn.disabled = false;
    btn.classList.remove('opacity-40', 'opacity-70', 'cursor-not-allowed');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// G. DOM RENDERING ENGINE
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Main render entry-point. Dispatches to extraction summary + results cards.
 * @param {Object} data — full response from POST /process-tender
 */
function _renderResults(data) {
  if (!data || (data.status !== 'ok' && data.status !== 'needs_clarification' && data.status !== 'out_of_scope')) {
    _showError('Unexpected response from server. Check the browser console for details.');
    console.error('[StandardSense] Unexpected API response:', data);
    return;
  }

  currentTenderData = data;

  if (data.status === 'out_of_scope') {
    const section = document.getElementById('results-section');
    const panel = document.getElementById('clarification-panel');
    const cards = document.getElementById('results-cards');
    if (section) section.classList.remove('hidden');
    if (cards) cards.innerHTML = '';

    // Hide standard features
    document.getElementById('compliance-summary-chart')?.classList.add('hidden');
    document.getElementById('results-summary-badges')?.classList.add('hidden');
    document.getElementById('empty-state')?.classList.add('hidden');

    // Show out of scope message in the clarification panel style or similar
    if (panel) {
      panel.classList.remove('hidden');
      const q = document.getElementById('clarification-question');
      if (q) q.textContent = data.message;
    }
    return;
  }

  if (data.status === 'needs_clarification') {
    const section = document.getElementById('results-section');
    const panel = document.getElementById('clarification-panel');
    const q     = document.getElementById('clarification-question');
    if (section) section.classList.remove('hidden');
    if (panel) panel.classList.remove('hidden');
    if (q)     q.textContent = data.question || 'Could you clarify the product category or intended use?';

    // Hide standard features
    document.getElementById('compliance-summary-chart')?.classList.add('hidden');
    document.getElementById('results-summary-badges')?.classList.add('hidden');
    document.getElementById('results-cards')?.classList.add('hidden');
    document.getElementById('empty-state')?.classList.add('hidden');
    return;
  }

  _renderExtractionSummary(data.extraction);

  const chart = document.getElementById('compliance-summary-chart');
  if (selectedRole === 'vendor') {
    if (chart) chart.classList.add('hidden');
    _renderVendorResults(data.rag, data.ranking);
  } else {
    if (chart) chart.classList.remove('hidden');
    _renderComplianceResults(data.rag, data.ranking);
  }
}

// ── G1. Extraction Summary Panel ────────────────────────────────────────────

function _renderExtractionSummary(extraction) {
  if (!extraction) return;

  const panel = document.getElementById('extraction-summary');
  if (!panel) return;
  panel.classList.remove('hidden');

  // spec_id badge
  _setText('spec-id-badge', extraction.spec_id || '');

  // Multilingual badge
  const meta   = extraction.multilingual_meta || {};
  const badge  = document.getElementById('lang-badge');
  const badgeText = document.getElementById('lang-badge-text');
  if (badge) {
    if (meta.was_translated && meta.original_language && meta.original_language !== 'English') {
      badge.classList.remove('hidden');
      if (badgeText) badgeText.textContent = `Translated from ${meta.original_language}`;
    } else {
      badge.classList.add('hidden');
    }
  }

  // Product
  _setText('ext-product', extraction.product || '—');

  // Spec text
  _setText('ext-spec-text', extraction.spec_text || '—');

  // Parameters chips
  const paramsEl = document.getElementById('ext-params');
  if (paramsEl) {
    paramsEl.innerHTML = '';
    const params = extraction.parameters || {};
    const entries = Object.entries(params);
    if (entries.length === 0) {
      paramsEl.innerHTML = '<span class="text-slate-400 text-xs">No parameters extracted</span>';
    } else {
      entries.forEach(([key, val]) => {
        const chip = document.createElement('span');
        chip.className = 'inline-flex items-center gap-1 bg-slate-100 border border-slate-200 text-slate-700 text-xs font-medium px-2.5 py-1 rounded-full';
        chip.innerHTML = `<span class="text-slate-400 font-normal">${_escHtml(key.replace(/_/g,' '))}:</span> ${_escHtml(String(val))}`;
        paramsEl.appendChild(chip);
      });
    }
  }

  // Explicit IS standards
  const standards = extraction.explicit_standards || [];
  const stdRow    = document.getElementById('ext-standards-row');
  const stdEl     = document.getElementById('ext-standards');
  if (stdRow && stdEl) {
    if (standards.length > 0) {
      stdRow.classList.remove('hidden');
      stdEl.innerHTML = standards.map(s =>
        `<span class="inline-flex items-center bg-blue-50 border border-blue-200 text-blue-800 text-xs font-semibold px-2.5 py-1 rounded-full">${_escHtml(s)}</span>`
      ).join('');
    } else {
      stdRow.classList.add('hidden');
    }
  }
}

// ── G2. Compliance Results Cards ────────────────────────────────────────────

/**
 * @param {Object} rag     — {status, spec_id, explanations:[...]}
 * @param {Object} ranking — {spec_id, spec_text, recommendations:[...]}
 */
function _renderComplianceResults(rag, ranking) {
  const section = document.getElementById('results-section');
  const cards   = document.getElementById('results-cards');
  const badges  = document.getElementById('results-summary-badges');
  if (!section || !cards) return;

  // Handle needs_clarification passthrough
  if (rag && rag.status === 'needs_clarification') {
    const panel = document.getElementById('clarification-panel');
    const q     = document.getElementById('clarification-question');
    if (panel) panel.classList.remove('hidden');
    if (q)     q.textContent = rag.question || 'Could you clarify the product category or intended use?';
    section.classList.add('hidden');
    document.getElementById('empty-state')?.classList.add('hidden');
    return;
  }

  const explanations   = (rag && rag.explanations)              || [];
  const recommendations = (ranking && ranking.recommendations)  || [];

  // ── Feature 1: Compliance Summary Chart (uses ONLY ranking.recommendations) ──
  const totalRecs = recommendations.length;
  const totalEl   = document.getElementById('compliance-summary-total');
  const barsEl    = document.getElementById('compliance-summary-bars');

  if (totalEl) {
    totalEl.textContent = `${totalRecs} recommendation${totalRecs === 1 ? '' : 's'}`;
  }

  if (barsEl) {
    const validStatuses = new Set(['compliant', 'partial', 'non-compliant', 'unknown']);
    const chartCounts = {
      compliant: 0,
      partial: 0,
      'non-compliant': 0,
      unknown: 0,
    };

    recommendations.forEach(r => {
      const rawStatus = (r && r.compliance_status) ? String(r.compliance_status).trim().toLowerCase() : '';
      const status = validStatuses.has(rawStatus) ? rawStatus : 'unknown';
      chartCounts[status] = (chartCounts[status] || 0) + 1;
    });

    const statusConfigs = [
      { key: 'compliant',     label: 'Compliant',     color: 'bg-green-500' },
      { key: 'partial',       label: 'Partial',       color: 'bg-yellow-500' },
      { key: 'non-compliant', label: 'Non-compliant', color: 'bg-red-500' },
      { key: 'unknown',       label: 'Unknown',       color: 'bg-slate-400' },
    ];

    barsEl.innerHTML = statusConfigs.map(cfg => {
      const count = chartCounts[cfg.key] || 0;
      const pct = totalRecs > 0 ? (count / totalRecs) * 100 : 0;
      return `
        <div>
          <div class="flex items-center justify-between text-xs font-medium text-slate-700 mb-1">
            <span>${cfg.label}</span>
            <span class="font-semibold text-slate-800">${count}</span>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
            <div class="${cfg.color} h-2 rounded-full transition-all duration-300" style="width: ${pct}%;"></div>
          </div>
        </div>
      `;
    }).join('');
  }

  if (explanations.length === 0) {
    section.classList.add('hidden');
    document.getElementById('empty-state')?.classList.remove('hidden');
    return;
  }

  // Build summary badge counts
  const counts = { compliant: 0, partial: 0, unknown: 0, 'non-compliant': 0 };
  explanations.forEach(e => {
    const s = e.compliance_status || 'unknown';
    counts[s] = (counts[s] || 0) + 1;
  });

  if (badges) {
    badges.innerHTML = Object.entries(counts)
      .filter(([, n]) => n > 0)
      .map(([status, n]) =>
        `<span class="text-xs font-semibold px-2.5 py-1 rounded-full ${_badgeClass(status)}">${n} ${status}</span>`
      ).join('');
  }

  // Build a quick lookup: is_code → recommendation detail
  const recMap = {};
  recommendations.forEach(r => { recMap[r.is_code] = r; });

  const specText = (ranking && ranking.spec_text) || (currentTenderData && currentTenderData.ranking && currentTenderData.ranking.spec_text) || (currentTenderData && currentTenderData.extraction && currentTenderData.extraction.spec_text) || '';

  // Render cards
  cards.innerHTML = '';
  explanations.forEach((exp, idx) => {
    const rec    = recMap[exp.is_code] || {};
    const card   = _buildResultCard(exp, rec, idx, specText);
    cards.appendChild(card);
  });

  section.classList.remove('hidden');
  document.getElementById('empty-state')?.classList.add('hidden');
  document.getElementById('download-pdf-btn')?.classList.remove('hidden');
  document.getElementById('download-pdf-btn')?.classList.add('flex');

  // Smooth-scroll to first card
  setTimeout(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
}

/**
 * Build a single compliance result card DOM element.
 * @param {Object} exp      — explanation object from rag.explanations[]
 * @param {Object} rec      — matching recommendation from ranking.recommendations[]
 * @param {number} idx      — zero-based rank index
 * @param {string} specText — original tender specification text
 * @returns {HTMLElement}
 */
function _buildResultCard(exp, rec, idx, specText = '') {
  const status  = exp.compliance_status || 'unknown';
  const statusLower = String(status).toLowerCase().trim();
  const score   = typeof exp.semantic_score === 'number' ? exp.semantic_score.toFixed(4) : '—';
  const cardId  = `result-card-${idx}`;
  const bodyId  = `result-body-${idx}`;

  const card = document.createElement('div');
  card.id        = cardId;
  card.className = 'bg-white rounded-2xl shadow-card border border-slate-100 overflow-hidden';

  // ── Card header (always visible) ──────────────────────────────────────────
  const headerBg = {
    compliant:        'bg-green-50 border-b border-green-100',
    partial:          'bg-amber-50 border-b border-amber-100',
    'non-compliant':  'bg-red-50 border-b border-red-100',
    unknown:          'bg-slate-50 border-b border-slate-100',
  }[status] || 'bg-slate-50 border-b border-slate-100';

  const rankLabel = `#${idx + 1}`;

  // Compliance field chips
  const passed  = rec.passed_fields  || [];
  const failed  = rec.failed_fields  || [];
  const missing = rec.missing_fields || [];

  // Determine Auto-Fix eligibility: ONLY for 'partial' or 'non-compliant' with failed or missing fields
  const canAutoFix = (statusLower === 'partial' || statusLower === 'non-compliant') &&
                     (failed.length > 0 || missing.length > 0);

  const originalSpec = specText ||
                       (currentTenderData && currentTenderData.ranking && currentTenderData.ranking.spec_text) ||
                       (currentTenderData && currentTenderData.extraction && currentTenderData.extraction.spec_text) || '';

  const fieldChips = [
    ...passed.map(f  => `<span class="inline-flex items-center gap-1 bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded-full font-medium">✓ ${_escHtml(f)}</span>`),
    ...failed.map(f  => `<span class="inline-flex items-center gap-1 bg-red-100 text-red-800 text-xs px-2 py-0.5 rounded-full font-medium">✗ ${_escHtml(f)}</span>`),
    ...missing.map(f => `<span class="inline-flex items-center gap-1 bg-slate-100 text-slate-500 text-xs px-2 py-0.5 rounded-full font-medium">? ${_escHtml(f)}</span>`),
  ].join('');

  // Semantic score bar (0 = best match, higher = worse; clamp to 0-2 range)
  const scoreNum     = parseFloat(score) || 0;
  const scorePercent = Math.max(0, Math.min(100, Math.round((1 - scoreNum / 2) * 100)));
  const scoreColor   = scorePercent >= 70 ? 'bg-green-500' : scorePercent >= 40 ? 'bg-amber-400' : 'bg-red-400';

  // Build Auto-Fix markup only if eligible
  let autoFixHtml = '';
  if (canAutoFix) {
    const fieldSummary = [
      failed.length ? `${failed.length} failed` : '',
      missing.length ? `${missing.length} missing` : '',
    ].filter(Boolean).join(' and ');

    autoFixHtml = `
        <!-- Auto-Fix Section -->
        <div class="mt-4 pt-4 border-t border-slate-100" id="autofix-section-${idx}">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div>
              <span class="text-xs font-bold text-govnavy flex items-center gap-1.5">
                <svg class="w-3.5 h-3.5 text-govorange" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
                Specification Auto-Fix
              </span>
              <p class="text-[11px] text-slate-500 mt-0.5">Generate a standard-compliant draft addressing ${fieldSummary} field${(failed.length + missing.length) === 1 ? '' : 's'}.</p>
            </div>
            <button
              id="autofix-btn-${idx}"
              type="button"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-govnavy hover:bg-govnavy/90 text-white text-xs font-semibold rounded-lg shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-govorange disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <svg id="autofix-icon-${idx}" class="w-3.5 h-3.5 text-govorange flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/>
              </svg>
              <span id="autofix-btn-text-${idx}">Generate Compliant Version</span>
            </button>
          </div>
          <div id="autofix-error-${idx}" class="hidden mt-3 p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg"></div>
          <div id="autofix-result-${idx}" class="hidden mt-3"></div>
        </div>
    `;
  }

  card.innerHTML = `
    <!-- Card header -->
    <div class="${headerBg} px-5 py-4">
      <div class="flex items-start justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <span class="flex-shrink-0 w-7 h-7 rounded-full bg-govnavy text-white text-xs font-bold flex items-center justify-center">${_escHtml(rankLabel)}</span>
          <div class="min-w-0">
            <p class="text-govnavy font-bold text-sm leading-tight truncate">${_escHtml(exp.is_code || '—')}</p>
            <p class="text-slate-500 text-xs mt-0.5 leading-tight">${_escHtml(exp.title || '—')}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-xs font-bold px-2.5 py-1 rounded-full ${_badgeClass(status)}">${_escHtml(status)}</span>
          <button
            onclick="toggleCard('${bodyId}')"
            aria-expanded="false"
            aria-controls="${bodyId}"
            class="w-7 h-7 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-400 hover:text-govnavy hover:border-slate-300 transition-colors flex-shrink-0"
            title="Expand explanation"
          >
            <svg id="chevron-${idx}" class="w-3.5 h-3.5 transition-transform duration-300" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Semantic score row -->
      <div class="mt-3 flex items-center gap-3">
        <div class="flex-1 h-1.5 bg-white rounded-full overflow-hidden border border-slate-200">
          <div class="h-full ${scoreColor} rounded-full transition-all duration-500" style="width:${scorePercent}%"></div>
        </div>
        <span class="text-slate-400 text-xs font-mono flex-shrink-0">L2 ${_escHtml(score)}</span>
      </div>

      <!-- Field chips row -->
      ${fieldChips ? `<div class="mt-3 flex flex-wrap gap-1.5">${fieldChips}</div>` : ''}
    </div>

    <!-- Expandable explanation body -->
    <div id="${bodyId}" class="explanation-body">
      <div class="px-5 py-4">
        <p class="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-2.5 flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5 text-govorange" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
          </svg>
          Groq RAG Explanation
        </p>
        <div class="explanation-text text-slate-600 text-xs leading-relaxed whitespace-pre-wrap">${_formatExplanation(exp.explanation || '')}</div>
        ${autoFixHtml}
      </div>
    </div>
  `;

  // Attach event listener for Auto-Fix button if present
  if (canAutoFix) {
    const autoFixBtn = card.querySelector(`#autofix-btn-${idx}`);
    if (autoFixBtn) {
      autoFixBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        _handleAutoFix(idx, {
          spec_text: originalSpec,
          is_code: exp.is_code || '',
          title: exp.title || '',
          failed_fields: failed,
          missing_fields: missing,
        });
      });
    }
  }

  return card;
}

/**
 * Handle Auto-Fix button click to generate a compliant specification.
 * @param {number} idx
 * @param {Object} payload - { spec_text, is_code, title, failed_fields, missing_fields }
 */
async function _handleAutoFix(idx, payload) {
  const btn = document.getElementById(`autofix-btn-${idx}`);
  const btnText = document.getElementById(`autofix-btn-text-${idx}`);
  const btnIcon = document.getElementById(`autofix-icon-${idx}`);
  const errorEl = document.getElementById(`autofix-error-${idx}`);
  const bodyEl = document.getElementById(`result-body-${idx}`);

  if (!btn || btn.disabled) return;

  // Clear previous error
  if (errorEl) {
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
  }

  // Ensure original spec text is available
  const originalSpec = payload.spec_text ||
    (currentTenderData && currentTenderData.ranking && currentTenderData.ranking.spec_text) ||
    (currentTenderData && currentTenderData.extraction && currentTenderData.extraction.spec_text) || '';

  if (!originalSpec.trim()) {
    if (errorEl) {
      errorEl.textContent = 'Original specification text is not available. Please re-run the tender analysis.';
      errorEl.classList.remove('hidden');
    }
    return;
  }

  // Set loading state: disable button, show spinner & "Generating..."
  btn.disabled = true;
  if (btnText) btnText.textContent = 'Generating...';
  if (btnIcon) {
    btnIcon.outerHTML = `
      <svg id="autofix-icon-${idx}" class="animate-spin w-3.5 h-3.5 text-white flex-shrink-0" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
      </svg>
    `;
  }

  try {
    const response = await fetch(AUTO_FIX_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        spec_text: originalSpec,
        is_code: payload.is_code || '',
        title: payload.title || '',
        failed_fields: payload.failed_fields || [],
        missing_fields: payload.missing_fields || [],
      }),
    });

    if (!response.ok) {
      let message = 'Failed to generate compliant specification.';
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          message = errorData.detail;
        }
      } catch (_) {}
      throw new Error(message);
    }

    const data = await response.json();
    const correctedSpec = data.corrected_specification || '';

    if (!correctedSpec) {
      throw new Error('Auto-Fix returned an empty specification.');
    }

    // Render comparison result
    _renderAutoFixResult(idx, originalSpec, correctedSpec);

    // Re-enable button and allow regenerating
    btn.disabled = false;
    const currentBtnText = document.getElementById(`autofix-btn-text-${idx}`);
    const currentBtnIcon = document.getElementById(`autofix-icon-${idx}`);
    if (currentBtnText) currentBtnText.textContent = 'Regenerate Compliant Version';
    if (currentBtnIcon) {
      currentBtnIcon.outerHTML = `
        <svg id="autofix-icon-${idx}" class="w-3.5 h-3.5 text-govorange flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
      `;
    }
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = err.message || 'Auto-Fix request failed. Please try again.';
      errorEl.classList.remove('hidden');
    }
    btn.disabled = false;
    const currentBtnText = document.getElementById(`autofix-btn-text-${idx}`);
    const currentBtnIcon = document.getElementById(`autofix-icon-${idx}`);
    if (currentBtnText) currentBtnText.textContent = 'Generate Compliant Version';
    if (currentBtnIcon) {
      currentBtnIcon.outerHTML = `
        <svg id="autofix-icon-${idx}" class="w-3.5 h-3.5 text-govorange flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/>
        </svg>
      `;
    }
  }

  // Adjust card container height if expanded so that content is fully visible
  if (bodyEl && bodyEl.classList.contains('open')) {
    bodyEl.style.maxHeight = `${bodyEl.scrollHeight + 600}px`;
  }
}

/**
 * Render the Before/After comparison, disclaimer, and copy button for Auto-Fix.
 * @param {number} idx
 * @param {string} originalSpec
 * @param {string} correctedSpec
 */
function _renderAutoFixResult(idx, originalSpec, correctedSpec) {
  const resultEl = document.getElementById(`autofix-result-${idx}`);
  if (!resultEl) return;

  resultEl.innerHTML = `
    <div class="space-y-3 pt-2">
      <!-- Comparison Grid: side-by-side on desktop, stacked on mobile -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <!-- Original Specification -->
        <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 flex flex-col">
          <div class="flex items-center justify-between pb-2 mb-2 border-b border-slate-200">
            <span class="text-xs font-bold text-slate-700 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-slate-400 inline-block"></span>
              Original Specification
            </span>
          </div>
          <div class="text-xs text-slate-600 font-mono whitespace-pre-wrap leading-relaxed overflow-y-auto max-h-60 flex-1">${_escHtml(originalSpec)}</div>
        </div>

        <!-- Corrected Specification -->
        <div class="bg-emerald-50/40 border border-emerald-200 rounded-xl p-3 flex flex-col">
          <div class="flex items-center justify-between pb-2 mb-2 border-b border-emerald-200">
            <span class="text-xs font-bold text-emerald-900 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
              Corrected Specification
            </span>
            <button
              id="copy-autofix-btn-${idx}"
              type="button"
              class="inline-flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-emerald-50 text-emerald-800 text-xs font-semibold rounded-md border border-emerald-300 shadow-2xs transition-colors cursor-pointer"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
              </svg>
              <span id="copy-autofix-text-${idx}">Copy Corrected Text</span>
            </button>
          </div>
          <div class="text-xs text-emerald-950 font-mono whitespace-pre-wrap leading-relaxed overflow-y-auto max-h-60 flex-1">${_escHtml(correctedSpec)}</div>
        </div>
      </div>

      <!-- Exact Disclaimer -->
      <p class="text-[11px] text-slate-400 italic flex items-center gap-1">
        <svg class="w-3.5 h-3.5 flex-shrink-0 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
        AI-generated suggestion — please review before use.
      </p>
    </div>
  `;

  resultEl.classList.remove('hidden');

  // Attach copy event listener
  const copyBtn = document.getElementById(`copy-autofix-btn-${idx}`);
  const copyTextEl = document.getElementById(`copy-autofix-text-${idx}`);
  if (copyBtn && copyTextEl) {
    copyBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      _copyToClipboard(correctedSpec, copyTextEl);
    });
  }
}

/**
 * Copy text to clipboard with feedback and fallback.
 * @param {string} text
 * @param {HTMLElement} labelEl
 */
function _copyToClipboard(text, labelEl) {
  const showFeedback = () => {
    if (!labelEl) return;
    const oldText = labelEl.textContent;
    labelEl.textContent = 'Copied!';
    setTimeout(() => {
      labelEl.textContent = oldText;
    }, 2000);
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(showFeedback).catch(() => {
      _fallbackCopy(text);
      showFeedback();
    });
  } else {
    _fallbackCopy(text);
    showFeedback();
  }
}

function _fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.top = '0';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    document.execCommand('copy');
  } catch (_) {}
  document.body.removeChild(ta);
}

/**
 * Toggle expand/collapse on a result card's explanation body.
 * @param {string} bodyId
 */
function toggleCard(bodyId) {
  const body    = document.getElementById(bodyId);
  const idx     = bodyId.replace('result-body-', '');
  const chevron = document.getElementById(`chevron-${idx}`);
  if (!body) return;

  const isOpen = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  if (isOpen) {
    body.style.maxHeight = '';
  } else {
    // When expanding, accommodate any auto-fix result content
    body.style.maxHeight = `${Math.max(800, body.scrollHeight + 100)}px`;
  }
  if (chevron) {
    chevron.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
  }

  const btn = body.previousElementSibling?.querySelector(`button[aria-controls="${bodyId}"]`);
  if (btn) btn.setAttribute('aria-expanded', String(!isOpen));
}

// ── G3. Vendor View (Simplified) ────────────────────────────────────────────

function _renderVendorResults(rag, ranking) {
  const section = document.getElementById('results-section');
  const cards   = document.getElementById('results-cards');
  const badges  = document.getElementById('results-summary-badges');
  if (!section || !cards) return;

  // Handle needs_clarification passthrough
  if (rag && rag.status === 'needs_clarification') {
    const panel = document.getElementById('clarification-panel');
    const q     = document.getElementById('clarification-question');
    if (panel) panel.classList.remove('hidden');
    if (q)     q.textContent = rag.question || 'Could you clarify the product category or intended use?';
    section.classList.add('hidden');
    document.getElementById('empty-state')?.classList.add('hidden');
    return;
  }

  const explanations   = (rag && rag.explanations)              || [];
  const recommendations = (ranking && ranking.recommendations)  || [];

  if (explanations.length === 0) {
    section.classList.add('hidden');
    document.getElementById('empty-state')?.classList.remove('hidden');
    return;
  }

  if (badges) badges.innerHTML = ''; // Vendor view doesn't need summary badges

  const recMap = {};
  recommendations.forEach(r => { recMap[r.is_code] = r; });

  cards.innerHTML = '';
  explanations.forEach((exp, idx) => {
    const rec    = recMap[exp.is_code] || {};
    const card   = _buildVendorResultCard(exp, rec, idx);
    cards.appendChild(card);
  });

  section.classList.remove('hidden');
  document.getElementById('empty-state')?.classList.add('hidden');

  // Hide PDF download button for Vendor
  const pdfBtn = document.getElementById('download-pdf-btn');
  if (pdfBtn) {
    pdfBtn.classList.add('hidden');
    pdfBtn.classList.remove('flex');
  }

  // Smooth-scroll to first card
  setTimeout(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
}

function _buildVendorResultCard(exp, rec, idx) {
  const status  = exp.compliance_status || 'unknown';

  let verdictText = '⚠️ Needs Review';
  let verdictColor = 'text-amber-700 bg-amber-50 border-amber-200';
  let headerBg = 'bg-amber-50 border-b border-amber-100';

  if (status === 'compliant') {
    verdictText = '✅ Likely Compliant';
    verdictColor = 'text-green-700 bg-green-50 border-green-200';
    headerBg = 'bg-green-50 border-b border-green-100';
  } else if (status === 'non-compliant') {
    verdictText = '❌ Not Compliant';
    verdictColor = 'text-red-700 bg-red-50 border-red-200';
    headerBg = 'bg-red-50 border-b border-red-100';
  } else if (status === 'unknown') {
    verdictText = '⚠️ Needs Review';
    verdictColor = 'text-amber-700 bg-amber-50 border-amber-200';
    headerBg = 'bg-amber-50 border-b border-amber-100';
  }

  const failed  = rec.failed_fields  || [];
  const missing = rec.missing_fields || [];
  const allFixes = [...failed, ...missing];

  let fixSummary = 'All requirements appear to be met.';
  if (allFixes.length > 0) {
    const plainFields = allFixes.map(f => f.replace(/_/g, ' '));
    if (plainFields.length === 1) {
      fixSummary = `Please review and provide details for: ${plainFields[0]}`;
    } else if (plainFields.length === 2) {
      fixSummary = `Please review and provide details for: ${plainFields[0]} and ${plainFields[1]}`;
    } else {
      fixSummary = `Please review and provide details for: ${plainFields.slice(0, -1).join(', ')}, and ${plainFields[plainFields.length - 1]}`;
    }
  }

  const cardId  = `vendor-result-card-${idx}`;

  const card = document.createElement('div');
  card.id        = cardId;
  card.className = 'bg-white rounded-2xl shadow-card border border-slate-100 overflow-hidden mb-4';

  card.innerHTML = \`
    <div class="\${headerBg} px-5 py-4">
      <div class="flex items-start justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <div class="min-w-0">
            <p class="text-govnavy font-bold text-base leading-tight truncate">\${_escHtml(exp.title || '—')}</p>
            <p class="text-slate-500 text-xs mt-1 leading-tight">\${_escHtml(exp.is_code || '—')}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-sm font-bold px-3 py-1.5 rounded-full border \${verdictColor}">\${verdictText}</span>
        </div>
      </div>
      <div class="mt-4 p-3 bg-white/60 rounded-lg border border-white/40">
        <p class="text-slate-700 text-sm font-medium">💡 \${fixSummary}</p>
      </div>
    </div>
  \`;

  return card;
}

// ═══════════════════════════════════════════════════════════════════════════
// H. UTILITY HELPERS
// ═══════════════════════════════════════════════════════════════════════════

/** Map compliance status → CSS class string */
function _badgeClass(status) {
  return {
    compliant:        'badge-compliant',
    partial:          'badge-partial',
    'non-compliant':  'badge-non-compliant',
    unknown:          'badge-unknown',
  }[status] || 'badge-unknown';
}

/** Escape HTML special characters to prevent XSS from server text */
function _escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Lightly format the Groq explanation text:
 * - **bold** → <strong>
 * - *italic* → <em>
 * - Lines starting with "- " → list items
 * Escapes HTML first to prevent XSS.
 */
function _formatExplanation(text) {
  if (!text) return '';
  let safe = _escHtml(text);

  // **bold**
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // *italic*
  safe = safe.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Bullet list lines
  const lines = safe.split('\n');
  let inList = false;
  const result = [];
  for (const line of lines) {
    if (/^[-•]\s+/.test(line.trimStart())) {
      if (!inList) { result.push('<ul>'); inList = true; }
      result.push(`<li>${line.replace(/^[-•]\s+/, '').trim()}</li>`);
    } else {
      if (inList) { result.push('</ul>'); inList = false; }
      result.push(line);
    }
  }
  if (inList) result.push('</ul>');
  return result.join('\n');
}

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function _showError(message) {
  const banner = document.getElementById('upload-error');
  const text   = document.getElementById('upload-error-text');
  if (banner) banner.classList.remove('hidden');
  if (text)   text.textContent = message;
}

function _hideError() {
  document.getElementById('upload-error')?.classList.add('hidden');
}

function _resetResults() {
  currentTenderData = null;
  document.getElementById('extraction-summary')?.classList.add('hidden');
  document.getElementById('results-section')?.classList.add('hidden');
  document.getElementById('clarification-panel')?.classList.add('hidden');
  document.getElementById('empty-state')?.classList.remove('hidden');
  document.getElementById('download-pdf-btn')?.classList.add('hidden');
  document.getElementById('download-pdf-btn')?.classList.remove('flex');

  const cards = document.getElementById('results-cards');
  if (cards) cards.innerHTML = '';
  const badges = document.getElementById('results-summary-badges');
  if (badges) badges.innerHTML = '';
}

function _sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ═══════════════════════════════════════════════════════════════════════════
// I. PDF EXPORT
// ═══════════════════════════════════════════════════════════════════════════

function handleDownloadPdf() {
  if (currentTenderData) {
    _generatePdfReport(currentTenderData);
  }
}

function _generatePdfReport(data) {
  if (!window.jspdf || !window.jspdf.jsPDF) {
    _showError("PDF library failed to load.");
    return;
  }

  const doc = new window.jspdf.jsPDF();
  const extraction = data.extraction || {};
  const rag = data.rag || {};
  const ranking = data.ranking || {};

  const explanations = rag.explanations || [];
  const recommendations = ranking.recommendations || [];
  const recMap = {};
  recommendations.forEach(r => { recMap[r.is_code] = r; });

  let y = 20;
  const leftMargin = 15;
  const rightMargin = 195;
  const maxWidth = rightMargin - leftMargin;

  // Helper to add wrapped text and advance y
  function addText(text, x, startY, size, fontStyle = 'normal') {
    doc.setFont("helvetica", fontStyle);
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(text || '', maxWidth);

    // Check page break
    if (startY + (lines.length * size * 0.4) > 280) {
      doc.addPage();
      startY = 20;
    }

    doc.text(lines, x, startY);
    return startY + (lines.length * size * 0.4) + 5;
  }

  // Header
  doc.setTextColor(13, 33, 55); // govnavy
  y = addText("StandardSense Compliance Report", leftMargin, y, 18, 'bold');

  doc.setTextColor(100, 100, 100);
  const fileName = selectedFile ? selectedFile.name : (extraction.spec_id || "Report");
  const dateStr = new Date().toLocaleString();
  y = addText(`File: ${fileName} | Date: ${dateStr}`, leftMargin, y, 10, 'normal');
  y += 5;

  // Extracted Spec Summary
  doc.setTextColor(0, 0, 0);
  y = addText("Extracted Specification Summary", leftMargin, y, 14, 'bold');
  y = addText(`Product: ${extraction.product || 'N/A'}`, leftMargin, y, 11, 'normal');

  if (extraction.parameters) {
    const paramsText = Object.entries(extraction.parameters)
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
      .join(', ');
    if (paramsText) {
      y = addText(`Parameters: ${paramsText}`, leftMargin, y, 10, 'normal');
    }
  }
  y += 5;

  // Recommendations
  y = addText("BIS Standard Recommendations", leftMargin, y, 14, 'bold');
  y += 2;

  explanations.forEach((exp, idx) => {
    const rec = recMap[exp.is_code] || {};

    // Title
    doc.setTextColor(24, 61, 102); // slightly lighter navy
    y = addText(`#${idx + 1} - ${exp.is_code}: ${exp.title}`, leftMargin, y, 12, 'bold');

    doc.setTextColor(0, 0, 0);
    // Basic stats
    const status = exp.compliance_status || 'unknown';
    const score = typeof exp.semantic_score === 'number' ? exp.semantic_score.toFixed(4) : 'N/A';
    y = addText(`Status: ${status.toUpperCase()} | Semantic Score: ${score}`, leftMargin, y, 10, 'bold');

    // Fields
    const passed = (rec.passed_fields || []).join(', ') || 'none';
    const failed = (rec.failed_fields || []).join(', ') || 'none';
    const missing = (rec.missing_fields || []).join(', ') || 'none';

    y = addText(`Passed: ${passed}`, leftMargin, y, 10, 'normal');
    if (failed !== 'none') {
        doc.setTextColor(200, 0, 0);
        y = addText(`Failed: ${failed}`, leftMargin, y, 10, 'normal');
        doc.setTextColor(0, 0, 0);
    }
    if (missing !== 'none') {
        y = addText(`Missing: ${missing}`, leftMargin, y, 10, 'normal');
    }

    // Mandatory/Advisory (Task 5 data if present)
    const mandStatus = rec.is_mandatory_compliant !== undefined ? (rec.is_mandatory_compliant ? 'Yes' : 'No') : 'N/A';
    if (mandStatus !== 'N/A') {
       y = addText(`Mandatory Requirements Compliant: ${mandStatus}`, leftMargin, y, 10, 'italic');
    }

    // Explanation Summary (strip html, truncate)
    const rawExp = (exp.explanation || '').replace(/<[^>]*>?/gm, '').replace(/\*/g, '');
    const truncExp = rawExp;
    doc.setTextColor(80, 80, 80);
    y = addText(`Explanation: ${truncExp}`, leftMargin, y, 9, 'normal');

    y += 5; // spacing between cards
  });

  doc.save("compliance-report.pdf");
}

// ═══════════════════════════════════════════════════════════════════════════
// J. KEYBOARD ACCESSIBILITY + BOOT
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {

  // Show the API endpoint in the UI label
  const urlDisplay = document.getElementById('api-url-display');
  if (urlDisplay) urlDisplay.textContent = PROCESS_TENDER_ENDPOINT;

  // Role tabs — keyboard Enter/Space
  ['tab-officer', 'tab-vendor'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.setAttribute('role', 'tab');
    el.setAttribute('tabindex', '0');
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); }
    });
  });

  // Wire up dropzone
  _initDropzone();
});
