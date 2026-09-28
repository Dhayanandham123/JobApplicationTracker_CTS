/* ==========================================================================
   Refinement interaction layer — loaded AFTER app.js and theme-3d.js.
   Modules: toasts, resume preview panel, FIT optimize popover,
   profile photo manager, bulk selection + bulk actions.
   Uses only existing backend APIs; no mock data.
   ========================================================================== */
(function () {
    'use strict';

    /* ------------------------------------------------------------------ */
    /*  1. Toast notification system                                      */
    /* ------------------------------------------------------------------ */
    window.showToast = function showToast(message, type) {
        const container = document.getElementById('toast-container');
        if (!container) {
            alert(message);
            return;
        }
        const toast = document.createElement('div');
        toast.className = `toast toast-${type || 'info'}`;
        toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

        const msg = document.createElement('span');
        msg.className = 'toast-message';
        msg.textContent = message;

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'toast-close';
        close.setAttribute('aria-label', 'Dismiss notification');
        close.textContent = '×';
        close.addEventListener('click', () => toast.remove());

        toast.appendChild(msg);
        toast.appendChild(close);
        container.appendChild(toast);

        const timeout = type === 'error' ? 7000 : 4500;
        setTimeout(() => {
            if (toast.isConnected) toast.remove();
        }, timeout);
    };

    /* ------------------------------------------------------------------ */
    /*  2. Resume preview panel (read-only, scrollable, expand/collapse)  */
    /* ------------------------------------------------------------------ */
    async function renderResumePreview() {
        const container = document.getElementById('extracted-text-preview-container');
        const pre = document.getElementById('resume-preview-pre');
        const empty = document.getElementById('resume-preview-empty');
        const status = document.getElementById('resume-extraction-status');
        const count = document.getElementById('resume-char-count');
        if (!container || !pre) return;

        try {
            const res = await fetch('/api/resume');
            if (!res.ok) return;
            const data = await res.json();
            const text = (data.resume_text || '').trim();

            container.classList.remove('hidden');
            if (text) {
                pre.textContent = text;
                pre.classList.remove('hidden');
                if (empty) empty.classList.add('hidden');
                if (status) {
                    status.textContent = 'Extracted · ' + (data.resume_filename || 'resume');
                    status.classList.add('is-ok');
                    status.classList.remove('is-empty');
                }
                if (count) {
                    count.textContent = `${text.length.toLocaleString()} characters · ${text.split(/\n/).length.toLocaleString()} lines`;
                }
            } else {
                pre.textContent = '';
                pre.classList.add('hidden');
                if (empty) empty.classList.remove('hidden');
                if (status) {
                    status.textContent = 'No resume';
                    status.classList.add('is-empty');
                    status.classList.remove('is-ok');
                }
                if (count) count.textContent = '';
            }
        } catch (err) {
            console.error('Error rendering resume preview:', err);
        }
    }

    function initResumePreview() {
        const btn = document.getElementById('btn-toggle-extracted-text');
        const body = document.getElementById('resume-preview-body');
        const label = document.getElementById('btn-toggle-extracted-text-label');
        if (btn && body) {
            btn.addEventListener('click', () => {
                const collapsed = body.classList.toggle('collapsed');
                btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                if (label) label.textContent = collapsed ? 'Expand' : 'Collapse';
            });
        }
        const copyBtn = document.getElementById('btn-copy-resume-text');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                const pre = document.getElementById('resume-preview-pre');
                const text = pre ? pre.textContent : '';
                if (!text) return;
                try {
                    await navigator.clipboard.writeText(text);
                    window.showToast('Resume text copied to clipboard.', 'success');
                } catch (err) {
                    window.showToast('Could not copy text.', 'error');
                }
            });
        }
    }

    /* ------------------------------------------------------------------ */
    /*  3. FIT Score optimize popover                                     */
    /* ------------------------------------------------------------------ */
    let fitPopoverShownThisSession = false;
    let fitSelectedAppId = null;

    function sortRecentApps(apps) {
        return [...apps].sort((a, b) => {
            const aActive = a.status === 'Rejected' ? 1 : 0;
            const bActive = b.status === 'Rejected' ? 1 : 0;
            if (aActive !== bActive) return aActive - bActive;
            const da = a.last_updated || a.date_applied || '';
            const db = b.last_updated || b.date_applied || '';
            return db.localeCompare(da);
        });
    }

    async function populateFitPopover() {
        const options = document.getElementById('fit-optimize-options');
        const analyzeBtn = document.getElementById('btn-fit-analyze');
        const hint = document.getElementById('fit-popover-hint');
        if (!options) return;
        fitSelectedAppId = null;
        if (analyzeBtn) analyzeBtn.disabled = true;
        options.innerHTML = '<div class="fit-popover-empty">Loading recent applications…</div>';

        try {
            const res = await fetch('/applications');
            if (!res.ok) throw new Error('fetch failed');
            const apps = sortRecentApps(await res.json()).slice(0, 8);

            if (apps.length === 0) {
                options.innerHTML = '<div class="fit-popover-empty">No recent applications found.<br>Add a job application first, or use the version analysis below.</div>';
                return;
            }

            options.innerHTML = '';
            apps.forEach((app, idx) => {
                const label = document.createElement('label');
                label.className = 'fit-popover-option';
                const meta = [app.status, app.date_applied].filter(Boolean).join(' · ');
                label.innerHTML = `
                    <input type="radio" name="fit-target-job" value="${app.id}" ${idx === 0 ? '' : ''} aria-label="${escapeHtml(app.job_title)} at ${escapeHtml(app.company_name)}">
                    <span>
                        <span class="fit-option-title">${escapeHtml(app.job_title)} — ${escapeHtml(app.company_name)}</span><br>
                        <span class="fit-option-meta">${escapeHtml(meta)}</span>
                    </span>
                `;
                const radio = label.querySelector('input');
                radio.addEventListener('change', () => {
                    options.querySelectorAll('.fit-popover-option').forEach(o => o.classList.remove('is-selected'));
                    label.classList.add('is-selected');
                    fitSelectedAppId = app.id;
                    if (analyzeBtn) analyzeBtn.disabled = false;
                    if (hint) hint.textContent = '';
                });
                options.appendChild(label);
            });
        } catch (err) {
            console.error('Error populating fit popover:', err);
            options.innerHTML = '<div class="fit-popover-empty">Could not load applications.</div>';
        }
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function openFitPopover() {
        const pop = document.getElementById('fit-optimize-popover');
        if (!pop) return;
        pop.classList.remove('hidden');
        populateFitPopover();
        const closeBtn = document.getElementById('btn-fit-popover-close');
        if (closeBtn) closeBtn.focus();
    }

    function closeFitPopover() {
        const pop = document.getElementById('fit-optimize-popover');
        if (pop) pop.classList.add('hidden');
    }

    async function analyzeFitForSelectedJob() {
        const hint = document.getElementById('fit-popover-hint');
        const analyzeBtn = document.getElementById('btn-fit-analyze');
        if (!fitSelectedAppId) {
            if (hint) hint.textContent = 'Select a job first.';
            return;
        }
        closeFitPopover();
        const resultPanel = document.getElementById('fit-analysis-result');

        // Loading state inside the dedicated result panel (chat stays compact).
        if (resultPanel) {
            resultPanel.classList.remove('hidden');
            resultPanel.innerHTML = `
                <div class="fit-result-loading" role="status">
                    <div class="typing-dots"><span></span><span></span><span></span></div>
                    <p>Analyzing your active resume against the selected job…</p>
                </div>`;
            resultPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        if (analyzeBtn) analyzeBtn.disabled = true;

        try {
            const res = await fetch('/api/fit-score/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ application_id: fitSelectedAppId })
            });
            const data = await res.json();
            if (res.ok && data.success && data.analysis) {
                renderFitAnalysis(data);
            } else {
                renderFitError(data.error || 'The AI analysis could not be completed.', data.retryable !== false);
            }
        } catch (err) {
            console.error('FIT analysis error:', err);
            renderFitError('Could not reach the analysis service. Check your connection and retry.', true);
        } finally {
            if (analyzeBtn) analyzeBtn.disabled = !fitSelectedAppId;
        }
    }

    function fitStatusChip(status) {
        const labels = {
            PRESENT: 'Present',
            MISSING: 'Missing',
            POTENTIALLY_RELEVANT: 'Potentially relevant',
            NEEDS_VERIFICATION: 'Needs verification'
        };
        const key = String(status || '').toUpperCase();
        return `<span class="fit-chip fit-status-${key.toLowerCase()}">${escapeHtml(labels[key] || labels.NEEDS_VERIFICATION)}</span>`;
    }

    function scoreBand(score) {
        if (score >= 75) return 'Strong Match';
        if (score >= 50) return 'Moderate Match';
        return 'Needs Work';
    }

    /* Structured FIT rendering — components only, never raw JSON/markdown. */
    function renderFitAnalysis(data) {
        const panel = document.getElementById('fit-analysis-result');
        if (!panel) return;
        const a = data.analysis;
        const score = Math.max(0, Math.min(100, parseInt(a.fit_score, 10) || 0));
        const scoreNote = data.authoritative_fit_score != null
            ? `Application Fit Score: ${data.authoritative_fit_score}% (authoritative)`
            : 'AI assessment score (no deterministic score saved for this job yet)';
        const target = data.target_job || {};
        const resumeLine = escapeHtml(data.resume_filename || 'Active resume');

        const strengths = (a.strengths || []).map(s => `
            <li class="fit-item">
                <span class="fit-check" aria-hidden="true">✓</span>
                <div>
                    <div class="fit-item-title">${escapeHtml(s.title)} ${fitStatusChip(s.status)}</div>
                    ${s.detail ? `<div class="fit-item-detail">${escapeHtml(s.detail)}</div>` : ''}
                </div>
            </li>`).join('');

        const improvements = (a.improvements || []).map(s => `
            <li class="fit-item">
                <span class="fit-prio fit-prio-${escapeHtml(String(s.priority || 'MEDIUM'))}" aria-label="Priority ${escapeHtml(String(s.priority || 'MEDIUM'))}">${escapeHtml(String(s.priority || 'MEDIUM'))}</span>
                <div>
                    <div class="fit-item-title">${escapeHtml(s.title)} ${fitStatusChip(s.status)}</div>
                    ${s.detail ? `<div class="fit-item-detail">${escapeHtml(s.detail)}</div>` : ''}
                    ${s.evidence ? `<div class="fit-item-evidence">Evidence: ${escapeHtml(s.evidence)}</div>` : ''}
                </div>
            </li>`).join('');

        const kwPresent = (a.keywords_present || []).map(k =>
            `<span class="fit-kw fit-kw-present">${escapeHtml(k.keyword)}</span>`).join('');
        const kwMissing = (a.keywords_missing || []).map(k =>
            `<span class="fit-kw fit-kw-missing">${escapeHtml(k.keyword)}</span>`).join('');

        panel.classList.remove('hidden');
        panel.innerHTML = `
            <div class="card-header-flex">
                <div>
                    <h4>Resume Analysis — ${escapeHtml(target.role || '')} at ${escapeHtml(target.company || '')}</h4>
                    <p class="analytics-subtitle" style="margin:0;">Based on ${resumeLine} · ${escapeHtml(scoreNote)}</p>
                </div>
                <button type="button" class="btn-text" id="btn-fit-result-dismiss">Dismiss</button>
            </div>
            <div class="fit-score-hero">
                <div class="fit-score-ring" role="img" aria-label="Fit score ${score} percent, ${scoreBand(score)}">
                    <span class="fit-score-number">${score}%</span>
                </div>
                <div>
                    <div class="fit-score-band">${scoreBand(score)}</div>
                    <p class="fit-summary">${escapeHtml(a.summary || '')}</p>
                </div>
            </div>
            <div class="fit-result-grid">
                <section aria-label="Strengths">
                    <h5 class="fit-section-title">Strong Matches</h5>
                    ${strengths ? `<ul class="fit-list">${strengths}</ul>` : '<p class="fit-empty">No verified strengths returned.</p>'}
                </section>
                <section aria-label="Priority improvements">
                    <h5 class="fit-section-title">Priority Improvements</h5>
                    ${improvements ? `<ul class="fit-list">${improvements}</ul>` : '<p class="fit-empty">No improvements suggested.</p>'}
                </section>
            </div>
            <section aria-label="Keywords">
                <h5 class="fit-section-title">Keywords</h5>
                <div class="fit-kw-group"><span class="fit-kw-label">Present</span>${kwPresent || '<span class="fit-empty">—</span>'}</div>
                <div class="fit-kw-group"><span class="fit-kw-label">Missing / verify</span>${kwMissing || '<span class="fit-empty">—</span>'}</div>
            </section>
            ${a.final_advice ? `<p class="fit-advice">${escapeHtml(a.final_advice)}</p>` : ''}
            <p class="fit-grounding-note">Recommendations are grounded in your active resume and this job description. Items marked “Needs verification” come from profile data not confirmed in the resume.</p>
        `;
        const dismiss = document.getElementById('btn-fit-result-dismiss');
        if (dismiss) dismiss.addEventListener('click', () => panel.classList.add('hidden'));
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function renderFitError(message, retryable) {
        const panel = document.getElementById('fit-analysis-result');
        if (!panel) {
            window.showToast(message, 'error');
            return;
        }
        panel.classList.remove('hidden');
        panel.innerHTML = `
            <div class="fit-result-error" role="alert">
                <h4>Analysis unavailable</h4>
                <p>${escapeHtml(message)}</p>
                <div class="fit-error-actions">
                    ${retryable ? '<button type="button" class="btn btn-sm btn-primary" id="btn-fit-retry">Retry analysis</button>' : ''}
                    <button type="button" class="btn btn-sm btn-outline" id="btn-fit-error-dismiss">Dismiss</button>
                </div>
            </div>`;
        const retry = document.getElementById('btn-fit-retry');
        if (retry) retry.addEventListener('click', analyzeFitForSelectedJob);
        const dismiss = document.getElementById('btn-fit-error-dismiss');
        if (dismiss) dismiss.addEventListener('click', () => panel.classList.add('hidden'));
    }

    function initFitPopover() {
        const openBtn = document.getElementById('btn-fit-optimize');
        if (openBtn) openBtn.addEventListener('click', openFitPopover);
        const closeBtn = document.getElementById('btn-fit-popover-close');
        if (closeBtn) closeBtn.addEventListener('click', closeFitPopover);
        const analyzeBtn = document.getElementById('btn-fit-analyze');
        if (analyzeBtn) analyzeBtn.addEventListener('click', analyzeFitForSelectedJob);
    }

    /* ------------------------------------------------------------------ */
    /*  4. Profile photo manager                                          */
    /* ------------------------------------------------------------------ */
    function setAvatarImages(url) {
        ['profile-photo-img'].forEach(() => {});
        const managerPreview = document.getElementById('profile-photo-manager-preview');
        if (managerPreview) {
            if (url) {
                managerPreview.innerHTML = `<img src="${url}" alt="Profile photo" class="avatar-img" id="profile-photo-img">`;
            } else {
                const nameEl = document.getElementById('profile-header-name');
                const initial = ((nameEl ? nameEl.textContent : '') || 'U').trim().charAt(0).toUpperCase() || 'U';
                managerPreview.innerHTML = `<span id="profile-photo-initials" aria-hidden="true">${escapeHtml(initial)}</span>`;
            }
        }
        const headerPreview = document.getElementById('profile-avatar-preview');
        if (headerPreview) {
            if (url) {
                headerPreview.innerHTML = `<img src="${url}" alt="Avatar" class="avatar-img">`;
            } else {
                const nameEl = document.getElementById('profile-header-name');
                const initial = ((nameEl ? nameEl.textContent : '') || 'U').trim().charAt(0).toUpperCase() || 'U';
                headerPreview.textContent = initial;
            }
        }
        document.querySelectorAll('.user-avatar').forEach(slot => {
            if (url) {
                slot.innerHTML = `<img src="${url}" alt="Profile" class="avatar-img">`;
            }
        });
    }

    function initPhotoManager() {
        const changeBtn = document.getElementById('btn-photo-change');
        const removeBtn = document.getElementById('btn-photo-remove');
        const fileInput = document.getElementById('profile-photo-input');
        const status = document.getElementById('profile-photo-status');
        if (!changeBtn || !fileInput) return;

        const setStatus = (msg, isError) => {
            if (!status) return;
            status.textContent = msg;
            status.className = 'save-status-text ' + (msg ? (isError ? 'save-status-error' : 'save-status-success') : '');
        };

        changeBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', async () => {
            const file = fileInput.files && fileInput.files[0];
            fileInput.value = '';
            if (!file) return;

            const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
            if (!validTypes.includes(file.type)) {
                setStatus('Unsupported format. Use JPG, PNG, or WEBP.', true);
                return;
            }
            if (file.size > 2 * 1024 * 1024) {
                setStatus('Photo is too large. Maximum size is 2 MB.', true);
                return;
            }

            // Instant local preview
            const reader = new FileReader();
            reader.onload = (e) => setAvatarImages(e.target.result);
            reader.readAsDataURL(file);

            setStatus('Uploading…', false);
            const formData = new FormData();
            formData.append('photo', file);
            try {
                const res = await fetch('/api/profile/photo', { method: 'POST', body: formData });
                const data = await res.json();
                if (res.ok && data.success) {
                    setAvatarImages(data.avatar_url + '?t=' + Date.now());
                    setStatus('Photo updated!', false);
                    setTimeout(() => setStatus('', false), 2500);
                } else {
                    setStatus(data.error || 'Upload failed.', true);
                }
            } catch (err) {
                console.error('Photo upload error:', err);
                setStatus('Error connecting to server.', true);
            }
        });

        if (removeBtn) {
            removeBtn.addEventListener('click', async () => {
                setStatus('Removing…', false);
                try {
                    const res = await fetch('/api/profile/photo', { method: 'DELETE' });
                    if (res.ok) {
                        setAvatarImages(null);
                        setStatus('Photo removed.', false);
                        setTimeout(() => setStatus('', false), 2500);
                    } else {
                        setStatus('Could not remove photo.', true);
                    }
                } catch (err) {
                    setStatus('Error connecting to server.', true);
                }
            });
        }
    }

    /* ------------------------------------------------------------------ */
    /*  5. Bulk selection + bulk actions                                  */
    /* ------------------------------------------------------------------ */
    const selectedIds = new Set();
    let pendingBulkAction = null;

    function cardId(card) {
        const checkbox = card.querySelector('[data-card-select]');
        if (checkbox) return parseInt(checkbox.getAttribute('data-card-select'), 10);
        return parseInt(card.getAttribute('data-id'), 10);
    }

    function refreshBulkBar() {
        const bar = document.getElementById('bulk-action-bar');
        const count = document.getElementById('bulk-selected-count');
        if (!bar || !count) return;
        const n = selectedIds.size;
        count.textContent = n === 0 ? 'Nothing selected'
            : n === 1 ? '1 application selected'
            : `${n} applications selected`;
        const visible = n > 0;
        bar.classList.toggle('hidden', !visible);
        // Lift the fixed AI dock above the sticky toolbar so the two can
        // never overlap, regardless of theme, viewport, or button text.
        requestAnimationFrame(() => {
            const lift = visible ? Math.ceil(bar.getBoundingClientRect().height + 40) : 24;
            document.documentElement.style.setProperty('--ai-dock-bottom', `${lift}px`);
        });
    }

    function syncCardSelectionUI() {
        document.querySelectorAll('.app-card').forEach(card => {
            const id = cardId(card);
            const checkbox = card.querySelector('[data-card-select]');
            const selected = selectedIds.has(id);
            card.classList.toggle('card-selected', selected);
            if (checkbox && checkbox.checked !== selected) checkbox.checked = selected;
        });
        syncColumnHeaders();
        refreshBulkBar();
    }

    /* Column-level tri-state selection, derived from the DOM data model. */
    function columnScope(status) {
        const col = document.querySelector(`.status-column[data-column="${String(status).replace(/"/g, '')}"]`);
        return col ? col.querySelector('.column-cards-container') : null;
    }

    function columnCardIds(scope) {
        if (!scope) return [];
        return [...scope.querySelectorAll('.app-card')]
            .map(cardId)
            .filter(id => id && !isNaN(id));
    }

    function toggleColumnSelection(status, select) {
        const ids = columnCardIds(columnScope(status));
        if (select) ids.forEach(id => selectedIds.add(id));
        else ids.forEach(id => selectedIds.delete(id));
        syncCardSelectionUI();
    }

    function syncColumnHeaders() {
        document.querySelectorAll('.status-column[data-column]').forEach(col => {
            const header = col.querySelector('[data-column-select]');
            if (!header) return;
            const ids = columnCardIds(col.querySelector('.column-cards-container'));
            const selected = ids.filter(id => selectedIds.has(id)).length;
            const all = ids.length > 0 && selected === ids.length;
            const some = selected > 0 && !all;
            header.checked = all;
            header.indeterminate = some;
            const label = header.closest('.card-select');
            if (label) label.classList.toggle('is-indeterminate', some);
            const text = label ? label.querySelector('.column-select-text') : null;
            if (text) text.textContent = all && ids.length > 0 ? 'Deselect all' : 'Select all';
        });
    }

    function visibleCards() {
        return [...document.querySelectorAll('.app-card')].filter(card => {
            if (card.classList.contains('hidden')) return false;
            if (card.closest('.hidden')) return false;
            return cardId(card) && !isNaN(cardId(card));
        });
    }

    function initBulkSelection() {
        // ONE centralized selection state (selectedIds) drives card boxes,
        // column headers, toolbar actions, and the count — nothing keeps a
        // private copy. Statuses/columns are discovered from data attributes,
        // never hardcoded.
        //
        // Single-card actions (status dropdown, delete) live in app.js and
        // announce board changes via `kanban:changed`; we prune dead ids and
        // re-sync headers so selection never references removed cards.
        document.addEventListener('kanban:changed', (e) => {
            const removed = e && e.detail && e.detail.removedId;
            if (removed != null) selectedIds.delete(parseInt(removed, 10));
            // Prune any ids no longer present anywhere on the board.
            const live = new Set(
                [...document.querySelectorAll('.app-card')]
                    .map(cardId)
                    .filter(id => id && !isNaN(id))
            );
            [...selectedIds].forEach(id => { if (!live.has(id)) selectedIds.delete(id); });
            syncCardSelectionUI();
        });
        document.addEventListener('change', (e) => {
            const target = e.target.closest ? e.target.closest('[data-card-select],[data-column-select]') : null;
            if (!target) return;
            if (target.hasAttribute('data-card-select')) {
                const id = parseInt(target.getAttribute('data-card-select'), 10);
                if (isNaN(id)) return;
                if (target.checked) selectedIds.add(id);
                else selectedIds.delete(id);
                syncCardSelectionUI();
            } else if (target.hasAttribute('data-column-select')) {
                toggleColumnSelection(target.getAttribute('data-column-select'), target.checked);
            }
        });

        const btnAll = document.getElementById('btn-bulk-select-all');
        if (btnAll) btnAll.addEventListener('click', () => {
            visibleCards().forEach(card => selectedIds.add(cardId(card)));
            syncCardSelectionUI();
        });

        const btnStale = document.getElementById('btn-bulk-select-stale');
        if (btnStale) btnStale.addEventListener('click', () => {
            const stale = visibleCards().filter(card => card.classList.contains('stale-highlight'));
            if (stale.length === 0) {
                window.showToast('No stale applications among visible cards.', 'info');
                return;
            }
            stale.forEach(card => selectedIds.add(cardId(card)));
            syncCardSelectionUI();
            window.showToast(`${stale.length} stale application${stale.length === 1 ? '' : 's'} selected.`, 'info');
        });

        const btnClear = document.getElementById('btn-bulk-clear');
        if (btnClear) btnClear.addEventListener('click', clearBulkSelection);

        const btnStatus = document.getElementById('btn-bulk-status');
        if (btnStatus) btnStatus.addEventListener('click', () => {
            if (selectedIds.size === 0) return;
            const target = document.getElementById('bulk-status-select').value;
            runBulkAction('status', { status: target }, false);
        });

        const btnArchive = document.getElementById('btn-bulk-archive');
        if (btnArchive) btnArchive.addEventListener('click', () => {
            if (selectedIds.size === 0) return;
            openBulkConfirm(
                `Archive ${selectedIds.size} application${selectedIds.size === 1 ? '' : 's'}?`,
                'Archived applications will no longer appear in your active tracker. You can restore them later.',
                'Archive',
                () => runBulkAction('archive', {}, true)
            );
        });

        const btnDelete = document.getElementById('btn-bulk-delete');
        if (btnDelete) btnDelete.addEventListener('click', () => {
            if (selectedIds.size === 0) return;
            openBulkConfirm(
                `Remove ${selectedIds.size} application${selectedIds.size === 1 ? '' : 's'}?`,
                'This permanently deletes the selected applications. This action cannot be undone.',
                'Remove',
                () => runBulkAction('delete', {}, true)
            );
        });

        initBulkConfirmModal();
    }

    function clearBulkSelection() {
        selectedIds.clear();
        syncCardSelectionUI();
    }

    function openBulkConfirm(title, message, okLabel, onConfirm) {
        const modal = document.getElementById('bulk-confirm-modal');
        const titleEl = document.getElementById('bulk-confirm-title');
        const msgEl = document.getElementById('bulk-confirm-message');
        const okBtn = document.getElementById('btn-bulk-confirm-ok');
        if (!modal || !titleEl || !msgEl || !okBtn) {
            if (confirm(`${title}\n\n${message}`)) onConfirm();
            return;
        }
        titleEl.textContent = title;
        msgEl.textContent = message;
        okBtn.textContent = okLabel;
        okBtn.className = okLabel === 'Remove' ? 'btn btn-danger' : 'btn btn-primary';
        pendingBulkAction = onConfirm;
        modal.classList.remove('hidden');
        okBtn.focus();
    }

    function closeBulkConfirm() {
        const modal = document.getElementById('bulk-confirm-modal');
        if (modal) modal.classList.add('hidden');
        pendingBulkAction = null;
    }

    function initBulkConfirmModal() {
        const okBtn = document.getElementById('btn-bulk-confirm-ok');
        const cancelBtn = document.getElementById('btn-bulk-confirm-cancel');
        const xBtn = document.getElementById('btn-bulk-confirm-cancel-x');
        if (okBtn) okBtn.addEventListener('click', () => {
            const fn = pendingBulkAction;
            closeBulkConfirm();
            if (fn) fn();
        });
        if (cancelBtn) cancelBtn.addEventListener('click', closeBulkConfirm);
        if (xBtn) xBtn.addEventListener('click', closeBulkConfirm);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeBulkConfirm();
                closeFitPopover();
            }
        });
    }

    async function runBulkAction(action, extra, destructive) {
        const ids = [...selectedIds];
        if (ids.length === 0) return;

        const payload = Object.assign({ action, ids }, extra || {});
        let result = null;
        try {
            const res = await fetch('/api/applications/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            result = await res.json();
            if (!res.ok) throw new Error(result.error || 'Request failed');
        } catch (err) {
            console.error('Bulk action error:', err);
            window.showToast(err.message || 'Bulk action failed. Please try again.', 'error');
            return;
        }

        const updatedSet = new Set(result.updated || []);
        const failedSet = new Set((result.failed || []).map(f => f.id));

        if (action === 'status' && payload.status) {
            applyBulkStatusToDOM([...updatedSet], payload.status);
        } else if (action === 'archive' || action === 'delete') {
            [...updatedSet].forEach(id => {
                document.querySelectorAll(`.app-card`).forEach(card => {
                    if (cardId(card) === id) card.remove();
                });
                selectedIds.delete(id);
            });
            if (typeof updateEmptyStates === 'function') updateEmptyStates();
            if (typeof recalculateCounters === 'function') recalculateCounters();
        }

        // Keep failed selections so the user can retry/review.
        failedSet.forEach(() => {});
        syncCardSelectionUI();

        if ((result.failed || []).length === 0) {
            window.showToast(result.message || 'Bulk update complete.', 'success');
            if (!destructive) { /* selection retained for further actions */ }
            else clearBulkSelection();
        } else {
            window.showToast(
                `${result.message || 'Partial update.'} (${(result.failed || []).length} failed — selection kept for retry.)`,
                'warning'
            );
        }
    }

    function applyBulkStatusToDOM(ids, newStatus) {
        const newColumn = document.getElementById(`cards-${newStatus}`);
        ids.forEach(id => {
            document.querySelectorAll('.app-card').forEach(card => {
                if (cardId(card) !== id) return;
                const oldStatus = card.getAttribute('data-status');
                card.setAttribute('data-status', newStatus);
                const sel = card.querySelector('select.status-dropdown');
                if (sel) {
                    sel.value = newStatus;
                    sel.className = `status-dropdown status-dropdown-full status-pill-${newStatus.toLowerCase()}`;
                }
                if (oldStatus) {
                    card.classList.remove(`status-accent-${oldStatus.toLowerCase()}`);
                    card.classList.add(`status-accent-${newStatus.toLowerCase()}`);
                }
                if (card.closest('.column-cards-container') && newColumn && card.closest('.column-cards-container') !== newColumn) {
                    newColumn.insertBefore(card, newColumn.querySelector('.empty-state') || null);
                }
            });
        });
        if (typeof updateEmptyStates === 'function') updateEmptyStates();
        if (typeof recalculateCounters === 'function') recalculateCounters();
    }

    /* ------------------------------------------------------------------ */
    /*  6. View-change hooks                                              */
    /* ------------------------------------------------------------------ */
    function initViewHooks() {
        window.addEventListener('resize', () => {
            if (selectedIds.size > 0) refreshBulkBar();
        });
        if (typeof window.switchView !== 'function') return;
        const original = window.switchView;
        window.switchView = function (viewName) {
            original(viewName);
            if (viewName === 'fit-score') {
                renderResumePreview();
                if (!fitPopoverShownThisSession) {
                    fitPopoverShownThisSession = true;
                    setTimeout(openFitPopover, 450);
                }
            } else {
                closeFitPopover();
            }
            if (viewName !== 'dashboard') {
                clearBulkSelection();
            }
        };
    }

    /* ------------------------------------------------------------------ */
    /*  Init                                                              */
    /* ------------------------------------------------------------------ */
    document.addEventListener('DOMContentLoaded', () => {
        initResumePreview();
        initFitPopover();
        initPhotoManager();
        initBulkSelection();
        initViewHooks();
        // If landing directly on fit-score via ?view=fit-score
        try {
            const params = new URLSearchParams(window.location.search);
            if (params.get('view') === 'fit-score') {
                renderResumePreview();
            }
        } catch (err) { /* ignore */ }
    });
})();
