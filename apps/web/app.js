// State management
const state = {
  currentDocumentId: null,
  currentVersionId: null,
  activePreviewTab: 'translated', // 'translated' or 'source'
  documentIR: null,
  selectedNodeId: null,
  selection: null,
  mode: 'text',
  scale: 1.4,
  pdfDoc: null,
  edits: [],
  cursor: 0,
  versions: [],
  isTranslating: false,
};

// Elements
const uploadModal = document.getElementById('uploadModal');
const btnOpenUpload = document.getElementById('btnOpenUpload');
const btnCloseModal = document.getElementById('btnCloseModal');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');

const activeDocInfo = document.getElementById('activeDocInfo');
const docFilename = document.getElementById('docFilename');
const docBadge = document.getElementById('docBadge');
const pageCountBadge = document.getElementById('pageCountBadge');

const sourceLangSelect = document.getElementById('sourceLangSelect');
const targetLangSelect = document.getElementById('targetLangSelect');
const providerSelect = document.getElementById('providerSelect');
const btnTranslate = document.getElementById('btnTranslate');


const tabTranslated = document.getElementById('tabTranslated');
const tabSource = document.getElementById('tabSource');
const versionSelect = document.getElementById('versionSelect');
const btnDownloadPdf = document.getElementById('btnDownloadPdf');
const qaScoreBadge = document.getElementById('qaScoreBadge');

const previewPlaceholder = document.getElementById('previewPlaceholder');
const pdfViewerContainer = document.getElementById('pdfViewerContainer');
const previewLoading = document.getElementById('previewLoading');
const loadingMessage = document.getElementById('loadingMessage');

const copilotEmptyState = document.getElementById('copilotEmptyState');
const copilotActivePanel = document.getElementById('copilotActivePanel');
const selectionKind = document.getElementById('selectionKind');
const selectionPage = document.getElementById('selectionPage');
const selectionPreview = document.getElementById('selectionPreview');
const promptInput = document.getElementById('promptInput');
const btnApplyPromptEdit = document.getElementById('btnApplyPromptEdit');
const pdfPages = document.getElementById('pdfPages');
const editResult = document.getElementById('editResult');
const btnUndo = document.getElementById('btnUndo');
const btnRedo = document.getElementById('btnRedo');
const btnClearSelection = document.getElementById('btnClearSelection');
const modeText = document.getElementById('modeText');
const modeBox = document.getElementById('modeBox');
const zoomIn = document.getElementById('zoomIn');
const zoomOut = document.getElementById('zoomOut');
const zoomLabel = document.getElementById('zoomLabel');
const modeHint = document.getElementById('modeHint');
const costTotal = document.getElementById('costTotal');
const costDetail = document.getElementById('costDetail');
const editHistoryList = document.getElementById('editHistoryList');

// Event Listeners
btnOpenUpload.addEventListener('click', () => uploadModal.classList.add('active'));
btnCloseModal.addEventListener('click', () => uploadModal.classList.remove('active'));

dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    handleFileUpload(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files.length > 0) {
    handleFileUpload(e.target.files[0]);
  }
});

btnTranslate.addEventListener('click', handleTranslateDocument);
btnApplyPromptEdit.addEventListener('click', handleApplyPromptEdit);
btnClearSelection.addEventListener('click', clearSelection);
btnUndo.addEventListener('click', () => stepHistory(-1));
btnRedo.addEventListener('click', () => stepHistory(1));
function setZoom(scale) {
  state.scale = Math.min(3, Math.max(0.6, Math.round(scale * 100) / 100));
  zoomLabel.textContent = `${Math.round(state.scale / 1.4 * 100)}%`;
  if (state.pdfUrl) renderPdf(state.pdfUrl);
}
zoomIn.addEventListener('click', () => setZoom(state.scale + 0.2));
zoomOut.addEventListener('click', () => setZoom(state.scale - 0.2));
zoomLabel.addEventListener('click', () => setZoom(1.4));
pdfPages.addEventListener('wheel', (e) => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  setZoom(state.scale + (e.deltaY < 0 ? 0.1 : -0.1));
}, { passive: false });
modeText.addEventListener('click', () => setMode('text'));
modeBox.addEventListener('click', () => setMode('box'));
if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

