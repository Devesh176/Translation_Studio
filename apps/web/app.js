// State management
const state = {
  currentDocumentId: null,
  currentVersionId: null,
  activePreviewTab: 'translated', // 'translated' or 'source'
  documentIR: null,
  selectedNodeId: null,
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

const structureEmptyState = document.getElementById('structureEmptyState');
const nodesList = document.getElementById('nodesList');
const nodeCountBadge = document.getElementById('nodeCountBadge');

const tabTranslated = document.getElementById('tabTranslated');
const tabSource = document.getElementById('tabSource');
const versionSelect = document.getElementById('versionSelect');
const btnDownloadPdf = document.getElementById('btnDownloadPdf');
const qaScoreBadge = document.getElementById('qaScoreBadge');

const previewPlaceholder = document.getElementById('previewPlaceholder');
const pdfViewerContainer = document.getElementById('pdfViewerContainer');
const pdfFrame = document.getElementById('pdfFrame');
const previewLoading = document.getElementById('previewLoading');
const loadingMessage = document.getElementById('loadingMessage');

const copilotEmptyState = document.getElementById('copilotEmptyState');
const copilotActivePanel = document.getElementById('copilotActivePanel');
const selectedNodeType = document.getElementById('selectedNodeType');
const selectedNodeId = document.getElementById('selectedNodeId');
const selectedSourceText = document.getElementById('selectedSourceText');
const selectedCurrentTranslation = document.getElementById('selectedCurrentTranslation');
const promptInput = document.getElementById('promptInput');
const btnApplyPromptEdit = document.getElementById('btnApplyPromptEdit');
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
    await loadDocumentStructure(state.currentDocumentId, data.version_id);

    // Update Live PDF Preview
    updatePdfPreview(data.download_url);

    // Update QA Badge
    qaScoreBadge.classList.remove('hidden');
    qaScoreBadge.textContent = `QA: ${Math.round(data.qa_score * 100)}%`;

    btnDownloadPdf.href = data.download_url;
    btnDownloadPdf.classList.remove('disabled');

    hideLoading();
    btnTranslate.disabled = false;
  } catch (error) {
    hideLoading();
    btnTranslate.disabled = false;
    alert(`Translation Error: ${error.message}`);
  }
}

async function loadDocumentStructure(docId, versionId) {
  try {
    const res = await fetch(`/api/v1/documents/${docId}/versions/${versionId}/structure`);
    if (!res.ok) return;

    const ir = await res.json();
    state.documentIR = ir;

    renderStructureNodes(ir);
  } catch (error) {
    console.error('Failed to load IR structure:', error);
  }
}

function renderStructureNodes(ir) {
  nodesList.innerHTML = '';
  structureEmptyState.classList.add('hidden');
  nodesList.classList.remove('hidden');

  let totalNodes = 0;

  ir.pages.forEach((page) => {
    page.nodes.forEach((node) => {
      totalNodes++;
      const nodeEl = document.createElement('div');
      nodeEl.className = `node-card ${state.selectedNodeId === node.node_id ? 'active' : ''}`;
      nodeEl.dataset.nodeId = node.node_id;

      const typeClass = node.type.toLowerCase();
      const statusClass = (node.translation_status || 'PENDING').toLowerCase();

      nodeEl.innerHTML = `
        <div class="node-card-header">
          <span class="node-type-tag ${typeClass}">${node.type}</span>
          <span class="node-status-tag ${statusClass}">${node.translation_status || 'TRANSLATED'}</span>
        </div>
        <div class="node-text-preview source">${escapeHtml(node.source_text)}</div>
        ${node.translated_text ? `<div class="node-text-preview translated">${escapeHtml(node.translated_text)}</div>` : ''}
      `;

      nodeEl.addEventListener('click', () => selectNode(node));
      nodesList.appendChild(nodeEl);
    });
  });

  nodeCountBadge.textContent = `${totalNodes} Nodes`;
}

function selectNode(node) {
  state.selectedNodeId = node.node_id;

  // Highlight in structure list
  document.querySelectorAll('.node-card').forEach((el) => {
    el.classList.toggle('active', el.dataset.nodeId === node.node_id);
  });

  // Populate Right Copilot Panel
  copilotEmptyState.classList.add('hidden');
  copilotActivePanel.classList.remove('hidden');

  selectedNodeType.textContent = node.type;
  selectedNodeId.textContent = node.node_id;
  selectedSourceText.textContent = node.source_text;
  selectedCurrentTranslation.textContent = node.translated_text || '(Not translated)';
  promptInput.value = '';

  // Render Edit History
  renderEditHistory(node.edit_history || []);
}

function renderEditHistory(history) {
  editHistoryList.innerHTML = '';
  if (!history || history.length === 0) {
    editHistoryList.innerHTML = '<div class="history-item empty">No previous edits on this node</div>';
    return;
  }

  history.forEach((h, idx) => {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `
      <div style="font-weight: 600; color: #93c5fd; margin-bottom: 2px;">Prompt ${idx + 1}: "${escapeHtml(h.instruction)}"</div>
      <div style="color: #cbd5e1;">${escapeHtml(h.new_translation)}</div>
    `;
    editHistoryList.appendChild(item);
  });
}

async function handleApplyPromptEdit() {
  if (!state.currentDocumentId || !state.selectedNodeId || !state.currentVersionId) return;

  const instruction = promptInput.value.trim();
  if (!instruction) {
    alert('Please enter a prompt instruction to refine this section.');
    return;
  }

  showLoading('Prompt-editing section & re-rendering PDF...');
  btnApplyPromptEdit.disabled = true;

  try {
    const res = await fetch(
      `/api/v1/documents/${state.currentDocumentId}/nodes/${state.selectedNodeId}/edit?version_id=${state.currentVersionId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: instruction }),
      }
    );

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Section edit failed');
    }

    const data = await res.json();
    state.currentVersionId = data.version_id;

    // Add new version to list
    const verNum = state.versions.length + 1;
    state.versions.push({
      version_id: data.version_id,
      label: `v${verNum}.0 (Edited Section ${state.selectedNodeId.slice(-4)})`,
    });
    updateVersionDropdown(data.version_id);

    // Refresh structure and live preview
    await loadDocumentStructure(state.currentDocumentId, data.version_id);

    const pdfUrl = `/api/v1/documents/${state.currentDocumentId}/versions/${data.version_id}/pdf`;
    updatePdfPreview(pdfUrl);
    btnDownloadPdf.href = pdfUrl;

    // Update selected node display
    selectedCurrentTranslation.textContent = data.edited_translation;
    promptInput.value = '';

    hideLoading();
    btnApplyPromptEdit.disabled = false;
  } catch (error) {
    hideLoading();
    btnApplyPromptEdit.disabled = false;
    alert(`Edit Error: ${error.message}`);
  }
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
  showLoading('Switching version...');
  
  await loadDocumentStructure(state.currentDocumentId, versionId);
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
  const sep = url.includes('?') ? '&' : '?';
  pdfFrame.src = `${url}${sep}_t=${Date.now()}`;
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
