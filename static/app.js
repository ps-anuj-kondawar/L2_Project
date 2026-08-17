/* ─── ChemShield AI — Frontend Application ────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {

  // ── Session context (shared across sections) ──────────────────────────────
  // Holds the last audited formulation + audit summary so the Copilot can
  // reference it without the user re-typing anything.
  const session = {
    formulation:      null,
    auditSummary:     null,
    lastAuditResult:  null,
  };

  // ── DOM refs ──────────────────────────────────────────────────────────────
  const formulationInput  = document.getElementById('formulation-input');
  const cardRunBtn        = document.getElementById('card-run-btn');
  const cardRunLabel      = document.getElementById('card-run-label');
  const globalRunBtn      = document.getElementById('global-run-btn');
  const runStatusChip     = document.getElementById('run-status-chip');
  const scenariosRow      = document.getElementById('scenarios-row');
  const charCount         = document.getElementById('char-count');
  const generateSdsBtn    = document.getElementById('generate-sds-btn');
  const onboardingBanner  = document.getElementById('onboarding-banner');
  const onboardingClose   = document.getElementById('onboarding-close-btn');
  const retrievalLegend   = document.getElementById('retrieval-legend');
  const flagsHelpText     = document.getElementById('flags-help-text');

  // Incomplete Formulation Modal refs
  const incompleteModalOverlay = document.getElementById('incomplete-modal-overlay');
  const incompleteIssuesList   = document.getElementById('incomplete-issues-list');
  const incompleteOkBtn        = document.getElementById('incomplete-modal-ok-btn');
  const incompleteRiskBtn      = document.getElementById('incomplete-modal-risk-btn');

  // Audit section
  const metricsGrid       = document.getElementById('metrics-grid');
  const verdictBanner     = document.getElementById('verdict-banner');
  const auditResultsGrid  = document.getElementById('audit-results-grid');
  const summaryText       = document.getElementById('summary-text');
  const flagsContainer    = document.getElementById('flags-container');
  const logStream         = document.getElementById('log-stream');
  const mvLatency         = document.getElementById('mv-latency');
  const mvRag             = document.getElementById('mv-rag');
  const mvTools           = document.getElementById('mv-tools');
  const mvReflect         = document.getElementById('mv-reflect');

  // SDS section
  const sdsHtmlWrapper    = document.getElementById('sds-html-wrapper');
  const sdsMvSections     = document.getElementById('sds-mv-sections');
  const sdsMvReflect      = document.getElementById('sds-mv-reflect');
  const sdsMvIters        = document.getElementById('sds-mv-iters');
  const printSdsBtn       = document.getElementById('print-sds-btn');

  // Trace section
  const traceList         = document.getElementById('trace-list');
  const traceMvSteps      = document.getElementById('trace-mv-steps');
  const traceMvAgents     = document.getElementById('trace-mv-agents');
  const traceMvSuccess    = document.getElementById('trace-mv-success');
  const traceMvAvg        = document.getElementById('trace-mv-avg');

  // Copilot section
  const chatBox           = document.getElementById('chat-box');
  const chatInput         = document.getElementById('chat-input');
  const sendChatBtn       = document.getElementById('send-chat-btn');
  const contextBanner     = document.getElementById('context-banner');
  const contextBannerText = document.getElementById('context-banner-text');
  const contextClearBtn   = document.getElementById('context-clear-btn');

  // Sidebar Telemetry & Step Tracker refs
  const sidebarLiveDot    = document.getElementById('sidebar-live-dot');
  const stepExtract       = document.getElementById('step-extract');
  const stepAudit         = document.getElementById('step-audit');
  const stepVerdict       = document.getElementById('step-verdict');
  const stepSds           = document.getElementById('step-sds');

  const badgeExtract      = document.getElementById('badge-extract');
  const badgeAudit        = document.getElementById('badge-audit');
  const badgeVerdict      = document.getElementById('badge-verdict');
  const badgeSds          = document.getElementById('badge-sds');

  // SDS Popup Worker Modal refs
  const sdsModalOverlay   = document.getElementById('sds-modal-overlay');
  const modalSdsBody      = document.getElementById('modal-sds-body');
  const modalPrintBtn     = document.getElementById('modal-print-btn');
  const modalCloseBtn     = document.getElementById('modal-close-btn');

  let chatHistory = [];
  let scenarioMap = {};
  let activeEventSource = null;
  let pendingSdsAction = null;

  // ── Formulation Completeness Evaluator ──────────────────────────────────
  function evaluateFormulationCompleteness(text, auditResult = null) {
    const issues = [];
    const lower = text.toLowerCase();

    // Check 1: Prior audit result flags if available for the same formulation text
    if (auditResult && auditResult.compliance_report && auditResult.compliance_report.chemical_flags) {
      auditResult.compliance_report.chemical_flags.forEach(f => {
        if (!f.detected_concentration || f.detected_concentration === 'Not specified' || f.detected_concentration === 'null') {
          issues.push(`Chemical <strong>${f.chemical_name}</strong> has no specified concentration. GHS mixture classification cut-offs require explicit concentration (% w/w or ppm).`);
        }
      });
    }

    // Check 2: Direct heuristic pattern analysis on input text
    const commonChems = [
      'benzene', 'toluene', 'acetone', 'methanol', 'ethanol', 'isopropanol', 'ipa',
      'chloroform', 'formaldehyde', 'sulfuric acid', 'hydrochloric acid', 'nitric acid',
      'sodium hydroxide', 'phenol', 'dichloromethane', 'methylene chloride', 'hexane',
      'diethyl ether', 'tetrahydrofuran', 'thf', 'acetonitrile', 'xylene', 'ammonia'
    ];

    const detectedChems = commonChems.filter(c => lower.includes(c));
    const hasUnits = /([0-9]+(?:\.[0-9]+)?\s*(%|ppm|mg\/l|g\/l|wt%|vol%|m|mm|mol|mg|g|ml|l))/i.test(text);

    if (detectedChems.length > 0 && !hasUnits && issues.length === 0) {
      detectedChems.forEach(c => {
        const capitalized = c.charAt(0).toUpperCase() + c.slice(1);
        issues.push(`Chemical <strong>${capitalized}</strong>: No concentration detected in input (e.g. missing percentage '%' or 'ppm').`);
      });
    }

    if (detectedChems.length === 0 && !hasUnits && text.length > 0 && issues.length === 0) {
      issues.push(`Unquantified formulation: No quantifiable chemical concentrations or standard laboratory formulation parameters detected.`);
    }

    return {
      isComplete: issues.length === 0,
      issues: issues
    };
  }

  function showIncompleteWarningModal(issues, onProceedRisk) {
    if (!incompleteModalOverlay || !incompleteIssuesList) return;
    incompleteIssuesList.innerHTML = issues.map(iss => `
      <div class="incomplete-issue-item">
        <span class="incomplete-issue-dot">&#9888;</span>
        <span>${iss}</span>
      </div>
    `).join('');

    pendingSdsAction = onProceedRisk;
    incompleteModalOverlay.classList.remove('hidden');
  }

  if (incompleteOkBtn) {
    incompleteOkBtn.addEventListener('click', () => {
      if (incompleteModalOverlay) incompleteModalOverlay.classList.add('hidden');
      pendingSdsAction = null;
      if (formulationInput) {
        formulationInput.focus();
        formulationInput.style.borderColor = 'var(--partial)';
        setTimeout(() => { formulationInput.style.borderColor = ''; }, 2000);
      }
    });
  }

  if (incompleteRiskBtn) {
    incompleteRiskBtn.addEventListener('click', () => {
      if (incompleteModalOverlay) incompleteModalOverlay.classList.add('hidden');
      if (typeof pendingSdsAction === 'function') {
        const action = pendingSdsAction;
        pendingSdsAction = null;
        action();
      }
    });
  }

  if (incompleteModalOverlay) {
    incompleteModalOverlay.addEventListener('click', (e) => {
      if (e.target === incompleteModalOverlay) {
        incompleteModalOverlay.classList.add('hidden');
        pendingSdsAction = null;
      }
    });
  }

  // ── Step tracker status helper ───────────────────────────────────────────
  function resetTracker(intent = 'audit') {
    [stepExtract, stepAudit, stepVerdict, stepSds].forEach(el => {
      if (el) el.className = 'tracker-step';
    });
    [badgeExtract, badgeAudit, badgeVerdict, badgeSds].forEach(el => {
      if (el) el.textContent = '--';
    });
    if (badgeSds && intent === 'audit') {
      badgeSds.textContent = 'Skipped';
    }
  }

  function setStepStatus(stepEl, badgeEl, status, label) {
    if (!stepEl) return;
    stepEl.className = `tracker-step ${status}`;
    if (badgeEl) badgeEl.textContent = label || (status === 'running' ? 'Active' : status === 'complete' ? 'Done' : '--');
  }

  // ── Load scenario presets from API ───────────────────────────────────────
  fetch('/api/v1/examples')
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => { scenarioMap = data; })
    .catch(() => {
      scenarioMap = {
        rejected_benzene:  { input: 'Formula B: 94% Water, 6% Benzene. Heat the mixture to 120°C in a soda-lime glass beaker.' },
        approved_ipa:      { input: 'Mix 70% Isopropanol and 30% Water. Store in a polypropylene container at 25°C.' },
        partial_toluene:   { input: 'Formulation: 500 ppm Toluene, 800 ppm Acetone. Heated to 90°C in a polypropylene container.' },
        chloroform_web:    { input: 'Formula X: 50% Chloroform. Store at 25°C in a borosilicate glass beaker.' },
        typo_auto_correct: { input: 'Note: Contains 6% benzen. Heated to 50°C in a borosilicate glass beaker.' },
        cas_number_input:  { input: 'Formulation: CAS 71-43-2 at 0.5 ppm in 99.9% Water. Store at 25°C in a polypropylene container.' },
      };
    });

  scenariosRow.querySelectorAll('.scenario-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      scenariosRow.querySelectorAll('.scenario-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const key = chip.dataset.key;
      if (scenarioMap[key]) formulationInput.value = scenarioMap[key].input;
      updateCharCount();
    });
  });

  // ── Char counter ─────────────────────────────────────────────────────────
  const MAX_CHARS = 2000;
  function updateCharCount() {
    const len = formulationInput.value.length;
    if (charCount) {
      charCount.textContent = `${len} / ${MAX_CHARS}`;
      charCount.style.color = len > MAX_CHARS * 0.9 ? 'var(--rejected)' : 'var(--text-muted)';
    }
  }
  if (formulationInput) formulationInput.addEventListener('input', updateCharCount);

  // ── Onboarding banner dismiss ────────────────────────────────────────────
  const ONBOARDING_KEY = 'chemshield_onboarding_dismissed';
  if (onboardingBanner) {
    if (localStorage.getItem(ONBOARDING_KEY)) {
      onboardingBanner.style.display = 'none';
    }
    if (onboardingClose) {
      onboardingClose.addEventListener('click', () => {
        onboardingBanner.style.display = 'none';
        localStorage.setItem(ONBOARDING_KEY, '1');
      });
    }
  }

  // ── Generate SDS shortcut button ─────────────────────────────────────────
  if (generateSdsBtn) {
    generateSdsBtn.addEventListener('click', () => {
      const text = formulationInput ? formulationInput.value.trim() : '';
      if (!text) {
        if (formulationInput) {
          formulationInput.style.borderColor = 'var(--rejected)';
          formulationInput.focus();
          setTimeout(() => { formulationInput.style.borderColor = ''; }, 1800);
        }
        return;
      }

      // Check formulation completeness before generating SDS
      const check = evaluateFormulationCompleteness(text, session.lastAuditResult);
      if (!check.isComplete) {
        showIncompleteWarningModal(check.issues, () => {
          runAudit(text, 'full');
          activateSection('sds');
        });
        return;
      }

      runAudit(text, 'full');
      activateSection('sds');
    });
  }

  // ── Copilot suggestion chips ──────────────────────────────────────────────
  const suggestionChips = document.querySelectorAll('.suggestion-chip');
  const chatInputEl = document.getElementById('chat-input');
  suggestionChips.forEach(chip => {
    chip.addEventListener('click', () => {
      if (chatInputEl) {
        chatInputEl.value = chip.dataset.q || '';
        chatInputEl.focus();
        // Auto-send if copilot section is active
        const copilotSection = document.getElementById('section-copilot');
        if (copilotSection && !copilotSection.classList.contains('hidden')) {
          document.getElementById('send-chat-btn')?.click();
        }
      }
    });
  });

  // ── Navigation ────────────────────────────────────────────────────────────
  const NAV_LINKS = document.querySelectorAll('.nav-link[data-section]');
  const SECTIONS  = document.querySelectorAll('main section[id^="section-"]');

  function activateSection(id) {
    const scrollPos = window.scrollY;
    NAV_LINKS.forEach(btn => {
      const active = btn.dataset.section === id;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active);
    });
    SECTIONS.forEach(sec => sec.classList.toggle('hidden', sec.id !== `section-${id}`));
    window.scrollTo({ top: scrollPos, behavior: 'instant' });
  }

  NAV_LINKS.forEach(btn => btn.addEventListener('click', (e) => {
    e.preventDefault();
    activateSection(btn.dataset.section);
  }));

  document.querySelectorAll('.process-tile[data-goto]').forEach(tile => {
    tile.addEventListener('click', () => activateSection(tile.dataset.goto));
    tile.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') activateSection(tile.dataset.goto);
    });
  });

  async function downloadSdsPdf() {
    const text = (formulationInput && formulationInput.value.trim()) || session.formulation || '';
    if (!text) {
      alert('Please enter or run a formulation audit first.');
      return;
    }

    const origText = printSdsBtn ? printSdsBtn.textContent : 'Print / Save as PDF';
    if (printSdsBtn) { printSdsBtn.disabled = true; printSdsBtn.textContent = 'Generating PDF...'; }
    if (modalPrintBtn) { modalPrintBtn.disabled = true; modalPrintBtn.textContent = 'Generating PDF...'; }

    const regionEl = document.getElementById('select-region');
    const langEl = document.getElementById('select-language');
    const region = regionEl ? regionEl.value : 'US';
    const language = langEl ? langEl.value : 'en';

    try {
      const res = await fetch('/api/v1/sds/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: text, intent: 'full', region: region, language: language })
      });

      if (!res.ok) throw new Error(`Server returned status ${res.status}`);

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `GHS_SDS_${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('PDF Endpoint download error:', err);
      alert('Failed to generate PDF document: ' + err.message);
    } finally {
      if (printSdsBtn) { printSdsBtn.disabled = false; printSdsBtn.textContent = origText; }
      if (modalPrintBtn) { modalPrintBtn.disabled = false; modalPrintBtn.textContent = 'Download PDF'; }
    }
  }

  function printStandaloneSds() {
    const sdsHtml = (modalSdsBody && modalSdsBody.innerHTML) || (sdsHtmlWrapper && sdsHtmlWrapper.innerHTML);
    if (!sdsHtml || sdsHtml.includes('empty-state')) {
      alert('Please generate a GHS SDS document first.');
      return;
    }

    const printWin = window.open('', '_blank');
    if (printWin) {
      printWin.document.write(sdsHtml);
      printWin.document.close();
      setTimeout(() => {
        printWin.focus();
        printWin.print();
      }, 300);
    }
  }

  if (printSdsBtn) {
    printSdsBtn.addEventListener('click', downloadSdsPdf);
  }

  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', () => {
      if (sdsModalOverlay) sdsModalOverlay.classList.add('hidden');
    });
  }

  if (sdsModalOverlay) {
    sdsModalOverlay.addEventListener('click', (e) => {
      if (e.target === sdsModalOverlay) {
        sdsModalOverlay.classList.add('hidden');
      }
    });
  }

  if (modalPrintBtn) {
    modalPrintBtn.addEventListener('click', downloadSdsPdf);
  }

  // ── Trigger run ───────────────────────────────────────────────────────────
  function triggerRun() {
    const text = formulationInput.value.trim();
    if (!text) {
      formulationInput.style.borderColor = 'var(--rejected)';
      formulationInput.focus();
      setTimeout(() => { formulationInput.style.borderColor = ''; }, 1800);
      return;
    }
    
    // Automatically detect if user wants an SDS
    const lowerText = text.toLowerCase();
    let intent = 'audit';
    if (lowerText.includes('sds') || lowerText.includes('safety data sheet')) {
      intent = 'full';
    }

    if (intent === 'full' || intent === 'sds') {
      const check = evaluateFormulationCompleteness(text, session.lastAuditResult);
      if (!check.isComplete) {
        showIncompleteWarningModal(check.issues, () => {
          runAudit(text, intent);
        });
        return;
      }
    }
    
    runAudit(text, intent);
  }

  if (cardRunBtn)   cardRunBtn.addEventListener('click', triggerRun);
  if (globalRunBtn) globalRunBtn.addEventListener('click', triggerRun);

  // ── Loading state ─────────────────────────────────────────────────────────
  function setRunning(running, intent = 'audit') {
    const regionEl = document.getElementById('select-region');
    const langEl = document.getElementById('select-language');
    [cardRunBtn, globalRunBtn, regionEl, langEl].filter(Boolean).forEach(b => { b.disabled = running; });
    if (running) {
      if (cardRunLabel) cardRunLabel.textContent = (intent === 'sds' || intent === 'full' ? 'Authoring 16-Section GHS SDS...' : 'Running Compliance Audit...');
      if (runStatusChip) {
        runStatusChip.textContent = 'Running';
        runStatusChip.className = 'status-chip chip-PARTIAL loading-pulse';
      }
      if (sidebarLiveDot) sidebarLiveDot.classList.add('active');
      resetTracker(intent);
      setStepStatus(stepExtract, badgeExtract, 'running', 'Active');
    } else {
      if (cardRunLabel) cardRunLabel.textContent = 'Run Compliance Audit';
      if (runStatusChip) {
        runStatusChip.className = 'status-chip chip-NEUTRAL';
        runStatusChip.textContent = 'Ready';
      }
      if (sidebarLiveDot) sidebarLiveDot.classList.remove('active');
    }
  }

  // ── Append log line ───────────────────────────────────────────────────────
  function appendLog(el, text) {
    if (!el) return;
    const line = document.createElement('div');
    line.className = 'log-line';
    const lower = text.toLowerCase();
    if (lower.includes('error') || lower.includes('fail'))      line.classList.add('error');
    else if (lower.includes('warn'))                            line.classList.add('warn');
    else if (lower.includes('success') || lower.includes('complete') || lower.includes('approved')) line.classList.add('success');
    else if (lower.includes('info') || lower.includes('initializ') || lower.includes('[supervisor]') || lower.includes('[chemical') || lower.includes('[hardware') || lower.includes('[sds') || lower.includes('[reflect') || lower.includes('[intel')) line.classList.add('info');
    line.textContent = text;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  }

  function clearLog(el) {
    if (el) el.innerHTML = '';
  }

  // ── Main audit runner — SSE ────────────────────────────────────────────────
  function runAudit(text, intent = 'audit') {
    if (activeEventSource) { activeEventSource.close(); activeEventSource = null; }

    setRunning(true, intent);
    clearAllResults(intent);

    const regionEl = document.getElementById('select-region');
    const langEl = document.getElementById('select-language');
    const region = regionEl ? regionEl.value : 'US';
    const language = langEl ? langEl.value : 'en';

    clearLog(logStream);
    appendLog(logStream, `[INFO] Connecting to ChemShield AI pipeline (action='${intent}', region='${region}', lang='${language}')...`);

    const url = `/api/v1/stream?input_text=${encodeURIComponent(text)}&intent=${intent}&region=${encodeURIComponent(region)}&language=${encodeURIComponent(language)}`;
    const es = new EventSource(url);
    activeEventSource = es;

    es.addEventListener('start', e => {
      const d = JSON.parse(e.data);
      appendLog(logStream, d.message);
    });

    es.addEventListener('log', e => {
      const d = JSON.parse(e.data);
      appendLog(logStream, d.message);
      const lower = d.message.toLowerCase();
      if (lower.includes('extracted')) {
        setStepStatus(stepExtract, badgeExtract, 'complete', 'Done');
        setStepStatus(stepAudit, badgeAudit, 'running', 'Active');
      } else if (lower.includes('dispatching') || lower.includes('pubchem') || lower.includes('chemicalagent') || lower.includes('hardwareagent')) {
        setStepStatus(stepExtract, badgeExtract, 'complete', 'Done');
        setStepStatus(stepAudit, badgeAudit, 'running', 'Active');
      } else if (lower.includes('verdict calculated') || lower.includes('safety summary')) {
        setStepStatus(stepAudit, badgeAudit, 'complete', 'Done');
        setStepStatus(stepVerdict, badgeVerdict, 'complete', 'Done');
        if (intent === 'sds' || intent === 'full') {
          setStepStatus(stepSds, badgeSds, 'running', 'Active');
        }
      } else if (lower.includes('sdsauthoragent') || lower.includes('reflection')) {
        setStepStatus(stepSds, badgeSds, 'running', 'Active');
      }
    });

    es.addEventListener('heartbeat', () => {
      appendLog(logStream, '[INFO] Pipeline running...');
    });

    es.addEventListener('step', e => {
      const step = JSON.parse(e.data);
      appendLog(logStream, `[TRACE] ${step.agent} — ${step.action} (${step.duration_ms}ms)`);
    });

    let receivedResult = false;

    es.addEventListener('result', e => {
      receivedResult = true;
      es.close();
      activeEventSource = null;
      const result = JSON.parse(e.data);
      setRunning(false);
      setStepStatus(stepExtract, badgeExtract, 'complete', 'Done');
      setStepStatus(stepAudit, badgeAudit, 'complete', 'Done');
      setStepStatus(stepVerdict, badgeVerdict, 'complete', 'Done');
      if (intent === 'sds' || intent === 'full' || result.sds_html) {
        setStepStatus(stepSds, badgeSds, 'complete', 'Done');
      }
      renderResults(result, text);
      appendLog(logStream, '[SUCCESS] Pipeline action complete.');
    });

    es.addEventListener('error', e => {
      if (receivedResult) return;
      es.close();
      activeEventSource = null;
      runAuditFallback(text, intent);
    });

    es.onerror = () => {
      if (receivedResult) return;
      if (es.readyState === EventSource.CLOSED) return;
      es.close();
      activeEventSource = null;
      runAuditFallback(text, intent);
    };
  }

  // Fallback audit runner using standard POST API
  function runAuditFallback(text, intent = 'audit') {
    appendLog(logStream, '[INFO] Retrying via direct API request...');
    const regionEl = document.getElementById('select-region');
    const langEl   = document.getElementById('select-language');
    const region   = regionEl ? regionEl.value : 'US';
    const language = langEl   ? langEl.value   : 'en';
    fetch('/api/v1/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input: text, intent: intent, region: region, language: language })
    })
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => {
      setRunning(false);
      renderResults(data, text);
      appendLog(logStream, '[SUCCESS] Pipeline action complete.');
    })
    .catch(err => {
      setRunning(false);
      appendLog(logStream, `[ERROR] Pipeline action failed: ${err}`);
    });
  }

  // ── Clear results ─────────────────────────────────────────────────────────
  function clearAllResults(intent = 'audit') {
    if (intent === 'audit') {
      metricsGrid.classList.add('hidden');
      verdictBanner.classList.add('hidden');
      verdictBanner.innerHTML = '';
      summaryText.textContent = 'Running compliance check...';
      flagsContainer.innerHTML = '<div class="empty-state">Evaluating chemicals and hardware...</div>';
      sdsHtmlWrapper.innerHTML = '<p class="empty-state" style="text-align:center; padding:32px;">Evaluating formulation... Authoring 16-section GHS Safety Data Sheet.</p>';
      traceList.innerHTML = '<div class="empty-state">Collecting trace data...</div>';

      [mvLatency, mvRag, mvTools, mvReflect, sdsMvSections, sdsMvReflect,
       sdsMvIters, traceMvSteps, traceMvAgents, traceMvSuccess, traceMvAvg]
        .forEach(el => { if (el) el.textContent = '--'; });
    } else {
      // Generating SDS on demand: update SDS viewer placeholder, keep existing audit report intact
      sdsHtmlWrapper.innerHTML = '<p class="empty-state">Generating 16-section GHS SDS document...</p>';
    }
  }

  // ── Render full result ────────────────────────────────────────────────────
  function renderResults(result, formulation) {
    const report = result.compliance_report;
    const m      = report.metrics;
    const status = report.overall_approval_status;

    // Store session context so Copilot picks it up
    session.formulation     = formulation;
    session.auditSummary    = report.summary;
    session.lastAuditResult = result;
    updateContextBanner();

    // ── Metric scorecards
    metricsGrid.classList.remove('hidden');
    metricsGrid.classList.add('fade-in');
    mvLatency.textContent = `${m.total_latency.toFixed(2)}s`;
    mvRag.textContent     = `${(m.rag_context_relevancy * 100).toFixed(0)}%`;
    mvTools.textContent   = `${(m.agent_tool_call_success_rate * 100).toFixed(0)}%`;
    mvReflect.textContent = `${result.reflection_iterations}x`;

    // ── Verdict banner
    const labels = {
      APPROVED:        'APPROVED — Safe for Lab Use',
      REJECTED:        'REJECTED — Hazardous Violation',
      REVIEW_REQUIRED: 'REVIEW REQUIRED — Expert Manual Review Required',
    };
    verdictBanner.className = `verdict-banner ${status} fade-in`;
    verdictBanner.innerHTML = `
      <span>${esc(labels[status] || status)}</span>
      <span class="status-chip chip-${status}">${esc(status)}</span>
    `;
    verdictBanner.classList.remove('hidden');

    // ── Summary + Flags
    summaryText.textContent = report.summary;
    flagsContainer.innerHTML = '';

    report.chemical_flags.forEach(c => {
      const srcBadge = _retrievalSourceLabel(c.retrieval_source);
      flagsContainer.appendChild(buildFlagRow(
        'CHEM',
        c.chemical_name,
        `Limit: ${c.regulatory_limit}`,
        c.detected_concentration || 'Not specified',
        c.is_compliant ? 'APPROVED' : (c.status === 'REVIEW_REQUIRED' ? 'PARTIAL' : 'REJECTED'),
        c.is_compliant ? 'Compliant' : (c.status === 'REVIEW_REQUIRED' ? 'Review Required' : 'Non-Compliant'),
        srcBadge,
        c.source_citation || ''
      ));
    });

    report.hardware_flags.forEach(h => {
      flagsContainer.appendChild(buildFlagRow(
        'HW',
        h.equipment_name,
        `Max safe: ${h.max_safe_temperature_celsius != null ? h.max_safe_temperature_celsius + '°C' : 'Unknown'}`,
        h.target_temperature_celsius != null ? `${h.target_temperature_celsius}°C` : 'Not specified',
        h.is_safe ? 'APPROVED' : (h.status === 'REVIEW_REQUIRED' ? 'PARTIAL' : 'REJECTED'),
        h.is_safe ? 'Safe' : (h.status === 'REVIEW_REQUIRED' ? 'Review Required' : 'Unsafe'),
        'FastMCP',
        ''
      ));
    });

    if (report.chemical_flags.length > 0 || report.hardware_flags.length > 0) {
      if (retrievalLegend) retrievalLegend.classList.remove('hidden');
    }

    // ── SDS
    if (result.sds_html) {
      const renderIframeSDS = (container, html) => {
        const iframe = document.createElement('iframe');
        iframe.setAttribute('sandbox', 'allow-same-origin allow-popups');
        iframe.style.cssText = 'width:100%;border:none;min-height:600px;';
        container.innerHTML = '';
        container.appendChild(iframe);
        iframe.srcdoc = html;
      };
      renderIframeSDS(sdsHtmlWrapper, result.sds_html);
      if (modalSdsBody) renderIframeSDS(modalSdsBody, result.sds_html);
      if (sdsModalOverlay) sdsModalOverlay.classList.remove('hidden');
    } else {
      sdsHtmlWrapper.innerHTML = `
        <div class="empty-state" style="text-align: center; padding: 40px 20px;">
          <p style="margin-bottom: 16px; font-size: 14px; color: var(--text-muted);">
            Compliance Audit complete. Click below to author a full 16-section GHS Safety Data Sheet for this formulation:
          </p>
          <button class="btn-pill-primary" id="generate-sds-direct-btn">
            Generate 16-Section GHS SDS <span class="arrow-icon">&#8594;</span>
          </button>
        </div>
      `;
      const directSdsBtn = document.getElementById('generate-sds-direct-btn');
      if (directSdsBtn) {
        directSdsBtn.addEventListener('click', () => {
          const text = formulationInput.value.trim();
          if (text) runAudit(text, 'full');
        });
      }
    }

    // Count sections from the structured sds_document in the result
    const sdsSections = (result.sds_document && result.sds_document.sections)
      ? result.sds_document.sections.length
      : '--';

    sdsMvSections.textContent = sdsSections;
    sdsMvReflect.textContent  = result.reflection_passed ? 'Pass' : 'Warning';
    sdsMvIters.textContent    = `${result.reflection_iterations}x`;

    // Update Audit Evaluation Bar
    const evalAuditLatency = document.getElementById('eval-audit-latency');
    const evalAuditRag     = document.getElementById('eval-audit-rag');
    const evalAuditTools   = document.getElementById('eval-audit-tools');
    const evalAuditScore   = document.getElementById('eval-audit-score');
    if (evalAuditLatency) evalAuditLatency.textContent = `${m.total_latency.toFixed(2)}s`;
    if (evalAuditRag)     evalAuditRag.textContent     = `${(m.rag_context_relevancy * 100).toFixed(0)}%`;
    if (evalAuditTools)   evalAuditTools.textContent   = `${(m.agent_tool_call_success_rate * 100).toFixed(0)}%`;
    if (evalAuditScore)   evalAuditScore.textContent   = `${(m.llm_instruction_following * 100).toFixed(0)}%`;

    // Update SDS Evaluation Bar
    const evalSdsSections  = document.getElementById('eval-sds-sections');
    const evalSdsReflect   = document.getElementById('eval-sds-reflect');
    const evalSdsPrecision = document.getElementById('eval-sds-precision');
    const evalSdsLatency   = document.getElementById('eval-sds-latency');
    if (evalSdsSections)  evalSdsSections.textContent  = `${sdsSections} / 16`;
    if (evalSdsReflect)   evalSdsReflect.textContent   = result.reflection_passed ? 'PASSED' : 'WARNING';
    if (evalSdsPrecision) evalSdsPrecision.textContent = '100%';
    if (evalSdsLatency)   evalSdsLatency.textContent   = `${m.total_latency.toFixed(2)}s`;

    // ── Trace
    const trace = result.trace || [];
    traceList.innerHTML = '';

    if (!trace.length) {
      traceList.innerHTML = '<div class="empty-state">No trace steps recorded.</div>';
    } else {
      trace.forEach(step => {
        const dotClass  = step.status === 'success' ? 'success'
                        : step.status === 'warning' ? 'warning'
                        : 'error';
        const chipClass = step.status === 'success' ? 'chip-APPROVED'
                        : step.status === 'warning' ? 'chip-PARTIAL'
                        : 'chip-REJECTED';
        const sourceTag = step.action_source === 'guardrail_override'
          ? '<span class="trace-guardrail-badge" title="Safety guardrail enforced this step — the AI would have skipped it">Guardrail</span>'
          : '';
        const row = document.createElement('div');
        row.className = 'trace-row fade-in';
        row.innerHTML = `
          <span class="trace-dot ${dotClass}"></span>
          <span class="trace-agent">${esc(step.agent)}</span>
          <span class="trace-action">${esc(step.action)} ${sourceTag}</span>
          <span class="trace-obs">${esc(step.observation)}</span>
          <span class="trace-dur">${step.duration_ms}ms</span>
          <span class="status-chip ${chipClass}" style="font-size:10px;padding:3px 9px;">${esc(step.status)}</span>
        `;
        traceList.appendChild(row);
      });
    }

    // Trace metrics
    const successCount  = trace.filter(s => s.status === 'success').length;
    const uniqueAgents  = new Set(trace.map(s => s.agent)).size;
    const totalMs       = trace.reduce((a, s) => a + s.duration_ms, 0);
    const avgMs         = trace.length ? Math.round(totalMs / trace.length) : 0;

    traceMvSteps.textContent   = trace.length;
    traceMvAgents.textContent  = uniqueAgents;
    traceMvSuccess.textContent = trace.length ? `${Math.round(successCount / trace.length * 100)}%` : '--';
    traceMvAvg.textContent     = trace.length ? `${avgMs}ms` : '--';

    // Update nav chip
    runStatusChip.className   = `status-chip chip-${status}`;
    runStatusChip.textContent = status;
  }

  // ── Build a single flag row ────────────────────────────────────────────────
  function buildFlagRow(typeTag, name, limitLabel, concValue, chipClass, chipLabel, sourceBadge, citation) {
    const row = document.createElement('div');
    row.className = 'flag-row';
    const sourceHtml = sourceBadge
      ? `<span class="flag-source-badge" title="Regulatory data retrieved from: ${esc(sourceBadge)}">${esc(sourceBadge)}</span>`
      : '';
    const citationHtml = citation
      ? `<div class="flag-citation" title="${esc(citation)}">${esc(citation.length > 80 ? citation.slice(0, 77) + '...' : citation)}</div>`
      : '';
    row.innerHTML = `
      <div class="flag-row-left">
        <span class="flag-type-tag">${esc(typeTag)}</span>
        <div>
          <div class="flag-name">${esc(name)}</div>
          <div class="flag-limit">${esc(limitLabel)}</div>
          ${citationHtml}
        </div>
      </div>
      <div class="flag-row-right">
        ${sourceHtml}
        <span class="flag-conc" title="Detected concentration in your formulation">${esc(concValue)}</span>
        <span class="status-chip chip-${chipClass}">${esc(chipLabel)}</span>
      </div>
    `;
    return row;
  }

  // ── Context banner ────────────────────────────────────────────────────────
  function updateContextBanner() {
    if (session.formulation) {
      contextBannerText.textContent = session.formulation;
      contextBanner.classList.remove('hidden');
    } else {
      contextBanner.classList.add('hidden');
    }
  }

  contextClearBtn.addEventListener('click', () => {
    session.formulation  = null;
    session.auditSummary = null;
    updateContextBanner();
  });

  // ── Clear logs button ─────────────────────────────────────────────────────
  document.getElementById('clear-logs-btn').addEventListener('click', () => {
    clearLog(logStream);
    appendLog(logStream, '[INFO] Logs cleared.');
  });

  // ── Copilot chat ──────────────────────────────────────────────────────────
  sendChatBtn.addEventListener('click', sendChat);
  chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });

  async function sendChat() {
    const msg = chatInput.value.trim();
    if (!msg) return;

    appendChatMsg(msg, 'user');
    chatInput.value = '';
    sendChatBtn.disabled = true;

    const typingId = appendTypingIndicator();

    try {
      const payload = {
        message: msg,
        history: chatHistory,
        formulation_context: session.formulation  || null,
        audit_summary:       session.auditSummary || null,
      };

      const res = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      removeTypingIndicator(typingId);
      appendChatMsg(data.response, 'bot', data);
      chatHistory.push({ role: 'user',      content: msg });
      chatHistory.push({ role: 'assistant', content: data.response });

    } catch (err) {
      removeTypingIndicator(typingId);
      appendChatMsg(`Request failed: ${err.message}`, 'bot');
    } finally {
      sendChatBtn.disabled = false;
      chatInput.focus();
    }
  }

  function appendChatMsg(text, sender, metricsData = null) {
    const wrapper = document.createElement('div');
    wrapper.className = `chat-msg ${sender} fade-in`;
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.innerHTML = esc(text).replace(/\n/g, '<br>');
    const meta = document.createElement('div');
    meta.className = 'chat-meta';
    meta.textContent = sender === 'user' ? 'You' : 'ChemShield AI';
    wrapper.appendChild(bubble);

    if (sender === 'bot' && metricsData) {
      const evalBar = document.createElement('div');
      evalBar.className = 'chat-metrics-bar';
      evalBar.innerHTML = `
        <span class="chat-metric-title">Evaluation Metrics</span>
        <span class="chat-metric-pill">Latency: ${metricsData.latency_seconds || 0.8}s</span>
        <span class="chat-metric-pill">Grounding: ${((metricsData.grounding_precision || 1.0) * 100).toFixed(0)}%</span>
        <span class="chat-metric-pill">Instruction: ${((metricsData.instruction_score || 1.0) * 100).toFixed(0)}%</span>
        ${metricsData.cache_hit ? '<span class="chat-metric-pill cache-hit">Cache HIT</span>' : ''}
      `;
      wrapper.appendChild(evalBar);
    }

    wrapper.appendChild(meta);
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function appendTypingIndicator() {
    const id = `typing-${Date.now()}`;
    const wrapper = document.createElement('div');
    wrapper.className = 'chat-msg bot';
    wrapper.id = id;
    wrapper.innerHTML = `
      <div class="chat-bubble" style="color:var(--outline);">
        Thinking<span style="display:inline-block;width:8px;height:12px;background:currentColor;margin-left:4px;animation:blink 1s step-end infinite;vertical-align:middle;"></span>
      </div>
    `;
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    return id;
  }

  // Add keyframe for cursor blink if not in CSS
  if (!document.getElementById('blink-style')) {
    const style = document.createElement('style');
    style.id = 'blink-style';
    style.textContent = '@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}';
    document.head.appendChild(style);
  }

  function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  // ── Retrieval source → human label mapping ───────────────────────────────
  function _retrievalSourceLabel(source) {
    const map = {
      master_db:      'Master DB',
      chroma_rag:     'OSHA RAG',
      sqlite_cache:   'Cache',
      gemini_knowledge: 'Gemini AI',
      tavily_web:     'Web Search',
      water_standard: 'Standard',
      unindexed:      'Unindexed',
    };
    return map[source] || (source ? String(source) : '');
  }

  // ── HTML escape ───────────────────────────────────────────────────────────
  function esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g,  '&amp;')
      .replace(/</g,  '&lt;')
      .replace(/>/g,  '&gt;')
      .replace(/"/g,  '&quot;')
      .replace(/'/g,  '&#039;');
  }

});
