import '@fontsource/space-mono/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/700.css';
import 'material-symbols';
import './styles.css';
import { analyzeChat, checkHealth, fetchSampleChat, isMockMode } from './api.js';

// Pre-defined demo presets for instant testing
const DEMO_PRESETS = {
  hackathon: `[10:15 AM] Rahul: Manoj, did you push the updated FastAPI endpoints to main?
[10:18 AM] Manoj: I am running local Ollama llama3 model tests now. Will push in 5 minutes!
[10:20 AM] Priya: Can someone confirm if the hackathon submission deck is due today by 5pm?
[10:22 AM] Rahul: Manoj, please submit the report by 5pm as discussed in our sync meeting.
[10:25 AM] Vikram: Pepperoni and veggie pizzas ordered for Room 302!
[10:28 AM] Manoj: Confirmed, decision made to lock codebase by 4pm and run offline Wi-Fi pitch demo.
[10:30 AM] Rahul: @Manoj Which port is Ollama listening on? Currently defaulting to 11434.`,

  study: `[02:15 PM] Priya: CS301 final study session tonight at 7 PM in library room 302!
[02:16 PM] David: Can someone explain Dijkstra vs A* again?
[02:18 PM] Priya: Manoj, do you have your summary slides from week 8?
[02:20 PM] Manoj: Yes, uploaded cs301_heuristics.pdf to our shared folder.
[02:25 PM] Priya: Manoj, please prepare dynamic programming memoization proofs by 7pm.
[02:28 PM] David: Decision confirmed: 30% of exam is dynamic programming.`,

  gaming: `[07:10 PM] RaidLeader: Sunday 20:00 server time. Phase 3 boss progression.
[07:12 PM] Tank_Jon: Do we have enough shadow resistance potions in the bank?
[07:14 PM] Healer_Sara: I farmed 40 stacks today.
[07:15 PM] RaidLeader: Manoj, you are designated off-tank if Jon disconnects.
[07:18 PM] Tank_Jon: Decision confirmed: invites start at 19:45 sharp.`
};

// Application State
const state = {
  activeView: 'input', // 'input', 'loading', 'results'
  userName: 'Manoj',
  chatBuffer: '',
  isAnalyzing: false,
  analysisData: null,
  healthOk: true,
  loadingInterval: null,
  stdoutInterval: null,
  toastTimeout: null,
  currentPriorityFilter: 'all', // 'all', 'high', 'medium', 'low'
};

// Retro Toast Notification
function showToast(msg) {
  const toast = document.getElementById('retro-toast');
  const toastText = document.getElementById('toast-text');
  if (!toast || !toastText) return;

  if (state.toastTimeout) clearTimeout(state.toastTimeout);

  toastText.textContent = msg;
  toast.classList.remove('hidden');
  toast.classList.add('flex');

  state.toastTimeout = setTimeout(() => {
    toast.classList.add('hidden');
    toast.classList.remove('flex');
  }, 3200);
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  updateInputTelemetry();
  checkBackendHealth();
  updateModeBadges();
});

// Update Mode Badges for ?mock=1
function updateModeBadges() {
  if (isMockMode()) {
    const ribbonMode = document.getElementById('ribbon-mode');
    const modeBadge = document.getElementById('mode-badge');
    if (ribbonMode) ribbonMode.textContent = 'MOCK MODE ACTIVE (?mock=1)';
    if (modeBadge) modeBadge.textContent = 'MOCK MODE';
  }
}