// Functions
async function handleFileUpload(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    alert('Please upload a valid PDF file.');
    return;
  }

  uploadModal.classList.remove('active');
  showLoading('Uploading and classifying PDF...');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/v1/documents/upload', {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await res.json();
    state.currentDocumentId = data.document_id;
    state.versions = [];
    state.currentVersionId = null;
    state.selectedNodeId = null;
    state.edits = [];
    state.cursor = 0;
    costTotal.textContent = '$0.0000';
    costDetail.textContent = '';

    // Update Header UI
    activeDocInfo.classList.remove('hidden');
    docFilename.textContent = data.filename;
    docBadge.textContent = data.classification;
    pageCountBadge.textContent = `${data.total_pages} Page${data.total_pages > 1 ? 's' : ''}`;
    btnTranslate.disabled = false;

    // Reset right copilot panel
    copilotEmptyState.classList.remove('hidden');
    copilotActivePanel.classList.add('hidden');

    hideLoading();
    // Auto-trigger translation for seamless UX
    handleTranslateDocument();
  } catch (error) {
    hideLoading();
    alert(`Error: ${error.message}`);
  }
}

async function handleTranslateDocument() {
  if (!state.currentDocumentId) return;

  const targetLang = targetLangSelect.value;
  const sourceLang = sourceLangSelect.value === 'auto' ? null : sourceLangSelect.value;
  const provider = providerSelect.value || null;

  showLoading(`Translating document to ${targetLangSelect.options[targetLangSelect.selectedIndex].text}...`);
  btnTranslate.disabled = true;

  try {
    const res = await fetch(`/api/v1/documents/${state.currentDocumentId}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_language: targetLang,
        source_language: sourceLang,
        provider: provider,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Translation failed');
    }

    const data = await res.json();
    state.currentVersionId = data.version_id;
    state.versions.push({
      version_id: data.version_id,
      label: `v1.0 (Initial ${targetLang.toUpperCase()})`,
    });

    // Update Version Dropdown
    updateVersionDropdown();

    // Fetch and render Document IR Structure

    // Update Live PDF Preview
    await updatePdfPreview(data.download_url);

    // Update QA Badge
    qaScoreBadge.classList.remove('hidden');
    qaScoreBadge.textContent = `QA: ${Math.round(data.qa_score * 100)}%`;

    btnDownloadPdf.href = data.download_url;
    btnDownloadPdf.classList.remove('disabled');

    state.edits = [];
    state.cursor = 0;
    renderEditHistory();
    refreshCosts();
    hideLoading();
    btnTranslate.disabled = false;
  } catch (error) {
    hideLoading();
    btnTranslate.disabled = false;
    alert(`Translation Error: ${error.message}`);
  }
}

function setMode(mode) {
  state.mode = mode;
  modeText.classList.toggle('active', mode === 'text');
  modeBox.classList.toggle('active', mode === 'box');
  pdfViewerContainer.classList.toggle('draw-mode', mode === 'box');
  modeHint.textContent = mode === 'text'
    ? 'Highlight text on the page, then describe the change.'
    : 'Drag a rectangle over the area to change (whole paragraphs inside it are edited).';
}

async function renderPdf(url, flashPages = []) {
  if (!window.pdfjsLib) { alert('PDF.js failed to load.'); return; }
  state.pdfUrl = url;
  const scrollTop = pdfPages.scrollTop;
  const doc = await pdfjsLib.getDocument({ url: `${url}${url.includes('?') ? '&' : '?'}_t=${Date.now()}` }).promise;
  state.pdfDoc = doc;
  pdfPages.innerHTML = '';
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const viewport = page.getViewport({ scale: state.scale });
    const wrap = document.createElement('div');
    wrap.className = 'pdf-page';
    wrap.dataset.page = n;
    wrap.style.width = `${viewport.width}px`;
    wrap.style.height = `${viewport.height}px`;
    const canvas = document.createElement('canvas');
    const ratio = window.devicePixelRatio || 1;
    canvas.width = viewport.width * ratio;
    canvas.height = viewport.height * ratio;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    wrap.appendChild(canvas);
    await page.render({
      canvasContext: canvas.getContext('2d'),
      viewport,
      transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
    }).promise;
    const textDiv = document.createElement('div');
    textDiv.className = 'textLayer';
    wrap.appendChild(textDiv);
    const content = await page.getTextContent();
    pdfjsLib.renderTextLayer({ textContentSource: content, container: textDiv, viewport, textDivs: [] });
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    wrap.appendChild(overlay);
    attachBoxDrawing(overlay, wrap, n);
    if (flashPages.includes(n)) {
      const f = document.createElement('div');
      f.className = 'changed-flash';
      wrap.appendChild(f);
    }
    pdfPages.appendChild(wrap);
  }
  pdfPages.scrollTop = scrollTop;
  clearSelection();
  copilotActivePanel.classList.add('hidden');
  copilotEmptyState.classList.remove('hidden');
}

function attachBoxDrawing(overlay, wrap, pageNo) {
  let start = null;
  let rectEl = null;
  overlay.addEventListener('mousedown', (e) => {
    const r = wrap.getBoundingClientRect();
    start = { x: e.clientX - r.left, y: e.clientY - r.top };
    clearSelectionVisuals();
    rectEl = document.createElement('div');
    rectEl.className = 'sel-rect';
    overlay.appendChild(rectEl);
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!start || !rectEl || rectEl.parentNode !== overlay) return;
    const r = wrap.getBoundingClientRect();
    const x = Math.min(Math.max(e.clientX - r.left, 0), r.width);
    const y = Math.min(Math.max(e.clientY - r.top, 0), r.height);
    Object.assign(rectEl.style, {
      left: `${Math.min(start.x, x)}px`, top: `${Math.min(start.y, y)}px`,
      width: `${Math.abs(x - start.x)}px`, height: `${Math.abs(y - start.y)}px`,
    });
  });
  window.addEventListener('mouseup', (e) => {
    if (!start || !rectEl || rectEl.parentNode !== overlay) { start = null; return; }
    const r = wrap.getBoundingClientRect();
    const x = Math.min(Math.max(e.clientX - r.left, 0), r.width);
    const y = Math.min(Math.max(e.clientY - r.top, 0), r.height);
    const s = state.scale;
    const x0 = Math.min(start.x, x) / s, x1 = Math.max(start.x, x) / s;
    const y0 = Math.min(start.y, y) / s, y1 = Math.max(start.y, y) / s;
    start = null;
    if (x1 - x0 < 6 || y1 - y0 < 6) { rectEl.remove(); return; }
    setSelection({ kind: 'box', page: pageNo, rect: [x0, y0, x1, y1] }, `Area on page ${pageNo}`);
  });
}

function clearSelectionVisuals() {
  document.querySelectorAll('.sel-rect').forEach((el) => el.remove());
}

function clearSelection() {
  state.selection = null;
  clearSelectionVisuals();
  window.getSelection()?.removeAllRanges();
  copilotActivePanel.classList.add('hidden');
  copilotEmptyState.classList.remove('hidden');
}

function setSelection(sel, preview) {
  state.selection = sel;
  copilotEmptyState.classList.add('hidden');
  copilotActivePanel.classList.remove('hidden');
  selectionKind.textContent = sel.kind === 'box' ? 'BOX' : 'TEXT';
  selectionPage.textContent = `page ${sel.page}`;
  selectionPreview.textContent = preview;
  editResult.classList.add('hidden');
  promptInput.focus();
}

pdfPages.addEventListener('mouseup', () => {
  if (state.mode !== 'text') return;
  setTimeout(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
    const quote = sel.toString().replace(/\s+/g, ' ').trim();
    if (!quote) return;
    const range = sel.getRangeAt(0);
    const node = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
    let wrap = node.closest ? node.closest('.pdf-page') : null;
    if (!wrap) {
      const startEl = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
      wrap = startEl.closest('.pdf-page');
    }
    if (!wrap) return;
    const base = wrap.getBoundingClientRect();
    const s = state.scale;
    const rects = Array.from(range.getClientRects())
      .map((r) => [(r.left - base.left) / s, (r.top - base.top) / s, (r.right - base.left) / s, (r.bottom - base.top) / s])
      .filter((r) => r[2] - r[0] > 1 && r[3] - r[1] > 1);
    setSelection({ kind: 'text', page: parseInt(wrap.dataset.page, 10), quote, rects }, quote);
  }, 0);
});

function showEditResult(kind, html) {
  editResult.className = `edit-result ${kind}`;
  editResult.innerHTML = html;
}

function renderEditHistory() {
  editHistoryList.innerHTML = '';
  btnUndo.classList.toggle('hidden', state.cursor === 0);
  btnRedo.classList.toggle('hidden', state.cursor >= state.edits.length);
  if (state.edits.length === 0) {
    editHistoryList.innerHTML = '<div class="history-item empty">No edits yet</div>';
    return;
  }
  state.edits.forEach((h, idx) => {
    const item = document.createElement('div');
    item.className = 'history-item' + (idx >= state.cursor ? ' undone' : '');
    item.style.opacity = idx >= state.cursor ? '0.45' : '1';
    item.innerHTML = `<div style="font-weight:600;color:#93c5fd;margin-bottom:2px;">${idx + 1}. "${escapeHtml(h.instruction)}"${idx >= state.cursor ? ' (undone)' : ''}</div>
      <div style="color:#cbd5e1;">page ${h.pages.join(', ')}</div>`;
    editHistoryList.appendChild(item);
  });
}

async function handleApplyPromptEdit() {
  if (!state.currentDocumentId || !state.currentVersionId) return;
  if (!state.selection) { alert('Select text or draw a box on the PDF first.'); return; }
  const instruction = promptInput.value.trim();
  if (!instruction) { alert('Please describe the change you want.'); return; }

  showLoading('Checking the request and editing the selection...');
  btnApplyPromptEdit.disabled = true;
  try {
    const res = await fetch(`/api/v1/documents/${state.currentDocumentId}/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version_id: state.currentVersionId, instruction, selection: state.selection }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
    }
    const data = await res.json();
    refreshCosts();
    if (data.status === 'REJECTED') {
      showEditResult('rejected', `<div class="res-title">This can't be done</div>
        <div>${escapeHtml(data.reason || 'The request could not be fulfilled.')}</div>
        ${data.suggestion ? `<div class="res-sug">Try: ${escapeHtml(data.suggestion)}</div>` : ''}`);
      return;
    }
    const prev = state.currentVersionId;
    state.currentVersionId = data.version_id;
    state.edits = state.edits.slice(0, state.cursor);
    state.edits.push({ instruction, pages: data.changed_pages, parent: prev, version: data.version_id });
    state.cursor = state.edits.length;
    state.versions.push({ version_id: data.version_id, label: `v${state.versions.length + 1}.0 (Edit: ${instruction.slice(0, 24)})` });
    updateVersionDropdown(data.version_id);
    const url = `/api/v1/documents/${state.currentDocumentId}/versions/${data.version_id}/pdf`;
    btnDownloadPdf.href = url;
    await renderPdf(url, data.changed_pages);
    renderEditHistory();
    const c = data.changes[0];
    clearSelection();
    showEditResult('ok', `<div class="res-title">Edit applied (${data.changes.length} paragraph${data.changes.length > 1 ? 's' : ''})</div>
      ${c ? `<div class="res-diff"><del>${escapeHtml(c.before)}</del><br><ins>${escapeHtml(c.after)}</ins></div>` : ''}
      ${data.warnings.map((w) => `<div class="res-warn">${escapeHtml(w)}</div>`).join('')}`);
    copilotActivePanel.classList.remove('hidden');
    copilotEmptyState.classList.add('hidden');
    promptInput.value = '';
  } catch (error) {
    alert(`Edit Error: ${error.message}`);
  } finally {
    hideLoading();
    btnApplyPromptEdit.disabled = false;
  }
}

async function stepHistory(delta) {
  const next = state.cursor + delta;
  if (next < 0 || next > state.edits.length) return;
  const edit = delta < 0 ? state.edits[next] : state.edits[next - 1];
  const versionId = delta < 0 ? edit.parent : edit.version;
  state.cursor = next;
  state.currentVersionId = versionId;
  const url = `/api/v1/documents/${state.currentDocumentId}/versions/${versionId}/pdf`;
  updateVersionDropdown(versionId);
  btnDownloadPdf.href = url;
  showLoading(delta < 0 ? 'Undoing edit...' : 'Redoing edit...');
  await renderPdf(url, edit.pages);
  renderEditHistory();
  hideLoading();
}

async function refreshCosts() {
  if (!state.currentDocumentId) return;
  try {
    const r = await fetch(`/api/v1/documents/${state.currentDocumentId}/costs`);
    if (!r.ok) return;
    const c = await r.json();
    costTotal.textContent = `$${c.total_usd.toFixed(4)}`;
    costDetail.textContent = `translate $${c.translate_usd.toFixed(4)} · edits $${c.edit_usd.toFixed(4)}${c.has_estimates ? ' (est.)' : ''}`;
  } catch (e) { /* indicator is best effort */ }
}

function updateVersionDropdown(selectedId = null) {
  versionSelect.innerHTML = '';
  state.versions.forEach((v) => {
    const opt = document.createElement('option');
    opt.value = v.version_id;
    opt.textContent = v.label;
    if (selectedId && v.version_id === selectedId) {
      opt.selected = true;
    }
    versionSelect.appendChild(opt);
  });
}