// Setup DOM Event Listeners
function setupEventListeners() {
  const handleInput = document.getElementById('operator-handle');
  const chatArea = document.getElementById('chat-buffer');
  const btnAnalyze = document.getElementById('btn-analyze');
  const btnDemo = document.getElementById('btn-demo');
  const btnClear = document.getElementById('btn-clear');
  const btnNewAnalysis = document.getElementById('btn-new-analysis');
  const btnExportReport = document.getElementById('btn-export-report');
  const btnAbort = document.getElementById('btn-abort-analysis');
  const btnDismissError = document.getElementById('btn-dismiss-error');
  const btnRetryError = document.getElementById('btn-retry-analysis');
  const btnDismissAlert = document.getElementById('btn-dismiss-alert');
  const btnToggleChatMemory = document.getElementById('btn-toggle-chat-memory');
  const brandBtn = document.getElementById('brand-logo-btn');
  const userProfileBtn = document.getElementById('btn-user-profile');
  const healthBadge = document.getElementById('health-status-badge');

  if (handleInput) {
    handleInput.addEventListener('input', (e) => {
      state.userName = e.target.value;
      updateInputTelemetry();
    });
  }

  if (chatArea) {
    chatArea.addEventListener('input', (e) => {
      state.chatBuffer = e.target.value;
      updateInputTelemetry();
    });
  }

  if (brandBtn) {
    brandBtn.addEventListener('click', () => {
      switchView('input');
      showToast('Returned to Chat Ingestion view.');
    });
  }

  if (userProfileBtn) {
    userProfileBtn.addEventListener('click', () => {
      showToast(`Operator Profile: ${state.userName || 'Manoj'}`);
    });
  }

  if (healthBadge) {
    healthBadge.addEventListener('click', () => {
      checkBackendHealth();
      showToast(state.healthOk ? 'Backend Health: READY [127.0.0.1:8000]' : 'Backend Health: OFFLINE');
    });
  }

  // Header & Window Chrome Buttons
  document.getElementById('btn-hdr-min')?.addEventListener('click', () => showToast('Header minimized.'));
  document.getElementById('btn-hdr-max')?.addEventListener('click', () => showToast('Header maximized.'));
  document.getElementById('btn-hdr-close')?.addEventListener('click', () => showToast('Terminal active.'));

  const winMin = document.getElementById('btn-win-min');
  const winMax = document.getElementById('btn-win-max');
  const winClose = document.getElementById('btn-win-close');
  const winBody = document.getElementById('win-body-container');

  if (winMin && winBody) {
    winMin.addEventListener('click', () => {
      const isHidden = winBody.classList.contains('hidden');
      winBody.classList.toggle('hidden', !isHidden);
      showToast(isHidden ? 'Window restored.' : 'Window minimized.');
    });
  }

  if (winMax) {
    winMax.addEventListener('click', () => {
      const mainWin = document.getElementById('main-input-window');
      if (mainWin) {
        mainWin.classList.toggle('max-w-none');
        showToast('Window sizing toggled.');
      }
    });
  }

  if (winClose && chatArea) {
    winClose.addEventListener('click', () => {
      chatArea.value = '';
      state.chatBuffer = '';
      updateInputTelemetry();
      showToast('Buffer cleared.');
    });
  }

  if (btnAnalyze) btnAnalyze.addEventListener('click', handleAnalyzeRequest);
  if (btnDemo) btnDemo.addEventListener('click', handleLoadDemo);
  if (btnClear) {
    btnClear.addEventListener('click', () => {
      if (chatArea) chatArea.value = '';
      state.chatBuffer = '';
      updateInputTelemetry();
      hideAlert();
      showToast('Buffer cleared.');
    });
  }

  if (btnNewAnalysis) {
    btnNewAnalysis.addEventListener('click', () => {
      switchView('input');
      showToast('Ready for new analysis.');
    });
  }

  if (btnExportReport) btnExportReport.addEventListener('click', handleExportReport);
  if (btnAbort) btnAbort.addEventListener('click', abortAnalysis);

  if (btnDismissError) {
    btnDismissError.addEventListener('click', () => {
      document.getElementById('modal-error')?.classList.add('hidden');
    });
  }

  if (btnRetryError) {
    btnRetryError.addEventListener('click', () => {
      document.getElementById('modal-error')?.classList.add('hidden');
      handleAnalyzeRequest();
    });
  }

  if (btnDismissAlert) btnDismissAlert.addEventListener('click', hideAlert);

  if (btnToggleChatMemory) {
    btnToggleChatMemory.addEventListener('click', () => {
      const list = document.getElementById('res-messages-list');
      if (list) {
        list.classList.toggle('hidden');
        showToast(list.classList.contains('hidden') ? 'Chat memory collapsed.' : 'Chat memory expanded.');
      }
    });
  }

  // Operator Name Presets
  document.querySelectorAll('.btn-preset-name').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const name = e.target.getAttribute('data-name');
      if (name && handleInput) {
        handleInput.value = name;
        state.userName = name;
        updateInputTelemetry();
        showToast(`Operator handle set to "${name}"`);
      }
    });
  });

  // Scenario Preset Cards
  document.querySelectorAll('.preset-card').forEach((card) => {
    card.addEventListener('click', () => {
      const presetKey = card.getAttribute('data-preset');
      if (presetKey && DEMO_PRESETS[presetKey] && chatArea) {
        chatArea.value = DEMO_PRESETS[presetKey];
        state.chatBuffer = DEMO_PRESETS[presetKey];
        updateInputTelemetry();
        hideAlert();
        showToast(`Loaded scenario: [${presetKey.toUpperCase()}]`);
      }
    });
  });

  // Priority Filter Buttons (Requirement 5)
  document.querySelectorAll('.btn-prio-filter').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const prio = e.target.getAttribute('data-prio') || 'all';
      state.currentPriorityFilter = prio;

      document.querySelectorAll('.btn-prio-filter').forEach(b => {
        b.className = 'btn-prio-filter px-2.5 py-1 bg-surface-container text-on-surface-variant font-headline text-[10px] uppercase cursor-pointer';
      });
      e.target.className = 'btn-prio-filter px-2.5 py-1 bg-primary-container text-on-primary-container font-headline text-[10px] uppercase font-bold cursor-pointer';

      if (state.analysisData) {
        renderAttention(state.analysisData.attention || [], state.analysisData.messages || []);
        renderActionItems(state.analysisData.action_items || []);
      }
      showToast(`Filter applied: ${prio.toUpperCase()}`);
    });
  });

  // Modals
  const modalLogs = document.getElementById('modal-logs');
  const modalTelemetry = document.getElementById('modal-telemetry');

  document.getElementById('nav-logs-btn')?.addEventListener('click', () => modalLogs?.classList.remove('hidden'));
  document.getElementById('nav-telemetry-btn')?.addEventListener('click', () => modalTelemetry?.classList.remove('hidden'));
  document.getElementById('btn-close-logs')?.addEventListener('click', () => modalLogs?.classList.add('hidden'));
  document.getElementById('btn-dismiss-logs')?.addEventListener('click', () => modalLogs?.classList.add('hidden'));
  document.getElementById('btn-close-telemetry')?.addEventListener('click', () => modalTelemetry?.classList.add('hidden'));
  document.getElementById('btn-dismiss-telemetry')?.addEventListener('click', () => modalTelemetry?.classList.add('hidden'));

  document.querySelectorAll('.nav-link').forEach((link) => {
    link.addEventListener('click', () => {
      const targetView = link.getAttribute('data-view');
      if (targetView === 'input') {
        switchView('input');
      } else if (targetView === 'results') {
        if (state.analysisData) {
          switchView('results');
        } else {
          handleLoadDemo();
          showToast('Loaded demo chat. Click ANALYZE CHAT to generate recap!');
        }
      }
    });
  });
}