async function switchVersion(versionId) {
  if (!versionId || !state.currentDocumentId) return;
  state.currentVersionId = versionId;
  const idx = state.edits.findIndex((e) => e.version === versionId);
  if (idx >= 0) state.cursor = idx + 1;
  else if (state.edits.length && state.edits[0].parent === versionId) state.cursor = 0;
  renderEditHistory();
  showLoading('Switching version...');
  
  const pdfUrl = `/api/v1/documents/${state.currentDocumentId}/versions/${versionId}/pdf`;
  updatePdfPreview(pdfUrl);
  btnDownloadPdf.href = pdfUrl;

  hideLoading();
}

function switchPreviewTab(tab) {
  state.activePreviewTab = tab;
  tabTranslated.classList.toggle('active', tab === 'translated');
  tabSource.classList.toggle('active', tab === 'source');

  if (!state.currentDocumentId) return;

  if (tab === 'translated' && state.currentVersionId) {
    const pdfUrl = `/api/v1/documents/${state.currentDocumentId}/versions/${state.currentVersionId}/pdf`;
    updatePdfPreview(pdfUrl);
  } else if (tab === 'source') {
    const pdfUrl = `/api/v1/documents/${state.currentDocumentId}/original/pdf`;
    updatePdfPreview(pdfUrl);
  }
}

function updatePdfPreview(url) {
  previewPlaceholder.classList.add('hidden');
  pdfViewerContainer.classList.remove('hidden');
  return renderPdf(url);
}


function showLoading(msg = 'Processing...') {
  loadingMessage.textContent = msg;
  previewLoading.classList.remove('hidden');
}

function hideLoading() {
  previewLoading.classList.add('hidden');
}

function setQuickPrompt(prompt) {
  promptInput.value = prompt;
  promptInput.focus();
}

// Generate sample PDF for instant demonstration
async function loadSampleDocument(type) {
  uploadModal.classList.remove('active');
  showLoading('Generating sample document...');

  // Create a synthetic PDF via server or fetch
  const samplePdfs = {
    financial: {
      title: 'Q3 Financial Performance Report',
      heading: 'Executive Summary & Operating Margins',
      para1: 'Revenue grew by 24.5% year-over-year reaching $18.4 million in Q3 2026.',
      para2: 'Operating expenses decreased by 8.2% to $12.1 million due to automation efficiencies.',
    },
    legal: {
      title: 'Mutual Non-Disclosure Agreement',
      heading: 'Section 4: Confidentiality Obligations',
      para1: 'The Recipient shall hold and maintain all Confidential Information in strictest confidence.',
      para2: 'This obligation shall remain in effect for a period of 5 (five) years from the effective date.',
    },
    technical: {
      title: 'Neural Machine Translation Whitepaper',
      heading: 'Abstract & Transformer Architecture',
      para1: 'We present a structure-preserving document transformation model preserving 100% of formatting markers.',
      para2: 'The system achieves state-of-the-art BLEU and chrF++ scores on low-resource Indic language benchmarks.',
    },
  };

  const sample = samplePdfs[type] || samplePdfs.financial;

  // Use PyMuPDF mock on backend or direct generation
  // We can create a simple PDF Blob using minimal PDF syntax
  const minimalPdf = generateMinimalPdf(sample);
  const file = new File([minimalPdf], `${type}_document.pdf`, { type: 'application/pdf' });
  await handleFileUpload(file);
}

function generateMinimalPdf(sample) {
  // Minimal standard PDF 1.4 binary template
  const textContent = `
BT
/F1 16 Tf
50 750 Td
(${sample.title}) Tj
0 -35 Td
/F1 13 Tf
(${sample.heading}) Tj
0 -30 Td
/F1 10 Tf
(${sample.para1}) Tj
0 -20 Td
(${sample.para2}) Tj
ET
`;

  const pdfTemplate = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length ${textContent.length} >>
stream
${textContent}
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000236 00000 n 
0000000307 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
${360 + textContent.length}
%%EOF`;

  return new Blob([pdfTemplate], { type: 'application/pdf' });
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