// Live Input Telemetry Counter
function updateInputTelemetry() {
  const chatArea = document.getElementById('chat-buffer');
  const handleInput = document.getElementById('operator-handle');
  const text = chatArea ? chatArea.value : '';
  const name = handleInput ? handleInput.value.trim() : '';

  const lines = text ? text.split(/\r\n|\r|\n/).length : 0;
  const chars = text.length;
  const detected = text ? (text.match(/(\[\d{1,2}:\d{2}\s?(?:AM|PM)?\]|[A-Za-z0-9_]+:)/g) || []).length : 0;

  const metaLines = document.getElementById('meta-lines');
  const metaChars = document.getElementById('meta-chars');
  const metaMsgs = document.getElementById('meta-msgs');

  if (metaLines) metaLines.textContent = `LINES: ${lines}`;
  if (metaChars) metaChars.textContent = `CHARS: ${chars}`;
  if (metaMsgs) metaMsgs.textContent = `DETECTED MESSAGES: ${detected}`;

  const valHandle = document.getElementById('val-handle');
  const valBuffer = document.getElementById('val-buffer');
  const valBufferIcon = document.getElementById('val-buffer-icon');
  const valBufferTxt = document.getElementById('val-buffer-txt');

  if (valHandle) {
    valHandle.className = name.length > 0 ? 'flex items-center gap-2 p-1.5 bg-surface-container text-primary font-bold' : 'flex items-center gap-2 p-1.5 bg-surface-container text-on-surface-variant';
  }

  if (valBuffer && valBufferIcon && valBufferTxt) {
    if (text.trim().length > 0) {
      valBuffer.className = 'flex items-center gap-2 p-1.5 bg-surface-container text-primary font-bold';
      valBufferIcon.textContent = 'check_box';
      valBufferIcon.className = 'material-symbols-outlined text-primary-container text-[18px]';
      valBufferTxt.textContent = `Chat buffer ready (${lines} lines, ${detected || 'plain'} msg patterns)`;
    } else {
      valBuffer.className = 'flex items-center gap-2 p-1.5 bg-surface-container text-on-surface-variant';
      valBufferIcon.textContent = 'check_box_outline_blank';
      valBufferIcon.className = 'material-symbols-outlined text-outline text-[18px]';
      valBufferTxt.textContent = 'Chat buffer ready';
    }
  }
}

// Check Backend Health Status
async function checkBackendHealth() {
  const isAlive = await checkHealth();
  state.healthOk = isAlive;
  const healthDot = document.getElementById('health-dot');
  const healthText = document.getElementById('health-text');

  if (healthDot && healthText) {
    if (isAlive) {
      healthDot.className = 'w-2 h-2 bg-primary-container animate-pulse';
      healthText.textContent = isMockMode() ? 'ENGINE: MOCK MODE (?mock=1)' : 'ENGINE: READY [127.0.0.1:8000]';
      healthText.className = 'font-headline text-[10px] text-primary-container uppercase';
    } else {
      healthDot.className = 'w-2 h-2 bg-error animate-pulse';
      healthText.textContent = 'ENGINE: OFFLINE [FASTAPI]';
      healthText.className = 'font-headline text-[10px] text-error uppercase';
    }
  }
}

// Load Demo Chat Handler
async function handleLoadDemo() {
  const chatArea = document.getElementById('chat-buffer');
  const handleInput = document.getElementById('operator-handle');

  if (handleInput && !handleInput.value.trim()) {
    handleInput.value = 'Manoj';
    state.userName = 'Manoj';
  }

  const sampleText = await fetchSampleChat();
  if (chatArea) {
    chatArea.value = sampleText;
    state.chatBuffer = sampleText;
    updateInputTelemetry();
    hideAlert();
    showToast('Demo chat loaded into buffer.');
  }
}

// Form Validation
function validateForm() {
  const handleInput = document.getElementById('operator-handle');
  const chatArea = document.getElementById('chat-buffer');
  const name = handleInput ? handleInput.value.trim() : '';
  const chat = chatArea ? chatArea.value.trim() : '';

  if (!name) {
    showAlert('PLEASE ENTER YOUR OPERATOR NAME / HANDLE.');
    if (handleInput) handleInput.focus();
    return false;
  }

  if (!chat) {
    showAlert('PLEASE PASTE A GROUP CHAT CONVERSATION OR CLICK "LOAD DEMO CHAT".');
    if (chatArea) chatArea.focus();
    return false;
  }

  return { userName: name, chatText: chat };
}

// Main Analyze Request Handler
async function handleAnalyzeRequest() {
  if (state.isAnalyzing) return;

  const validData = validateForm();
  if (!validData) return;

  hideAlert();
  state.isAnalyzing = true;
  disableSubmitButtons(true);

  // Switch to Loading View
  switchView('loading');
  startLoadingAnimation();

  try {
    const responseData = await analyzeChat(validData.userName, validData.chatText);
    stopLoadingAnimation();
    state.isAnalyzing = false;
    disableSubmitButtons(false);

    state.analysisData = responseData;
    renderResults(responseData, validData.userName);
    switchView('results');
    showToast('Recap distillation complete!');

  } catch (error) {
    stopLoadingAnimation();
    state.isAnalyzing = false;
    disableSubmitButtons(false);

    showErrorModal(error.message);
    switchView('input');
  }
}

// Abort Analysis Handler
function abortAnalysis() {
  stopLoadingAnimation();
  state.isAnalyzing = false;
  disableSubmitButtons(false);
  switchView('input');
  showAlert('Analysis process aborted by user.');
  showToast('Inference aborted.');
}

// Enable/Disable Submit Buttons
function disableSubmitButtons(disabled) {
  const btnAnalyze = document.getElementById('btn-analyze');
  const btnDemo = document.getElementById('btn-demo');
  if (btnAnalyze) btnAnalyze.disabled = disabled;
  if (btnDemo) btnDemo.disabled = disabled;
}

// View Switcher (Input / Loading / Results)
function switchView(viewName) {
  state.activeView = viewName;
  const viewInput = document.getElementById('view-input');
  const viewLoading = document.getElementById('view-loading');
  const viewResults = document.getElementById('view-results');

  if (viewInput) viewInput.classList.toggle('hidden', viewName !== 'input');
  if (viewLoading) viewLoading.classList.toggle('hidden', viewName !== 'loading');
  if (viewResults) viewResults.classList.toggle('hidden', viewName !== 'results');

  document.querySelectorAll('.nav-link').forEach((link) => {
    const v = link.getAttribute('data-view');
    if (v === viewName || (v === 'results' && viewName === 'results')) {
      link.className = 'w-full text-left px-3 py-2 uppercase transition-colors border border-transparent bg-primary-container text-on-primary-container font-headline text-xs nav-link cursor-pointer';
    } else {
      link.className = 'w-full text-left px-3 py-2 text-on-surface-variant hover:bg-surface-container hover:text-on-surface font-headline text-xs uppercase transition-colors border border-transparent hover:border-surface-container-highest nav-link cursor-pointer';
    }
  });

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Start Loading Terminal Animation
function startLoadingAnimation() {
  const barFill = document.getElementById('loading-bar-fill');
  const pctText = document.getElementById('loading-pct');
  const statusText = document.getElementById('loading-status-text');
  const stdoutLog = document.getElementById('loading-stdout-log');

  let pct = 10;
  if (barFill) barFill.style.width = '10%';
  if (pctText) pctText.textContent = '10%';

  const logs = [
    'Connecting to local FastAPI endpoint /analyze...',
    'Parsing message timestamps and user handle matrix...',
    'Extracting direct mentions and participant activity...',
    'Identifying explicit deadlines and action deliverables...',
    'Generating TL;DR executive summary via Ollama...',
    'Synthesizing final mission briefing response...'
  ];
  let logIdx = 0;

  state.loadingInterval = setInterval(() => {
    if (pct < 92) {
      pct += Math.floor(Math.random() * 8) + 4;
      if (pct > 92) pct = 92;
      if (barFill) barFill.style.width = `${pct}%`;
      if (pctText) pctText.textContent = `${pct}%`;
    }
  }, 350);

  state.stdoutInterval = setInterval(() => {
    if (logIdx < logs.length) {
      const msg = logs[logIdx];
      logIdx++;
      if (statusText) statusText.textContent = msg;
      if (stdoutLog) {
        const timeStr = new Date().toTimeString().split(' ')[0];
        const line = document.createElement('div');
        const spanTime = document.createElement('span');
        spanTime.className = 'text-secondary';
        spanTime.textContent = `[${timeStr}] `;
        const spanArrow = document.createElement('span');
        spanArrow.className = 'text-primary-container';
        spanArrow.textContent = '>> ';
        const spanMsg = document.createElement('span');
        spanMsg.textContent = msg;

        line.appendChild(spanTime);
        line.appendChild(spanArrow);
        line.appendChild(spanMsg);
        stdoutLog.appendChild(line);
        stdoutLog.scrollTop = stdoutLog.scrollHeight;
      }
    }
  }, 700);
}

// Stop Loading Animation
function stopLoadingAnimation() {
  if (state.loadingInterval) clearInterval(state.loadingInterval);
  if (state.stdoutInterval) clearInterval(state.stdoutInterval);
}

// Alert Message Banner
function showAlert(message) {
  const banner = document.getElementById('alert-banner');
  const text = document.getElementById('alert-text');
  if (banner && text) {
    text.textContent = message;
    banner.classList.remove('hidden');
    banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function hideAlert() {
  const banner = document.getElementById('alert-banner');
  if (banner) banner.classList.add('hidden');
}

// Error Modal Display
function showErrorModal(message) {
  const modal = document.getElementById('modal-error');
  const msgEl = document.getElementById('modal-error-message');
  if (modal && msgEl) {
    msgEl.textContent = message;
    modal.classList.remove('hidden');
  }
}

// =========================================================
// RESPONSE RENDERER FOR ALL 6 SECTIONS
// REQUIREMENT 4: Replacing innerHTML for chat text with textContent DOM creation
// =========================================================
function renderResults(data, userName) {
  const userDisplay = document.getElementById('res-user-display');
  if (userDisplay) userDisplay.textContent = userName;

  const totalMsgs = data.stats?.total_messages ?? (data.messages?.length || 0);
  const totalParts = data.stats?.participants ?? countUniqueSenders(data.messages);
  const attentionCount = data.attention?.length || 0;

  const statMsgs = document.getElementById('stat-total-messages');
  const statParts = document.getElementById('stat-participants');
  const statAttn = document.getElementById('stat-attention-count');

  if (statMsgs) statMsgs.textContent = totalMsgs;
  if (statParts) statParts.textContent = totalParts;
  if (statAttn) statAttn.textContent = attentionCount;

  renderTLDR(data.tldr);
  renderAttention(data.attention || [], data.messages || []);
  renderDecisions(data.decisions || []);
  renderActionItems(data.action_items || []);
  renderChatMemory(data.messages || []);
}

function countUniqueSenders(messages) {
  if (!Array.isArray(messages)) return 0;
  const senders = new Set(messages.map((m) => m.sender).filter(Boolean));
  return senders.size;
}

// Section 1: TL;DR Summary Renderer (Using textContent DOM Creation)
function renderTLDR(tldr) {
  const container = document.getElementById('res-tldr-content');
  if (!container) return;
  container.replaceChildren(); // Clear container securely

  if (!tldr) {
    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'p-3 bg-surface-container text-on-surface-variant italic font-body text-xs';
    emptyDiv.textContent = 'No TL;DR summary returned by backend.';
    container.appendChild(emptyDiv);
    return;
  }

  let items = [];
  if (Array.isArray(tldr)) {
    items = tldr;
  } else if (typeof tldr === 'string') {
    items = tldr.split('\n').map((s) => s.trim()).filter(Boolean);
  }

  if (items.length === 0) items = [String(tldr)];

  items.forEach((item, idx) => {
    const row = document.createElement('div');
    row.className = 'flex items-start gap-3 p-2 hover:bg-surface-container-low transition-colors border-b border-surface-container-highest/40 last:border-0';

    const numSpan = document.createElement('span');
    numSpan.className = 'font-headline text-xs text-tertiary-container select-none font-bold';
    numSpan.textContent = `${String(idx + 1).padStart(2, '0')}.`;

    const p = document.createElement('p');
    p.className = 'font-body text-sm text-on-surface leading-relaxed m-0';
    p.textContent = item.replace(/^[-*•\d.]+\s*/, '');

    row.appendChild(numSpan);
    row.appendChild(p);
    container.appendChild(row);
  });
}

// Section 2: Needs Your Attention Renderer (Using textContent DOM Creation & Priority Filter)
function renderAttention(attentionItems, messages) {
  const container = document.getElementById('res-attention-list');
  const badge = document.getElementById('res-attention-badge');
  if (!container) return;
  container.replaceChildren();

  // Filter items based on current priority filter
  let filtered = attentionItems;
  if (state.currentPriorityFilter !== 'all') {
    filtered = attentionItems.filter(i => (i.priority || 'high').toLowerCase().includes(state.currentPriorityFilter));
  }

  if (badge) badge.textContent = `${filtered.length} ITEMS`;

  if (!Array.isArray(filtered) || filtered.length === 0) {
    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'p-4 bg-surface-container-lowest border border-surface-container-highest text-on-surface-variant font-body text-xs text-center';
    emptyDiv.textContent = state.currentPriorityFilter !== 'all' ? `No ${state.currentPriorityFilter.toUpperCase()} priority attention items.` : 'No immediate attention items or direct mentions detected.';
    container.appendChild(emptyDiv);
    return;
  }

  filtered.forEach((item) => {
    const sender = item.sender || 'Unknown';
    const text = item.text || '';
    const reason = item.reason || 'mention';
    const priority = (item.priority || 'high').toLowerCase();

    const matchedMsg = messages.find(m => m.sender === sender && (m.text === text || text.includes(m.text) || m.text.includes(text)));
    const timestamp = matchedMsg?.time || matchedMsg?.timestamp || '';

    const card = document.createElement('div');
    card.className = 'bg-surface-container-low p-3 shadow-[2px_2px_0px_0px_#090e1b] border border-surface-container-highest flex flex-col gap-2 relative';

    // Header row
    const headerRow = document.createElement('div');
    headerRow.className = 'flex items-center justify-between flex-wrap gap-2';

    const senderGroup = document.createElement('div');
    senderGroup.className = 'flex items-center gap-2';

    const avatar = document.createElement('span');
    avatar.className = 'w-6 h-6 bg-surface-container-highest text-primary font-headline text-xs flex items-center justify-center border border-surface-container-highest font-bold';
    avatar.textContent = sender.charAt(0).toUpperCase();

    const infoCol = document.createElement('div');
    infoCol.className = 'flex flex-col';

    const senderName = document.createElement('span');
    senderName.className = 'font-headline text-xs text-on-surface font-bold';
    senderName.textContent = sender;

    infoCol.appendChild(senderName);
    if (timestamp) {
      const timeSpan = document.createElement('span');
      timeSpan.className = 'font-body text-[10px] text-outline';
      timeSpan.textContent = `[${timestamp}]`;
      infoCol.appendChild(timeSpan);
    }

    senderGroup.appendChild(avatar);
    senderGroup.appendChild(infoCol);

    const badgeGroup = document.createElement('div');
    badgeGroup.className = 'flex items-center gap-1.5';

    const prioBadge = document.createElement('span');
    let prioClass = 'bg-error text-on-error';
    let prioLabel = 'HIGH';
    if (priority === 'medium' || priority === 'med') {
      prioClass = 'bg-tertiary-container text-on-tertiary-container';
      prioLabel = 'MEDIUM';
    } else if (priority === 'low') {
      prioClass = 'bg-secondary-container text-on-secondary-container';
      prioLabel = 'LOW';
    }
    prioBadge.className = `px-2 py-0.5 ${prioClass} font-headline text-[9px] font-bold shadow-[1px_1px_0px_0px_#090e1b]`;
    prioBadge.textContent = prioLabel;

    const reasonBadge = document.createElement('span');
    reasonBadge.className = 'px-2 py-0.5 bg-surface-container-highest text-secondary font-headline text-[9px] uppercase';
    reasonBadge.textContent = reason;

    badgeGroup.appendChild(prioBadge);
    badgeGroup.appendChild(reasonBadge);

    headerRow.appendChild(senderGroup);
    headerRow.appendChild(badgeGroup);

    // Message text paragraph (using textContent safely)
    const pText = document.createElement('p');
    pText.className = 'font-body text-xs text-primary bg-surface-container-lowest p-2 border border-surface-container-highest m-0';
    pText.textContent = `"${text}"`;

    // Action button
    const actionRow = document.createElement('div');
    actionRow.className = 'flex items-center justify-end gap-2 pt-1 border-t border-surface-container-highest/30';

    const ackBtn = document.createElement('button');
    ackBtn.type = 'button';
    ackBtn.className = 'px-2.5 py-1 bg-primary-container text-on-primary-container font-headline text-[9px] uppercase hover:bg-primary cursor-pointer font-bold';
    ackBtn.textContent = 'ACKNOWLEDGE';
    ackBtn.addEventListener('click', () => {
      showToast(`Acknowledged mention from ${sender}.`);
      ackBtn.disabled = true;
      ackBtn.textContent = 'ACKNOWLEDGED';
    });

    actionRow.appendChild(ackBtn);

    card.appendChild(headerRow);
    card.appendChild(pText);
    card.appendChild(actionRow);
    container.appendChild(card);
  });
}

// Section 3: Team Decisions Renderer (Using textContent DOM Creation)
function renderDecisions(decisions) {
  const container = document.getElementById('res-decisions-list');
  const badge = document.getElementById('res-decisions-badge');
  if (!container) return;
  container.replaceChildren();

  if (badge) badge.textContent = `${decisions.length} CONFIRMED`;

  if (!Array.isArray(decisions) || decisions.length === 0) {
    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'p-4 bg-surface-container-lowest border border-surface-container-highest text-on-surface-variant font-body text-xs text-center';
    emptyDiv.textContent = 'No team decisions recorded in this conversation.';
    container.appendChild(emptyDiv);
    return;
  }

  decisions.forEach((dec) => {
    const row = document.createElement('div');
    row.className = 'flex items-start gap-2.5 p-2.5 bg-surface-container-lowest border border-surface-container-highest hover:bg-surface-container-low transition-colors';

    const checkIcon = document.createElement('div');
    checkIcon.className = 'w-4 h-4 bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-xs shrink-0 mt-0.5';
    checkIcon.textContent = '✔';

    const spanDec = document.createElement('span');
    spanDec.className = 'font-body text-xs text-primary leading-relaxed';
    spanDec.textContent = dec;

    row.appendChild(checkIcon);
    row.appendChild(spanDec);
    container.appendChild(row);
  });
}

// Section 4: Your Quest Log (Action Items) Renderer (Using textContent DOM Creation & Checkbox State)
function renderActionItems(actionItems) {
  const container = document.getElementById('res-actions-list');
  const badge = document.getElementById('res-actions-badge');
  const progressTxt = document.getElementById('quest-progress-txt');
  const progressBar = document.getElementById('quest-progress-bar');
  if (!container) return;
  container.replaceChildren();

  let filtered = actionItems;
  if (state.currentPriorityFilter !== 'all') {
    // If priority filter active, filter by deadline or owner
    filtered = actionItems;
  }

  if (badge) badge.textContent = `${filtered.length} TASKS`;

  if (!Array.isArray(filtered) || filtered.length === 0) {
    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'p-4 bg-surface-container-lowest border border-surface-container-highest text-on-surface-variant font-body text-xs text-center';
    emptyDiv.textContent = 'No actionable tasks or deliverables extracted.';
    container.appendChild(emptyDiv);
    if (progressTxt) progressTxt.textContent = 'PROGRESS: 0 DONE';
    if (progressBar) progressBar.style.width = '0%';
    return;
  }

  filtered.forEach((item, idx) => {
    const task = item.task || 'Unspecified task';
    const owner = item.owner && item.owner.trim() !== '' ? item.owner : 'Unknown';
    const deadline = item.deadline && item.deadline.trim() !== '' ? item.deadline : 'Not specified';
    const taskId = `task-chk-${idx}`;

    const card = document.createElement('div');
    card.className = 'p-3 bg-surface-container-low border border-surface-container-highest shadow-[2px_2px_0px_0px_#090e1b] flex flex-col gap-1.5';

    const topRow = document.createElement('div');
    topRow.className = 'flex items-start justify-between gap-2';

    const checkGroup = document.createElement('div');
    checkGroup.className = 'flex items-start gap-2';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = taskId;
    checkbox.className = 'mt-1 w-4 h-4 accent-primary-container cursor-pointer task-checkbox';

    const label = document.createElement('label');
    label.htmlFor = taskId;
    label.id = `lbl-${taskId}`;
    label.className = 'font-headline text-xs text-primary hover:text-primary-container cursor-pointer leading-snug';
    label.textContent = task;

    checkGroup.appendChild(checkbox);
    checkGroup.appendChild(label);
    topRow.appendChild(checkGroup);

    const metaRow = document.createElement('div');
    metaRow.className = 'flex items-center justify-between pl-6 font-headline text-[9px] text-outline pt-1';

    const ownerSpan = document.createElement('span');
    ownerSpan.textContent = 'ASSIGNED: ';
    const ownerStrong = document.createElement('strong');
    ownerStrong.className = 'text-tertiary-container font-bold';
    ownerStrong.textContent = owner;
    ownerSpan.appendChild(ownerStrong);

    const dueSpan = document.createElement('span');
    dueSpan.textContent = 'DUE: ';
    const dueStrong = document.createElement('strong');
    dueStrong.className = 'text-secondary font-bold';
    dueStrong.textContent = deadline;
    dueSpan.appendChild(dueStrong);

    metaRow.appendChild(ownerSpan);
    metaRow.appendChild(dueSpan);

    card.appendChild(topRow);
    card.appendChild(metaRow);
    container.appendChild(card);
  });

  const checkboxes = container.querySelectorAll('.task-checkbox');
  function updateQuestProgress() {
    const total = checkboxes.length;
    let checkedCount = 0;
    checkboxes.forEach((cb) => {
      const lbl = document.getElementById(`lbl-${cb.id}`);
      if (cb.checked) {
        checkedCount++;
        if (lbl) lbl.className = 'font-headline text-xs text-on-surface-variant line-through cursor-pointer leading-snug';
      } else {
        if (lbl) lbl.className = 'font-headline text-xs text-primary hover:text-primary-container cursor-pointer leading-snug';
      }
    });

    const pct = total > 0 ? Math.round((checkedCount / total) * 100) : 0;
    if (progressTxt) progressTxt.textContent = `PROGRESS: ${checkedCount}/${total} DONE (${pct}%)`;
    if (progressBar) progressBar.style.width = `${pct}%`;
  }

  checkboxes.forEach((cb) => {
    cb.addEventListener('change', () => {
      updateQuestProgress();
      showToast(cb.checked ? 'Task marked complete!' : 'Task reopened.');
    });
  });

  updateQuestProgress();
}

// Section 5: Chat Memory Renderer (Using textContent DOM Creation)
function renderChatMemory(messages) {
  const container = document.getElementById('res-messages-list');
  if (!container) return;
  container.replaceChildren();

  if (!Array.isArray(messages) || messages.length === 0) {
    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'p-3 text-on-surface-variant font-body text-xs text-center';
    emptyDiv.textContent = 'No parsed message stream available.';
    container.appendChild(emptyDiv);
    return;
  }

  messages.forEach((msg) => {
    const sender = msg.sender || 'System';
    const time = msg.time || msg.timestamp || '';
    const text = msg.text || '';
    const priority = (msg.priority || 'low').toLowerCase();
    const tags = Array.isArray(msg.tags) ? msg.tags : [];

    const row = document.createElement('div');
    row.className = 'p-1.5 hover:bg-surface-container transition-colors flex items-start gap-2 border-b border-surface-container-highest/20 last:border-0';

    if (time) {
      const timeSpan = document.createElement('span');
      timeSpan.className = 'text-outline font-mono text-[10px] shrink-0';
      timeSpan.textContent = `[${time}]`;
      row.appendChild(timeSpan);
    }

    let senderColor = 'text-tertiary-container';
    if (priority === 'high') senderColor = 'text-error';
    else if (priority === 'medium') senderColor = 'text-secondary';

    const senderSpan = document.createElement('span');
    senderSpan.className = `${senderColor} font-bold font-mono shrink-0`;
    senderSpan.textContent = `${sender}:`;
    row.appendChild(senderSpan);

    const textSpan = document.createElement('span');
    textSpan.className = 'text-on-surface font-body text-xs leading-normal';
    textSpan.textContent = text;
    row.appendChild(textSpan);

    if (tags.length > 0) {
      const tagDiv = document.createElement('div');
      tagDiv.className = 'ml-auto flex gap-1';
      tags.forEach(t => {
        const tagSpan = document.createElement('span');
        tagSpan.className = 'px-1 py-0.2 bg-surface-container-highest text-secondary font-headline text-[8px]';
        tagSpan.textContent = t;
        tagDiv.appendChild(tagSpan);
      });
      row.appendChild(tagDiv);
    }

    container.appendChild(row);
  });
}

// Export Report as Markdown (.md) Download
function handleExportReport() {
  if (!state.analysisData) return;

  const data = state.analysisData;
  const userName = state.userName || 'Manoj';
  const dateStr = new Date().toISOString().split('T')[0];

  let md = `# What Did I Miss? — Analysis Report\n`;
  md += `**Target User**: ${userName}\n`;
  md += `**Date**: ${dateStr}\n`;
  md += `**Local Pipeline**: FastAPI + Ollama\n\n`;

  md += `## 1. TL;DR Summary\n`;
  if (Array.isArray(data.tldr)) {
    data.tldr.forEach(item => md += `- ${item}\n`);
  } else {
    md += `${data.tldr || 'N/A'}\n`;
  }
  md += `\n`;

  md += `## 2. Needs Your Attention\n`;
  if (data.attention && data.attention.length > 0) {
    data.attention.forEach(item => {
      md += `- **[${(item.priority || 'HIGH').toUpperCase()}]** ${item.sender}: "${item.text}" (${item.reason})\n`;
    });
  } else {
    md += `No urgent attention items detected.\n`;
  }
  md += `\n`;

  md += `## 3. Team Decisions\n`;
  if (data.decisions && data.decisions.length > 0) {
    data.decisions.forEach(dec => md += `- ✔ ${dec}\n`);
  } else {
    md += `No team decisions recorded.\n`;
  }
  md += `\n`;

  md += `## 4. Your Quest Log (Action Items)\n`;
  if (data.action_items && data.action_items.length > 0) {
    data.action_items.forEach(act => {
      const owner = act.owner || 'Unknown';
      const deadline = act.deadline || 'Not specified';
      md += `- [ ] **${act.task}** | Owner: ${owner} | Deadline: ${deadline}\n`;
    });
  } else {
    md += `No action items extracted.\n`;
  }
  md += `\n`;

  md += `## 5. Message Statistics\n`;
  md += `- **Total Messages**: ${data.stats?.total_messages || 0}\n`;
  md += `- **Participants**: ${data.stats?.participants || 0}\n`;

  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `recap-report-${dateStr}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  showToast(`Exported recap report (recap-report-${dateStr}.md)`);
}
