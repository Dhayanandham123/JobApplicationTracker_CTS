document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
    initNavigationEvents();
    initSearchFilter();
    initModalEvents();
    initCalendarEvents();
    initAnalyticsEvents();
    initDetailsEvents();
    initAutoFillEvents();
    initModalDismissibility();
    initChatbot();
    initProfileAndSettingsEvents();
    initFitScoreEvents();
    initResumeVersionsEvents();
    initEmailIntelligenceEvents();
    populateResumeVersionSelects();
    recalculateCounters();
    loadDashboardEmailUpdates();
});

function initThemeToggle() {
    const toggleBtn = document.getElementById('theme-toggle-btn');
    const moonIcon = document.getElementById('theme-icon-moon');
    const sunIcon = document.getElementById('theme-icon-sun');

    // 1. Check local storage first for instant load
    const savedTheme = localStorage.getItem('app-theme');
    if (savedTheme === 'dark') {
        document.body.setAttribute('data-theme', 'dark');
        if (moonIcon) moonIcon.classList.add('hidden');
        if (sunIcon) sunIcon.classList.remove('hidden');
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isDark = document.body.getAttribute('data-theme') === 'dark';
            if (isDark) {
                document.body.removeAttribute('data-theme');
                localStorage.setItem('app-theme', 'light');
                if (moonIcon) moonIcon.classList.remove('hidden');
                if (sunIcon) sunIcon.classList.add('hidden');
            } else {
                document.body.setAttribute('data-theme', 'dark');
                localStorage.setItem('app-theme', 'dark');
                if (moonIcon) moonIcon.classList.add('hidden');
                if (sunIcon) sunIcon.classList.remove('hidden');
            }

            // Sync with backend settings silently if the dropdown exists
            const themeSelect = document.getElementById('setting-theme');
            if (themeSelect) {
                themeSelect.value = isDark ? 'light' : 'dark';
                themeSelect.dispatchEvent(new Event('change'));
            }
        });
    }
}

// --------------------------------------------------------------------------
// 1. Search Filter Functionality
// --------------------------------------------------------------------------
function initSearchFilter() {
    const searchInput = document.getElementById('search-input');
    const searchClear = document.getElementById('search-clear');

    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        
        if (query.length > 0) {
            searchClear.classList.remove('hidden');
        } else {
            searchClear.classList.add('hidden');
        }

        filterCards(query);
    });

    searchClear.addEventListener('click', () => {
        searchInput.value = '';
        searchClear.classList.add('hidden');
        filterCards('');
    });
}

function filterCards(query) {
    const cards = document.querySelectorAll('.app-card');

    cards.forEach(card => {
        const company = card.dataset.company || '';
        const title = card.dataset.title || '';

        if (company.includes(query) || title.includes(query)) {
            card.classList.remove('hidden');
        } else {
            card.classList.add('hidden');
        }
    });

    updateEmptyStates();
}

function updateEmptyStates() {
    const columns = ['Applied', 'Interviewing', 'Offered', 'Rejected'];

    columns.forEach(col => {
        const container = document.getElementById(`cards-${col}`);
        if (!container) return;

        const visibleCards = container.querySelectorAll('.app-card:not(.hidden)');
        const emptyState = container.querySelector('.empty-state');

        if (emptyState) {
            if (visibleCards.length === 0) {
                emptyState.classList.remove('hidden');
            } else {
                emptyState.classList.add('hidden');
            }
        }
    });
}

// --------------------------------------------------------------------------
// 2. Status Dropdown Inline Update
// --------------------------------------------------------------------------
async function updateApplicationStatus(appId, newStatus) {
    const card = document.querySelector(`.app-card[data-id="${appId}"]`);
    if (!card) return;

    try {
        const response = await fetch(`/applications/${appId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });

        if (!response.ok) {
            throw new Error('Failed to update status');
        }

        const updatedApp = await response.json();

        // Inline update instead of reload
        const oldStatus = card.dataset.status;
        const allCards = document.querySelectorAll(`.app-card[data-id="${appId}"]`);
        const newColumn = document.getElementById(`cards-${newStatus}`);

        allCards.forEach(c => {
            c.dataset.status = newStatus;
            const sel = c.querySelector('select.status-dropdown');
            if (sel) {
                sel.value = newStatus;
                sel.className = `status-dropdown status-dropdown-full status-pill-${newStatus.toLowerCase()}`;
            }
            c.classList.remove(`status-accent-${oldStatus.toLowerCase()}`);
            c.classList.add(`status-accent-${newStatus.toLowerCase()}`);
            
            if (c.closest('.column-cards-container')) {
                if (newColumn) {
                    newColumn.insertBefore(c, newColumn.querySelector('.empty-state') || null);
                }
            }
        });

        // Check empty states
        document.querySelectorAll('.column-cards-container').forEach(container => {
            const visibleCards = container.querySelectorAll('.app-card:not(.hidden)');
            const emptyState = container.querySelector('.empty-state');
            if (emptyState) {
                if (visibleCards.length === 0) {
                    emptyState.classList.remove('hidden');
                } else {
                    emptyState.classList.add('hidden');
                }
            }
        });

        recalculateCounters();

    } catch (err) {
        console.error('Error updating status:', err);
        alert('Error updating status. Please try again.');
    }

    // Notify selection/other overlays that board membership changed.
    document.dispatchEvent(new CustomEvent('kanban:changed'));
}

// --------------------------------------------------------------------------
// 3. Notes Panel Functions
// --------------------------------------------------------------------------
function toggleNotesPanel(appId) {
    const content = document.getElementById(`notes-content-${appId}`);
    const toggleBtn = content.previousElementSibling;

    if (content) {
        content.classList.toggle('hidden');
        if (toggleBtn) {
            toggleBtn.classList.toggle('expanded');
        }
    }
}

async function saveNotes(appId) {
    const textarea = document.getElementById(`notes-text-${appId}`);
    if (!textarea) return;

    const notesText = textarea.value;

    try {
        const response = await fetch(`/applications/${appId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ notes: notesText })
        });

        if (!response.ok) {
            throw new Error('Failed to save notes');
        }

        // Brief visual confirmation
        const saveBtn = textarea.nextElementSibling.querySelector('button');
        if (saveBtn) {
            const originalText = saveBtn.innerText;
            saveBtn.innerText = 'Saved!';
            saveBtn.style.backgroundColor = '#10b981';
            setTimeout(() => {
                saveBtn.innerText = originalText;
                saveBtn.style.backgroundColor = '';
            }, 1800);
        }
    } catch (err) {
        console.error('Error saving notes:', err);
        alert('Could not save notes. Please try again.');
    }
}

// --------------------------------------------------------------------------
// 4. Application Counters Calculation
// --------------------------------------------------------------------------
function recalculateCounters() {
    const cards = document.querySelectorAll('.dashboard-board .app-card');
    
    let counts = {
        total: cards.length,
        Applied: 0,
        Interviewing: 0,
        Offered: 0,
        Rejected: 0,
        needs_followup: 0
    };

    cards.forEach(card => {
        const status = card.dataset.status;
        if (counts[status] !== undefined) {
            counts[status]++;
        }
        if (card.classList.contains('stale-highlight')) {
            counts.needs_followup++;
        }
    });

    // Update Header Counter Bar (if present)
    const countTotal = document.getElementById('count-total');
    if (countTotal) countTotal.innerText = counts.total;
    const countApplied = document.getElementById('count-applied');
    if (countApplied) countApplied.innerText = counts.Applied;
    const countInterviewing = document.getElementById('count-interviewing');
    if (countInterviewing) countInterviewing.innerText = counts.Interviewing;
    const countOffered = document.getElementById('count-offered');
    if (countOffered) countOffered.innerText = counts.Offered;
    const countRejected = document.getElementById('count-rejected');
    if (countRejected) countRejected.innerText = counts.Rejected;
    
    const followupElem = document.getElementById('count-followup');
    if (followupElem) {
        followupElem.innerText = counts.needs_followup;
        const followupBadge = followupElem.closest('.counter-badge');
        if (followupBadge) {
            if (counts.needs_followup > 0) {
                followupBadge.classList.add('active-alert');
            } else {
                followupBadge.classList.remove('active-alert');
            }
        }
    }

    // Update Column Header Count Badges
    ['Applied', 'Interviewing', 'Offered', 'Rejected'].forEach(col => {
        const badge = document.getElementById(`col-count-${col}`);
        if (badge) {
            badge.innerText = counts[col];
        }
    });
}

// --------------------------------------------------------------------------
// 5. Add Application & Delete Modals
// --------------------------------------------------------------------------
let targetDeleteId = null;

function initModalEvents() {
    // Add Modal Elements
    const addModal = document.getElementById('add-modal');
    const openBtn = document.getElementById('btn-open-modal');
    const closeBtn = document.getElementById('modal-close-btn');
    const cancelBtn = document.getElementById('modal-cancel-btn');
    const addForm = document.getElementById('add-app-form');

    if (openBtn && addModal) {
        openBtn.addEventListener('click', () => addModal.classList.remove('hidden'));
    }

    const closeAddModal = () => {
        if (addModal) addModal.classList.add('hidden');
        if (addForm) addForm.reset();
    };

    if (closeBtn) closeBtn.addEventListener('click', closeAddModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeAddModal);

    // Duplicate Modal Elements
    const duplicateModal = document.getElementById('duplicate-modal');
    const dupCloseBtn = document.getElementById('duplicate-modal-close');
    const dupViewBtn = document.getElementById('duplicate-view-btn');
    const dupAddBtn = document.getElementById('duplicate-add-btn');
    const dupCompanyName = document.getElementById('duplicate-company-name');
    const dupJobTitle = document.getElementById('duplicate-job-title');

    let currentPendingPayload = null;
    let existingDuplicateId = null;

    const closeDuplicateModal = () => {
        if (duplicateModal) duplicateModal.classList.add('hidden');
    };
    if (dupCloseBtn) dupCloseBtn.addEventListener('click', closeDuplicateModal);

    if (dupViewBtn) {
        dupViewBtn.addEventListener('click', () => {
            closeDuplicateModal();
            closeAddModal();
            if (existingDuplicateId) {
                // Find card, highlight, and pulse
                const existingCard = document.querySelector(`[data-id="${existingDuplicateId}"]`);
                if (existingCard) {
                    existingCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    existingCard.classList.add('app-card-highlight-pulse');
                    setTimeout(() => existingCard.classList.remove('app-card-highlight-pulse'), 3000);
                }
            }
        });
    }

    if (dupAddBtn) {
        dupAddBtn.addEventListener('click', async () => {
            if (!currentPendingPayload) return;
            
            // Re-submit with force_add
            currentPendingPayload.force_add = true;
            try {
                const response = await fetch('/applications', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentPendingPayload)
                });
                
                if (!response.ok) {
                    const err = await response.json();
                    alert(err.error || 'Failed to add application');
                    return;
                }
                
                window.location.reload();
            } catch (err) {
                console.error('Error forcefully creating application:', err);
                alert('Error connecting to server.');
            }
        });
    }

    // Form Submit Listener
    if (addForm) {
        addForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(addForm);
            const payload = Object.fromEntries(formData.entries());

            try {
                const response = await fetch('/applications', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.status === 409) {
                    const data = await response.json();
                    if (data.duplicate_found && data.existing_app) {
                        currentPendingPayload = payload;
                        existingDuplicateId = data.existing_app.id;
                        
                        if (dupCompanyName) dupCompanyName.textContent = data.existing_app.company_name;
                        if (dupJobTitle) dupJobTitle.textContent = data.existing_app.job_title;
                        
                        if (duplicateModal) duplicateModal.classList.remove('hidden');
                        return;
                    }
                }

                if (!response.ok) {
                    const err = await response.json();
                    alert(err.error || 'Failed to add application');
                    return;
                }

                // Refresh page to load newly created application card
                window.location.reload();
            } catch (err) {
                console.error('Error creating application:', err);
                alert('Error connecting to server.');
            }
        });
    }

    // Delete Modal Elements
    const deleteModal = document.getElementById('delete-modal');
    const deleteClose = document.getElementById('delete-modal-close');
    const deleteCancel = document.getElementById('delete-cancel-btn');
    const deleteConfirm = document.getElementById('delete-confirm-btn');

    const closeDeleteModal = () => {
        if (deleteModal) deleteModal.classList.add('hidden');
        targetDeleteId = null;
    };

    if (deleteClose) deleteClose.addEventListener('click', closeDeleteModal);
    if (deleteCancel) deleteCancel.addEventListener('click', closeDeleteModal);

    if (deleteConfirm) {
        deleteConfirm.addEventListener('click', async () => {
            if (!targetDeleteId) return;

            try {
                const response = await fetch(`/applications/${targetDeleteId}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    const card = document.querySelector(`.app-card[data-id="${targetDeleteId}"]`);
                    if (card) {
                        card.remove();
                    }
                    recalculateCounters();
                    updateEmptyStates();
                    closeDeleteModal();
                    document.dispatchEvent(new CustomEvent('kanban:changed', { detail: { removedId: targetDeleteId } }));
                } else {
                    alert('Failed to delete application.');
                }
            } catch (err) {
                console.error('Error deleting application:', err);
                alert('Error connecting to server.');
            }
        });
    }
}

function confirmDelete(appId, companyName) {
    targetDeleteId = appId;
    const deleteModal = document.getElementById('delete-modal');
    const companySpan = document.getElementById('delete-company-name');

    if (companySpan) {
        companySpan.innerText = `"${companyName}"`;
    }

    if (deleteModal) {
        deleteModal.classList.remove('hidden');
    }
}

// --------------------------------------------------------------------------
// 6. Google One Tap / Sign-In Callback Handler
// --------------------------------------------------------------------------
async function handleGoogleCredentialResponse(response) {
    if (!response || !response.credential) return;

    try {
        const res = await fetch('/auth/google', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ credential: response.credential })
        });

        const data = await res.json();

        if (res.ok && data.success) {
            window.location.href = data.redirect || '/';
        } else {
            alert(data.error || 'Google login failed.');
        }
    } catch (err) {
        console.error('Error during Google authentication:', err);
        alert('Could not authenticate with Google.');
    }
}


// --------------------------------------------------------------------------
// 8. Smart Calendar Generator & Interactivity
// --------------------------------------------------------------------------
// 7. Full-Page View Controller (Dashboard, Analytics, Calendar)
// --------------------------------------------------------------------------
function switchView(viewName) {
    // Hide all full-page views
    document.querySelectorAll('.app-view-page').forEach(v => v.classList.add('hidden'));

    // Deactivate all top-nav gradient items
    document.querySelectorAll('.gradient-menu-item').forEach(item => {
        item.classList.remove('active');
        item.setAttribute('aria-selected', 'false');
    });

    // Toggle search box visibility
    const searchBox = document.querySelector('.search-box');
    if (searchBox) {
        if (viewName === 'dashboard') {
            searchBox.classList.remove('hidden');
        } else {
            searchBox.classList.add('hidden');
        }
    }

    // Sync Top Navigation Gradient Menu item
    const topNavMap = {
        'dashboard': 'top-nav-dashboard',
        'analytics': 'top-nav-analytics',
        'calendar': 'top-nav-calendar',
        'fit-score': 'top-nav-fit-score',
        'resume-versions': 'top-nav-resume-versions',
        'email-intelligence': 'top-nav-email-intelligence'
    };

    const topNavId = topNavMap[viewName];
    if (topNavId) {
        const topItem = document.getElementById(topNavId);
        if (topItem) {
            topItem.classList.add('active');
            topItem.setAttribute('aria-selected', 'true');
        }
    }

    if (viewName === 'dashboard') {
        const v = document.getElementById('view-dashboard');
        if (v) v.classList.remove('hidden');
    } else if (viewName === 'analytics') {
        const v = document.getElementById('view-analytics');
        if (v) v.classList.remove('hidden');
        loadAnalyticsData();
    } else if (viewName === 'calendar') {
        const v = document.getElementById('view-calendar');
        if (v) v.classList.remove('hidden');
        renderSmartCalendar(calendarCurrentDate.getFullYear(), calendarCurrentDate.getMonth());
    } else if (viewName === 'fit-score') {
        const v = document.getElementById('view-fit-score');
        if (v) v.classList.remove('hidden');
        loadFitScorePage();
    } else if (viewName === 'resume-versions') {
        const v = document.getElementById('view-resume-versions');
        if (v) v.classList.remove('hidden');
        loadResumeVersionsPage();
    } else if (viewName === 'email-intelligence') {
        const v = document.getElementById('view-email-intelligence');
        if (v) v.classList.remove('hidden');
        loadEmailIntelligencePage();
    } else if (viewName === 'profile') {
        const v = document.getElementById('view-profile');
        if (v) v.classList.remove('hidden');
    } else if (viewName === 'settings') {
        const v = document.getElementById('view-settings');
        if (v) v.classList.remove('hidden');
    }
}

function initNavigationEvents() {
    // Header User Name / Profile button click handler
    const headerUserBtn = document.getElementById('header-user-btn');
    if (headerUserBtn) {
        headerUserBtn.addEventListener('click', (e) => {
            e.preventDefault();
            switchView('profile');
        });
    }

    // Top Gradient Menu Navigation Listeners
    document.querySelectorAll('.gradient-menu-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const viewName = item.dataset.view;
            if (viewName) {
                switchView(viewName);
            }
        });
    });

    // Check URL parameters for view navigation on page load
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const initialView = urlParams.get('view');
        const isConnected = urlParams.get('connected');
        const gmailError = urlParams.get('gmail_error') || urlParams.get('error');

        if (initialView) {
            switchView(initialView);
            if (initialView === 'email-intelligence') {
                if (isConnected === 'true') {
                    showEmailIntelligenceAlert(
                        'success',
                        'Gmail Connected Successfully',
                        'Your Gmail account is connected and ready to scan for recruitment updates.'
                    );
                    setTimeout(() => hideEmailIntelligenceAlert(), 4500);
                } else if (gmailError) {
                    showEmailIntelligenceAlert(
                        'error',
                        'Gmail Authorization Incomplete',
                        'Google OAuth authorization could not be completed. Please try connecting again.',
                        [{ label: 'Connect Gmail', action: 'reconnect' }]
                    );
                }
            }

            // Clean up the URL query parameters smoothly without reloading
            if (window.history && window.history.replaceState) {
                const cleanUrl = window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
            }
        }
    } catch (err) {
        console.error('Error processing URL view parameters:', err);
    }
}

// --------------------------------------------------------------------------
// 8. Smart Calendar Generator & Interactivity
// --------------------------------------------------------------------------
let calendarCurrentDate = new Date();
let cachedCalendarEvents = [];

function initCalendarEvents() {
    const prevBtn = document.getElementById('cal-prev-month');
    const nextBtn = document.getElementById('cal-next-month');
    const todayBtn = document.getElementById('cal-today-btn');
    const monthSelect = document.getElementById('calendar-month-select');
    const yearSelect = document.getElementById('calendar-year-select');

    if (prevBtn) {
        prevBtn.addEventListener('click', () => {
            calendarCurrentDate.setMonth(calendarCurrentDate.getMonth() - 1);
            renderSmartCalendar(calendarCurrentDate.getFullYear(), calendarCurrentDate.getMonth());
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            calendarCurrentDate.setMonth(calendarCurrentDate.getMonth() + 1);
            renderSmartCalendar(calendarCurrentDate.getFullYear(), calendarCurrentDate.getMonth());
        });
    }

    if (todayBtn) {
        todayBtn.addEventListener('click', () => {
            calendarCurrentDate = new Date();
            renderSmartCalendar(calendarCurrentDate.getFullYear(), calendarCurrentDate.getMonth());
        });
    }

    if (yearSelect) {
        const currentYear = new Date().getFullYear();
        yearSelect.innerHTML = '';
        for (let y = currentYear - 3; y <= currentYear + 3; y++) {
            const option = document.createElement('option');
            option.value = y;
            option.innerText = y;
            yearSelect.appendChild(option);
        }
    }

    if (monthSelect && yearSelect) {
        const handleChange = () => {
            calendarCurrentDate.setFullYear(parseInt(yearSelect.value, 10));
            calendarCurrentDate.setMonth(parseInt(monthSelect.value, 10));
            renderSmartCalendar(calendarCurrentDate.getFullYear(), calendarCurrentDate.getMonth());
        };
        monthSelect.addEventListener('change', handleChange);
        yearSelect.addEventListener('change', handleChange);
    }

    // Setup Toolbar Search, Status Filter Pills, Event Type Dropdown, and Clear Action
    initCalendarToolbarEvents();

    // Setup Hover Popover and Click Modal Event Listeners
    initCalendarInteractivity();
}

function initCalendarInteractivity() {
    const popover = document.getElementById('cal-event-popover');
    const modal = document.getElementById('calendar-event-modal');
    const modalClose = document.getElementById('cal-modal-close');
    const modalCancel = document.getElementById('cal-modal-cancel');
    const modalGotoBoard = document.getElementById('cal-modal-goto-board');

    if (modalClose) modalClose.addEventListener('click', () => modal.classList.add('hidden'));
    if (modalCancel) modalCancel.addEventListener('click', () => modal.classList.add('hidden'));
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.add('hidden');
        });
    }

    // Grid Event Delegation for Hover and Click
    const grid = document.getElementById('calendar-grid');
    if (grid) {
        grid.addEventListener('mouseover', (e) => {
            const eventPill = e.target.closest('.event-pill');
            if (!eventPill || !popover) return;

            const evtDataRaw = eventPill.dataset.evt;
            if (!evtDataRaw) return;

            try {
                const evt = JSON.parse(evtDataRaw);
                showEventPopover(evt, eventPill);
            } catch (err) {
                // Ignore parse errors
            }
        });

        grid.addEventListener('mouseout', (e) => {
            const eventPill = e.target.closest('.event-pill');
            if (eventPill && popover) {
                popover.classList.remove('is-visible');
                popover.classList.add('hidden');
            }
        });

        grid.addEventListener('click', (e) => {
            const eventPill = e.target.closest('.event-pill');
            const dayCell = e.target.closest('.calendar-day-cell');

            if (eventPill) {
                e.stopPropagation();
                const evtDataRaw = eventPill.dataset.evt;
                if (!evtDataRaw) return;
                try {
                    const evt = JSON.parse(evtDataRaw);
                    openCalendarEventModal(evt);
                } catch (err) {
                    console.error('Error opening event modal:', err);
                }
                return;
            }

            if (dayCell && !dayCell.classList.contains('other-month')) {
                // Remove active highlight from other cells
                document.querySelectorAll('.calendar-day-cell').forEach(c => {
                    c.classList.remove('active-selected-day', 'selected-day');
                });
                dayCell.classList.add('active-selected-day', 'selected-day');

                const dateStr = dayCell.dataset.date;
                if (dateStr) {
                    renderSelectedDateSummary(dateStr);
                    if (window.innerWidth <= 768) {
                        renderMobileAgendaForDate(dateStr);
                    }
                }
            }
        });
    }

    if (modalGotoBoard) {
        modalGotoBoard.addEventListener('click', () => {
            const appId = modalGotoBoard.dataset.appId;
            if (modal) modal.classList.add('hidden');
            if (!appId) return;

            // Switch to dashboard view and pulse target card
            if (typeof switchView === 'function') switchView('dashboard');

            setTimeout(() => {
                const targetCard = document.querySelector(`.app-card[data-id="${appId}"]`);
                if (targetCard) {
                    targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    targetCard.classList.remove('app-card-highlight-pulse');
                    void targetCard.offsetWidth;
                    targetCard.classList.add('app-card-highlight-pulse');
                    setTimeout(() => {
                        targetCard.classList.remove('app-card-highlight-pulse');
                    }, 2800);
                }
            }, 100);
        });
    }
}

function showEventPopover(evt, triggerEl) {
    const popover = document.getElementById('cal-event-popover');
    if (!popover || !triggerEl) return;

    const companyEl = document.getElementById('popoverCompany');
    const statusEl = document.getElementById('popoverStatus');
    const roleEl = document.getElementById('popoverRole');
    const locationEl = document.getElementById('popoverLocation');
    const dateEl = document.getElementById('popoverDate');
    const notesEl = document.getElementById('popoverNotes');

    const meta = evt.meta || {};
    if (companyEl) companyEl.textContent = evt.company_name || 'Company';
    if (statusEl) {
        statusEl.textContent = evt.status || 'Applied';
        statusEl.className = `popover-status-badge badge-${(evt.status || 'applied').toLowerCase()}`;
    }
    if (roleEl) roleEl.textContent = evt.job_title || 'Software Engineer';
    if (locationEl) locationEl.textContent = meta.location || 'Remote';
    if (dateEl) dateEl.textContent = evt.date || '';

    if (notesEl) {
        if (meta.notes) {
            notesEl.textContent = meta.notes;
            notesEl.style.display = 'block';
        } else {
            notesEl.style.display = 'none';
        }
    }

    // Position Popover nicely relative to trigger element
    const rect = triggerEl.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

    let popoverX = rect.left + scrollLeft + rect.width / 2 - 130;
    let popoverY = rect.top + scrollTop - 120;

    // Viewport edge collision safety
    if (popoverX < 10) popoverX = 10;
    if (popoverX + 270 > window.innerWidth) popoverX = window.innerWidth - 275;
    if (popoverY < scrollTop + 10) popoverY = rect.bottom + scrollTop + 8;

    popover.style.left = `${popoverX}px`;
    popover.style.top = `${popoverY}px`;

    popover.classList.remove('hidden');
    requestAnimationFrame(() => popover.classList.add('is-visible'));
}

function openCalendarEventModal(evt) {
    const modal = document.getElementById('calendar-event-modal');
    if (!modal) return;

    const meta = evt.meta || {};
    const company = evt.company_name || 'Company';
    const role = evt.job_title || 'Software Engineer';
    const status = evt.status || 'Applied';

    const avatarEl = document.getElementById('calModalAvatar');
    const companyEl = document.getElementById('calModalCompany');
    const roleEl = document.getElementById('calModalRole');
    const statusBadge = document.getElementById('calModalStatusBadge');
    const fitScoreEl = document.getElementById('calModalFitScore');
    const locationEl = document.getElementById('calModalLocation');
    const salaryEl = document.getElementById('calModalSalary');
    const jobTypeEl = document.getElementById('calModalJobType');
    const resumeEl = document.getElementById('calModalResume');
    const dateAppliedEl = document.getElementById('calModalDateApplied');
    const interviewDateEl = document.getElementById('calModalInterviewDate');
    const notesEl = document.getElementById('calModalNotes');
    const jobLinkEl = document.getElementById('calModalJobLink');
    const gotoBoardBtn = document.getElementById('calModalGotoBoard');

    if (avatarEl) avatarEl.textContent = company.charAt(0).toUpperCase();
    if (companyEl) companyEl.textContent = company;
    if (roleEl) roleEl.textContent = role;

    if (statusBadge) {
        statusBadge.textContent = status;
        statusBadge.className = `activity-pill activity-pill-${status.toLowerCase()}`;
    }

    if (fitScoreEl) {
        if (meta.fit_score) {
            fitScoreEl.textContent = `Fit Score: ${meta.fit_score}%`;
            fitScoreEl.style.display = 'inline-flex';
        } else {
            fitScoreEl.style.display = 'none';
        }
    }

    if (locationEl) locationEl.textContent = meta.location || 'Not Specified';
    if (salaryEl) salaryEl.textContent = meta.salary || 'Competitive';
    if (jobTypeEl) jobTypeEl.textContent = meta.job_type || 'Full-time';
    if (resumeEl) resumeEl.textContent = meta.resume_version || 'Default Resume';
    if (dateAppliedEl) dateAppliedEl.textContent = meta.date_applied || evt.date || '-';
    if (interviewDateEl) interviewDateEl.textContent = meta.interview_date || meta.assessment_date || 'None scheduled';
    if (notesEl) notesEl.textContent = meta.notes || 'No extra notes recorded for this application.';

    if (jobLinkEl) {
        if (meta.job_url) {
            jobLinkEl.href = meta.job_url;
            jobLinkEl.style.display = 'inline-flex';
        } else {
            jobLinkEl.style.display = 'none';
        }
    }

    if (gotoBoardBtn) {
        gotoBoardBtn.dataset.appId = evt.app_id;
    }

    modal.classList.remove('hidden');
}

let calendarFilterState = {
    search: '',
    status: 'all',
    eventType: 'all'
};
let currentSelectedCalendarDate = null;

function matchesCalendarFilters(evt) {
    if (!evt) return false;

    // 1. Status Filter
    if (calendarFilterState.status !== 'all') {
        const s = (evt.status || '').toLowerCase();
        if (s !== calendarFilterState.status.toLowerCase()) {
            return false;
        }
    }

    // 2. Event Type Filter
    if (calendarFilterState.eventType !== 'all') {
        const filterType = calendarFilterState.eventType.toLowerCase();
        const evtType = (evt.event_type || evt.type || '').toLowerCase();
        const status = (evt.status || '').toLowerCase();
        const label = (evt.label || '').toLowerCase();

        if (filterType === 'application') {
            if (!evtType.includes('appl') && !status.includes('appl') && !label.includes('appl')) return false;
        } else if (filterType === 'interview') {
            if (!evtType.includes('interv') && !status.includes('interv') && !label.includes('interv')) return false;
        } else if (filterType === 'assessment') {
            if (!evtType.includes('assess') && !status.includes('assess') && !label.includes('assess')) return false;
        } else if (filterType === 'offer') {
            if (!evtType.includes('offer') && !status.includes('offer') && !label.includes('offer')) return false;
        }
    }

    // 3. Search Query
    if (calendarFilterState.search) {
        const q = calendarFilterState.search.toLowerCase().trim();
        const comp = (evt.company_name || '').toLowerCase();
        const title = (evt.job_title || '').toLowerCase();
        const status = (evt.status || '').toLowerCase();
        const label = (evt.label || '').toLowerCase();
        const evtType = (evt.event_type || evt.type || '').toLowerCase();
        const meta = evt.meta || {};
        const loc = (meta.location || '').toLowerCase();
        const notes = (meta.notes || '').toLowerCase();
        const rec = (meta.recruiter || meta.contact || '').toLowerCase();

        const matched = comp.includes(q) ||
                        title.includes(q) ||
                        status.includes(q) ||
                        label.includes(q) ||
                        evtType.includes(q) ||
                        loc.includes(q) ||
                        notes.includes(q) ||
                        rec.includes(q);

        if (!matched) return false;
    }

    return true;
}

function initCalendarToolbarEvents() {
    const searchInput = document.getElementById('calendar-search-input');
    const searchClearBtn = document.getElementById('calendar-search-clear-btn');
    const statusPills = document.querySelectorAll('#calendar-status-pills .cal-filter-pill');
    const typeFilter = document.getElementById('calendar-event-type-filter');
    const clearFiltersBtn = document.getElementById('calendar-clear-filters-btn');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            calendarFilterState.search = e.target.value;
            updateCalendarToolbarUI();
            applyCalendarFilters();
        });
    }

    if (searchClearBtn) {
        searchClearBtn.addEventListener('click', () => {
            if (searchInput) searchInput.value = '';
            calendarFilterState.search = '';
            updateCalendarToolbarUI();
            applyCalendarFilters();
        });
    }

    statusPills.forEach(pill => {
        pill.addEventListener('click', () => {
            statusPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            calendarFilterState.status = pill.dataset.status || 'all';
            updateCalendarToolbarUI();
            applyCalendarFilters();
        });
    });

    if (typeFilter) {
        typeFilter.addEventListener('change', (e) => {
            calendarFilterState.eventType = e.target.value;
            updateCalendarToolbarUI();
            applyCalendarFilters();
        });
    }

    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', () => {
            calendarFilterState.search = '';
            calendarFilterState.status = 'all';
            calendarFilterState.eventType = 'all';

            if (searchInput) searchInput.value = '';
            if (typeFilter) typeFilter.value = 'all';
            statusPills.forEach(p => {
                if (p.dataset.status === 'all') p.classList.add('active');
                else p.classList.remove('active');
            });

            updateCalendarToolbarUI();
            applyCalendarFilters();
        });
    }
}

function updateCalendarToolbarUI() {
    const searchClearBtn = document.getElementById('calendar-search-clear-btn');
    const clearFiltersBtn = document.getElementById('calendar-clear-filters-btn');

    const hasSearch = !!calendarFilterState.search.trim();
    const hasFilters = calendarFilterState.status !== 'all' || calendarFilterState.eventType !== 'all' || hasSearch;

    if (searchClearBtn) {
        if (hasSearch) searchClearBtn.classList.remove('hidden');
        else searchClearBtn.classList.add('hidden');
    }

    if (clearFiltersBtn) {
        if (hasFilters) clearFiltersBtn.classList.remove('hidden');
        else clearFiltersBtn.classList.add('hidden');
    }
}

function applyCalendarFilters() {
    renderCalendarGridCells();
    if (currentSelectedCalendarDate) {
        renderSelectedDateSummary(currentSelectedCalendarDate);
    }
}

function renderSelectedDateSummary(dateStr) {
    currentSelectedCalendarDate = dateStr;
    const section = document.getElementById('calendar-selected-date-section');
    const titleEl = document.getElementById('calSelectedDateTitle');
    const countEl = document.getElementById('calSelectedDateCount');
    const listEl = document.getElementById('calSelectedDateEventsList');
    if (!listEl || !dateStr) return;

    // Parse date parts safely to avoid timezone offset issues
    const parts = dateStr.split('-');
    if (parts.length === 3) {
        const yNum = parseInt(parts[0], 10);
        const mNum = parseInt(parts[1], 10) - 1;
        const dNum = parseInt(parts[2], 10);
        const monthNames = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ];
        if (titleEl) {
            titleEl.textContent = `${monthNames[mNum] || ''} ${dNum}, ${yNum}`;
        }
    } else {
        if (titleEl) titleEl.textContent = dateStr;
    }

    // Filter events for this specific date matching active search and filters
    const dayEvents = (cachedCalendarEvents || []).filter(e => e.date === dateStr && matchesCalendarFilters(e));
    const count = dayEvents.length;

    if (countEl) {
        countEl.textContent = `${count} event${count === 1 ? '' : 's'}`;
    }

    // Trigger fast subtle CSS transition
    if (section) {
        section.classList.remove('panel-fade');
        void section.offsetWidth;
        section.classList.add('panel-fade');
    }

    const hasFilters = calendarFilterState.status !== 'all' || calendarFilterState.eventType !== 'all' || !!calendarFilterState.search.trim();

    if (count === 0) {
        listEl.innerHTML = `
            <div class="selected-date-empty">
                <span>${hasFilters ? 'No matching events. Try changing your search or filters.' : 'No events scheduled for this day.'}</span>
            </div>
        `;
        return;
    }

    // Display ALL events for selected date without artificial limits or truncation
    let html = '';
    dayEvents.forEach(evt => {
        const meta = evt.meta || {};
        const status = evt.status || 'Applied';
        const statusLower = status.toLowerCase();
        const company = evt.company_name || 'Company';
        const role = evt.job_title || 'Software Engineer';

        let eventDetail = 'Application submitted';
        if (evt.type === 'interview' || status.toLowerCase() === 'interviewing') {
            const timeStr = meta.interview_time ? ` · ${meta.interview_time}` : '';
            eventDetail = `${meta.interview_type || 'Technical Interview'}${timeStr}`;
        } else if (evt.type === 'assessment') {
            eventDetail = 'Coding Assessment Deadline';
        } else if (status.toLowerCase() === 'offered') {
            eventDetail = 'Job Offer Received';
        } else if (status.toLowerCase() === 'rejected') {
            eventDetail = 'Application update';
        }

        const safeEvt = JSON.stringify(evt).replace(/"/g, '&quot;');

        html += `
            <div class="selected-event-card status-border-${statusLower}" data-evt="${safeEvt}" tabindex="0" role="button" aria-label="${company} · ${role} (${status})">
                <div class="selected-event-header">
                    <span class="selected-event-status status-text-${statusLower}">
                        <span class="legend-dot dot-${statusLower}"></span>
                        ${status}
                    </span>
                </div>
                <strong class="selected-event-company">${company} · ${role}</strong>
                <span class="selected-event-desc">${eventDetail}</span>
            </div>
        `;
    });

    listEl.innerHTML = html;

    // Attach click listeners to cards to open modal
    listEl.querySelectorAll('.selected-event-card').forEach(card => {
        card.addEventListener('click', () => {
            const raw = card.dataset.evt;
            if (raw) {
                try {
                    const evt = JSON.parse(raw);
                    openCalendarEventModal(evt);
                } catch (e) {
                    console.error('Error opening event modal from card:', e);
                }
            }
        });
    });
}

function renderMobileAgendaForDate(dateStr) {
    const agendaList = document.getElementById('agendaEventsList');
    const titleEl = document.getElementById('agendaSelectedDateTitle');
    const countBadge = document.getElementById('agendaCountBadge');
    if (!agendaList) return;

    const dayEvents = (cachedCalendarEvents || []).filter(e => e.date === dateStr && matchesCalendarFilters(e));
    if (titleEl) titleEl.textContent = `Events for ${dateStr}`;
    if (countBadge) countBadge.textContent = `${dayEvents.length} Event${dayEvents.length === 1 ? '' : 's'}`;

    if (dayEvents.length === 0) {
        agendaList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem 0;">No matching events for this date.</p>';
        return;
    }

    agendaList.innerHTML = '';
    dayEvents.forEach(evt => {
        const card = document.createElement('div');
        card.className = 'agenda-card';
        card.innerHTML = `
            <div>
                <strong style="display: block; font-size: 0.9rem; color: var(--text-primary);">${evt.company_name}</strong>
                <span style="font-size: 0.8rem; color: var(--text-secondary);">${evt.job_title}</span>
            </div>
            <span class="event-pill event-pill-${(evt.status || 'applied').toLowerCase()}">${evt.status}</span>
        `;
        card.addEventListener('click', () => openCalendarEventModal(evt));
        agendaList.appendChild(card);
    });
}

function renderCalendarGridCells() {
    const gridElem = document.getElementById('calendar-grid');
    if (!gridElem) return;

    const year = calendarCurrentDate.getFullYear();
    const month = calendarCurrentDate.getMonth();

    // Filter events by active search and status/type filters
    const matchingEvents = (cachedCalendarEvents || []).filter(matchesCalendarFilters);

    // Group matching events by YYYY-MM-DD
    const eventsByDate = {};
    matchingEvents.forEach(evt => {
        if (!evt.date) return;
        if (!eventsByDate[evt.date]) {
            eventsByDate[evt.date] = [];
        }
        eventsByDate[evt.date].push(evt);
    });

    const firstDayIndex = new Date(year, month, 1).getDay();
    const totalDaysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();

    const todayObj = new Date();
    const todayStr = `${todayObj.getFullYear()}-${String(todayObj.getMonth() + 1).padStart(2, '0')}-${String(todayObj.getDate()).padStart(2, '0')}`;

    gridElem.innerHTML = '';

    // 1. Previous Month Padding Days
    for (let i = firstDayIndex - 1; i >= 0; i--) {
        const dayNum = prevMonthDays - i;
        const cell = document.createElement('div');
        cell.className = 'calendar-day-cell other-month';
        cell.innerHTML = `<div class="calendar-cell-top"><span class="calendar-day-number">${dayNum}</span></div>`;
        gridElem.appendChild(cell);
    }

    // 2. Current Month Days
    for (let day = 1; day <= totalDaysInMonth; day++) {
        const cell = document.createElement('div');
        const monthStr = String(month + 1).padStart(2, '0');
        const dayStr = String(day).padStart(2, '0');
        const dateKey = `${year}-${monthStr}-${dayStr}`;

        cell.className = 'calendar-day-cell';
        cell.dataset.date = dateKey;

        if (dateKey === todayStr) {
            cell.classList.add('today-cell');
        }

        if (currentSelectedCalendarDate && dateKey === currentSelectedCalendarDate) {
            cell.classList.add('selected-day', 'active-selected-day');
        }

        const dayEvents = eventsByDate[dateKey] || [];

        // Build Cell Top
        let topHTML = `
            <div class="calendar-cell-top">
                <span class="calendar-day-number">${day}</span>
                ${dateKey === todayStr ? '<span class="today-badge-dot" title="Today"></span>' : ''}
            </div>
        `;

        // Render Up to 2 event pills + overflow badge for grid cell cleanliness
        let pillsHTML = '';
        const maxVisiblePills = 2;
        const visibleEvents = dayEvents.slice(0, maxVisiblePills);
        const overflowCount = dayEvents.length - maxVisiblePills;

        visibleEvents.forEach(evt => {
            const statusStr = evt.status || 'Applied';
            const statusClass = statusStr.toLowerCase();
            const companyName = evt.company_name || 'Company';
            const safeEvtData = JSON.stringify(evt).replace(/"/g, '&quot;');

            pillsHTML += `
                <div class="event-pill event-pill-${statusClass}" data-evt="${safeEvtData}" data-app-id="${evt.app_id}" tabindex="0" role="button" aria-label="${companyName} ${statusStr}">
                    <span class="event-status-dot"></span>
                    <span>${companyName}</span>
                </div>
            `;
        });

        if (overflowCount > 0) {
            pillsHTML += `<span class="more-events-badge">+${overflowCount} more</span>`;
        }

        cell.innerHTML = topHTML + pillsHTML;
        gridElem.appendChild(cell);
    }

    // 3. Next Month Padding Days
    const totalRendered = firstDayIndex + totalDaysInMonth;
    const remaining = (totalRendered % 7 === 0) ? 0 : (7 - (totalRendered % 7));
    for (let i = 1; i <= remaining; i++) {
        const cell = document.createElement('div');
        cell.className = 'calendar-day-cell other-month';
        cell.innerHTML = `<div class="calendar-cell-top"><span class="calendar-day-number">${i}</span></div>`;
        gridElem.appendChild(cell);
    }
}

async function renderSmartCalendar(year, month) {
    const monthSelect = document.getElementById('calendar-month-select');
    const yearSelect = document.getElementById('calendar-year-select');
    const gridElem = document.getElementById('calendar-grid');
    if (!gridElem) return;

    if (monthSelect) monthSelect.value = month.toString();
    if (yearSelect) {
        let yearExists = Array.from(yearSelect.options).some(opt => opt.value === year.toString());
        if (!yearExists) {
            const option = document.createElement('option');
            option.value = year;
            option.innerText = year;
            yearSelect.appendChild(option);
            const options = Array.from(yearSelect.options);
            options.sort((a, b) => parseInt(a.value) - parseInt(b.value));
            yearSelect.innerHTML = '';
            options.forEach(opt => yearSelect.appendChild(opt));
        }
        yearSelect.value = year.toString();
    }

    gridElem.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--text-muted);">Loading schedule events...</div>';

    let events = [];
    try {
        const response = await fetch('/api/calendar-events');
        if (response.ok) {
            events = await response.json();
            cachedCalendarEvents = events;
        }
    } catch (err) {
        console.error('Error fetching calendar events:', err);
    }

    const todayObj = new Date();
    const todayStr = `${todayObj.getFullYear()}-${String(todayObj.getMonth() + 1).padStart(2, '0')}-${String(todayObj.getDate()).padStart(2, '0')}`;
    const firstDayKey = `${year}-${String(month + 1).padStart(2, '0')}-01`;

    // Determine default selected date
    if (!currentSelectedCalendarDate || !currentSelectedCalendarDate.startsWith(`${year}-${String(month + 1).padStart(2, '0')}`)) {
        if (todayObj.getFullYear() === year && todayObj.getMonth() === month) {
            currentSelectedCalendarDate = todayStr;
        } else {
            currentSelectedCalendarDate = firstDayKey;
        }
    }

    renderCalendarGridCells();

    if (currentSelectedCalendarDate) {
        renderSelectedDateSummary(currentSelectedCalendarDate);
    }
}


// --------------------------------------------------------------------------
// 9. Analytics & Performance Insights Data Handler
// --------------------------------------------------------------------------
function initAnalyticsEvents() {
    const analyticsModal = document.getElementById('analytics-modal');
    const openBtn = document.getElementById('btn-open-analytics');
    const closeBtn = document.getElementById('analytics-close-btn');

    const handleAnalyticsOpen = () => {
        if (analyticsModal) {
            analyticsModal.classList.remove('hidden');
            loadAnalyticsData();
        }
    };

    if (openBtn) openBtn.addEventListener('click', handleAnalyticsOpen);

    if (closeBtn && analyticsModal) {
        closeBtn.addEventListener('click', () => analyticsModal.classList.add('hidden'));
    }
}

async function loadAnalyticsData() {
    try {
        const response = await fetch('/api/analytics');
        if (!response.ok) return;

        const data = await response.json();

        // Update Top KPI Metric Cards
        const totalElem = document.getElementById('kpi-total-apps');
        const interviewRateElem = document.getElementById('kpi-interview-rate');
        const interviewSubtext = document.getElementById('kpi-interview-subtext');
        const offerRateElem = document.getElementById('kpi-offer-rate');
        const offerSubtext = document.getElementById('kpi-offer-subtext');
        const rejectionRateElem = document.getElementById('kpi-rejection-rate');
        const rejectionSubtext = document.getElementById('kpi-rejection-subtext');

        if (totalElem) totalElem.innerText = data.total;
        if (interviewRateElem) interviewRateElem.innerText = `${data.interview_rate}%`;
        if (interviewSubtext) interviewSubtext.innerText = `${data.total_interviewed} interviews`;
        if (offerRateElem) offerRateElem.innerText = `${data.offer_rate}%`;
        if (offerSubtext) offerSubtext.innerText = `${data.offered} offers`;
        if (rejectionRateElem) rejectionRateElem.innerText = `${data.rejection_rate}%`;
        if (rejectionSubtext) rejectionSubtext.innerText = `${data.rejected} rejections`;

        // Update Status Funnel Breakdown Progress Bars
        const statuses = ['Applied', 'Interviewing', 'Offered', 'Rejected'];
        statuses.forEach(status => {
            const countElem = document.getElementById(`funnel-count-${status.toLowerCase()}`);
            const barFillElem = document.getElementById(`funnel-bar-${status.toLowerCase()}`);

            const info = data.funnel[status] || { count: 0, percentage: 0 };
            if (countElem) countElem.innerText = `${info.count} applications`;
            if (barFillElem) barFillElem.style.width = `${info.percentage}%`;
        });

        // Update Status Proportion Donut Chart Center & Segments
        const donutTotal = document.getElementById('donut-total');
        if (donutTotal) donutTotal.innerText = data.total;

        let accumulatedPct = 0;
        statuses.forEach(status => {
            const segElem = document.getElementById(`donut-segment-${status.toLowerCase()}`);
            const info = data.funnel[status] || { percentage: 0 };
            const pct = info.percentage || 0;

            if (segElem) {
                segElem.setAttribute('stroke-dasharray', `${pct} ${100 - pct}`);
                segElem.setAttribute('stroke-dashoffset', `${-accumulatedPct}`);
            }
            accumulatedPct += pct;
        });

    } catch (err) {
        console.error('Error loading analytics data:', err);
    }
}

// --------------------------------------------------------------------------
// 10. Application Details Modal Handler
// --------------------------------------------------------------------------
function handleCardClick(e, appId) {
    if (e.target.closest('select, button, a, textarea, input')) {
        return;
    }
    openApplicationDetails(appId);
}

function initDetailsEvents() {
    const detailsModal = document.getElementById('details-modal');
    const closeBtn = document.getElementById('details-close-btn');
    const form = document.getElementById('details-app-form');
    const deleteBtn = document.getElementById('details-delete-btn');
    const statusSelect = document.getElementById('details-status-select');

    if (closeBtn && detailsModal) {
        closeBtn.addEventListener('click', () => detailsModal.classList.add('hidden'));
    }

    if (statusSelect) {
        statusSelect.addEventListener('change', (e) => {
            statusSelect.className = `status-dropdown status-pill-${e.target.value.toLowerCase()}`;
        });
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const appId = document.getElementById('details-app-id').value;
            if (!appId) return;

            const payload = {
                company_name: document.getElementById('details-company').value,
                job_title: document.getElementById('details-title').value,
                status: document.getElementById('details-status-select').value,
                date_applied: document.getElementById('details-date-applied').value,
                interview_date: document.getElementById('details-interview-date').value,
                assessment_date: document.getElementById('details-assessment-date').value,
                job_url: document.getElementById('details-job-url').value,
                salary: document.getElementById('details-salary').value,
                location: document.getElementById('details-location').value,
                notes: document.getElementById('details-notes').value,
                job_type: document.getElementById('details-job-type') ? document.getElementById('details-job-type').value : 'Full-time',
                resume_version: document.getElementById('details-resume-version') ? document.getElementById('details-resume-version').value : ''
            };

            try {
                const response = await fetch(`/applications/${appId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    window.location.reload();
                } else {
                    const err = await response.json();
                    alert(err.error || 'Failed to update application details.');
                }
            } catch (err) {
                console.error('Error saving application details:', err);
                alert('Error connecting to server.');
            }
        });
    }


    if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
            const appId = document.getElementById('details-app-id').value;
            const companyName = document.getElementById('details-company-title').innerText;
            if (detailsModal) detailsModal.classList.add('hidden');
            if (appId) confirmDelete(appId, companyName);
        });
    }
}

function toggleEditMode(isEditing) {
    const viewMode = document.getElementById('details-view-mode');
    const editMode = document.getElementById('details-app-form');
    if (isEditing) {
        viewMode.classList.add('hidden');
        editMode.classList.remove('hidden');
    } else {
        viewMode.classList.remove('hidden');
        editMode.classList.add('hidden');
    }
}

async function openApplicationDetails(appId) {
    const detailsModal = document.getElementById('details-modal');
    if (!detailsModal) return;

    try {
        const response = await fetch(`/applications/${appId}`);
        if (!response.ok) {
            alert('Could not fetch application details.');
            return;
        }

        const app = await response.json();

        // Populate Form (Edit Mode)
        document.getElementById('details-app-id').value = app.id;
        document.getElementById('details-company-title').innerText = app.company_name;
        document.getElementById('details-job-subtitle').innerText = app.job_title;

        const statusSelect = document.getElementById('details-status-select');
        if (statusSelect) {
            statusSelect.value = app.status;
            statusSelect.className = `status-dropdown status-pill-${app.status.toLowerCase()}`;
        }

        document.getElementById('details-company').value = app.company_name;
        document.getElementById('details-title').value = app.job_title;

        const jobTypeElem = document.getElementById('details-job-type');
        if (jobTypeElem) jobTypeElem.value = app.job_type || 'Full-time';

        const resumeVersionElem = document.getElementById('details-resume-version');
        if (resumeVersionElem) resumeVersionElem.value = app.resume_version || '';

        document.getElementById('details-job-url').value = app.job_url || '';
        document.getElementById('details-salary').value = app.salary || '';
        document.getElementById('details-location').value = app.location || '';
        document.getElementById('details-date-applied').value = app.date_applied || '';
        document.getElementById('details-interview-date').value = app.interview_date || '';
        document.getElementById('details-assessment-date').value = app.assessment_date || '';
        document.getElementById('details-notes').value = app.notes || '';

        // Populate View Mode
        const jobUrlLink = document.getElementById('view-job-url');
        if (app.job_url) {
            jobUrlLink.href = app.job_url;
            jobUrlLink.innerText = "View Listing";
            jobUrlLink.style.display = "inline";
        } else {
            jobUrlLink.removeAttribute('href');
            jobUrlLink.innerText = "Not provided";
        }

        document.getElementById('view-job-type').innerText = app.job_type || '--';
        document.getElementById('view-resume').innerText = app.resume_version || '--';
        document.getElementById('view-salary').innerText = app.salary || '--';
        document.getElementById('view-location').innerText = app.location || '--';
        
        document.getElementById('view-date-applied').innerText = app.date_applied || '--';
        document.getElementById('view-interview-date').innerText = app.interview_date || '--';
        document.getElementById('view-assessment-date').innerText = app.assessment_date || '--';
        
        const notesText = document.getElementById('view-notes');
        if (app.notes && app.notes.trim()) {
            notesText.innerText = app.notes;
            notesText.classList.remove('text-muted');
        } else {
            notesText.innerText = "No notes added yet.";
            notesText.classList.add('text-muted');
        }

        // Set up View Mode Delete Button
        const deleteBtnView = document.getElementById('details-delete-btn-view');
        if (deleteBtnView) {
            deleteBtnView.onclick = (e) => {
                e.stopPropagation();
                detailsModal.classList.add('hidden'); // hide modal to show confirm
                confirmDelete(app.id, app.company_name);
            };
        }

        // Load and render application timeline
        loadApplicationTimeline(app.id);

        // Default to view mode
        toggleEditMode(false);
        detailsModal.classList.remove('hidden');
    } catch (err) {
        console.error('Error opening details modal:', err);
    }
}

// --------------------------------------------------------------------------
// 11. URL Auto-Fill Event Handlers
// --------------------------------------------------------------------------
function initAutoFillEvents() {
    const btnAdd = document.getElementById('btn-autofill-add');
    const btnDetails = document.getElementById('btn-autofill-details');

    if (btnAdd) {
        btnAdd.addEventListener('click', () => {
            autoFillFromUrl('add-job-url', 'company_name', 'job_title', 'location', 'salary', 'job_type', 'notes', 'btn-autofill-add');
        });
    }

    if (btnDetails) {
        btnDetails.addEventListener('click', () => {
            autoFillFromUrl('details-job-url', 'details-company', 'details-title', 'details-location', 'details-salary', 'details-job-type', 'details-notes', 'btn-autofill-details');
        });
    }
}

async function autoFillFromUrl(urlInputId, companyInputId, titleInputId, locationInputId, salaryInputId, jobTypeInputId, notesInputId, btnId) {
    const urlElem = document.getElementById(urlInputId);
    const btn = document.getElementById(btnId);
    if (!urlElem || !btn) return;

    const url = urlElem.value.trim();
    if (!url) {
        alert('Please paste or type a job URL first.');
        return;
    }

    const origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '✨ Extracting Details...';

    try {
        const response = await fetch('/api/autofill-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (data.company_name && document.getElementById(companyInputId)) document.getElementById(companyInputId).value = data.company_name;
            if (data.job_title && document.getElementById(titleInputId)) document.getElementById(titleInputId).value = data.job_title;
            if (data.location && document.getElementById(locationInputId)) document.getElementById(locationInputId).value = data.location;
            if (data.salary && document.getElementById(salaryInputId)) document.getElementById(salaryInputId).value = data.salary;
            if (data.job_type && document.getElementById(jobTypeInputId)) document.getElementById(jobTypeInputId).value = data.job_type;
            if (data.job_description && document.getElementById(notesInputId)) document.getElementById(notesInputId).value = data.job_description;

            btn.innerHTML = 'Auto-Filled!';
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = origText;
            }, 2000);
        } else {
            alert(data.error || 'Could not auto-fill details from URL.');
            btn.disabled = false;
            btn.innerHTML = origText;
        }
    } catch (err) {
        console.error('Error auto-filling from URL:', err);
        alert('Error connecting to auto-fill service.');
        btn.disabled = false;
        btn.innerHTML = origText;
    }
}

// --------------------------------------------------------------------------
// 12. Modal Dismissibility (Backdrop Click & Escape Key)
// --------------------------------------------------------------------------
function initModalDismissibility() {
    document.querySelectorAll('.modal-backdrop').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
            }
        });
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-backdrop').forEach(modal => {
                modal.classList.add('hidden');
            });
        }
    });
}

// --------------------------------------------------------------------------
// 13. Floating AI Career Assistant Chatbot Handler (Career Copilot Engine)
// --------------------------------------------------------------------------
let chatHistory = [];
let activeChatContext = null; // e.g. { company: 'Google', role: 'Software Engineer', status: 'Interviewing' }
let lastUserMessageText = '';

const CHAT_PLACEHOLDERS = [
    "Ask about your applications...",
    "How should I prepare for my interview?",
    "Help me improve my resume...",
    "Draft a follow-up email...",
    "Analyze my job search strategy..."
];
let currentPlaceholderIndex = 0;

function initChatbot() {
    const toggleBtn = document.getElementById('chatbot-toggle-btn');
    const minimizeBtn = document.getElementById('chatbot-minimize-btn');
    const menuBtn = document.getElementById('chatbot-menu-btn');
    const dropdownMenu = document.getElementById('chatbot-dropdown-menu');
    const newChatBtn = document.getElementById('chatbot-new-chat-btn');
    const clearBtn = document.getElementById('chatbot-clear-btn');
    const clearConfirmBox = document.getElementById('chatbot-clear-confirm');
    const btnCancelClear = document.getElementById('btn-cancel-clear-chat');
    const btnConfirmClear = document.getElementById('btn-confirm-clear-chat');
    const windowElem = document.getElementById('chatbot-window');
    const form = document.getElementById('chatbot-form');
    const input = document.getElementById('chatbot-input');
    const messagesContainer = document.getElementById('chatbot-messages');
    const sendBtn = document.getElementById('chatbot-send-btn');
    const scrollDownBtn = document.getElementById('chatbot-scroll-down-btn');
    const unreadDot = document.getElementById('chatbot-unread-dot');
    const contextContainer = document.getElementById('ai-active-context');
    const contextLabel = document.getElementById('ai-context-label');
    const clearContextBtn = document.getElementById('ai-clear-context-btn');

    if (!toggleBtn || !windowElem) return;

    // Expose Global Helper to open chatbot with active application context
    window.openChatbotWithContext = function(company, role, status) {
        activeChatContext = { company, role, status: status || 'Applied' };
        if (contextLabel) contextLabel.textContent = `${company} · ${role}`;
        if (contextContainer) contextContainer.classList.remove('hidden');

        // Open chat window
        windowElem.classList.remove('hidden');
        if (unreadDot) unreadDot.classList.add('hidden');

        // Update suggested action chips
        renderSuggestedPrompts();
        if (chatHistory.length === 0) {
            renderWelcomeState();
        }
        if (input) input.focus();
        smartScrollToBottom(true);
    };

    // Toggle Chatbot Window
    toggleBtn.addEventListener('click', () => {
        const isHidden = windowElem.classList.contains('hidden');
        if (isHidden) {
            windowElem.classList.remove('hidden');
            if (unreadDot) unreadDot.classList.add('hidden');
            if (chatHistory.length === 0) {
                renderWelcomeState();
            }
            renderSuggestedPrompts();
            rotateInputPlaceholder();
            if (input) input.focus();
            smartScrollToBottom(true);
        } else {
            windowElem.classList.add('hidden');
            closeDropdownMenu();
        }
    });

    if (minimizeBtn) {
        minimizeBtn.addEventListener('click', () => {
            windowElem.classList.add('hidden');
            closeDropdownMenu();
        });
    }

    // Keyboard navigation: Escape closes chat, Enter sends
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !windowElem.classList.contains('hidden')) {
            windowElem.classList.add('hidden');
            closeDropdownMenu();
        }
    });

    // Three-dot Menu Trigger
    if (menuBtn && dropdownMenu) {
        menuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdownMenu.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!dropdownMenu.contains(e.target) && e.target !== menuBtn) {
                closeDropdownMenu();
            }
        });
    }

    function closeDropdownMenu() {
        if (dropdownMenu) dropdownMenu.classList.add('hidden');
    }

    // New Conversation
    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            closeDropdownMenu();
            resetConversation();
        });
    }

    // Clear Conversation Trigger
    if (clearBtn && clearConfirmBox) {
        clearBtn.addEventListener('click', () => {
            closeDropdownMenu();
            clearConfirmBox.classList.remove('hidden');
        });
    }

    if (btnCancelClear && clearConfirmBox) {
        btnCancelClear.addEventListener('click', () => {
            clearConfirmBox.classList.add('hidden');
        });
    }

    if (btnConfirmClear && clearConfirmBox) {
        btnConfirmClear.addEventListener('click', () => {
            clearConfirmBox.classList.add('hidden');
            resetConversation();
        });
    }

    function resetConversation() {
        chatHistory = [];
        lastUserMessageText = '';
        renderWelcomeState();
        renderSuggestedPrompts();
        rotateInputPlaceholder();
    }

    // Clear Active Context Chip
    if (clearContextBtn && contextContainer) {
        clearContextBtn.addEventListener('click', () => {
            activeChatContext = null;
            contextContainer.classList.add('hidden');
            renderSuggestedPrompts();
            if (chatHistory.length === 0) renderWelcomeState();
        });
    }

    // Scroll Down Floating Pill
    if (scrollDownBtn) {
        scrollDownBtn.addEventListener('click', () => {
            smartScrollToBottom(true);
            scrollDownBtn.classList.add('hidden');
        });
    }

    if (messagesContainer) {
        messagesContainer.addEventListener('scroll', () => {
            const distanceFromBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight;
            if (distanceFromBottom < 40 && scrollDownBtn) {
                scrollDownBtn.classList.add('hidden');
            }
        });
    }

    // Form Submission
    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const msg = input.value.trim();
            if (msg) {
                sendChatMessage(msg);
            }
        });
    }

    // Render Initial Welcome State
    renderWelcomeState();
    renderSuggestedPrompts();

    // --------------------------------------------------------------------------
    // Core Messaging Logic
    // --------------------------------------------------------------------------
    async function sendChatMessage(userText) {
        if (!userText || (sendBtn && sendBtn.disabled)) return;

        lastUserMessageText = userText;
        if (input) input.value = '';

        // If this is the first message, clear the welcome state container
        const welcomeEl = document.querySelector('.chatbot-welcome-screen');
        if (welcomeEl) welcomeEl.remove();

        appendBubble('user', userText);
        smartScrollToBottom(true);

        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.classList.add('is-loading');
        }
        showTypingIndicator();

        // Incorporate active application context into backend payload if set
        let contextualUserText = userText;
        if (activeChatContext && activeChatContext.company) {
            contextualUserText = `[Context: Application for ${activeChatContext.company} - ${activeChatContext.role} (${activeChatContext.status})]\n${userText}`;
        }

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: contextualUserText,
                    history: chatHistory
                })
            });

            removeTypingIndicator();
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove('is-loading');
            }

            const data = await response.json();

            if (response.ok && data.reply) {
                appendBubble('assistant', data.reply);
                chatHistory.push({ role: 'user', content: userText });
                chatHistory.push({ role: 'assistant', content: data.reply });

                // If window is currently hidden, trigger unread badge
                if (windowElem.classList.contains('hidden') && unreadDot) {
                    unreadDot.classList.remove('hidden');
                }
            } else {
                appendBubble('assistant', data.error || 'I encountered an unexpected issue while processing your request. Please try again.');
            }
        } catch (err) {
            console.error('Chatbot fetch error:', err);
            removeTypingIndicator();
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove('is-loading');
            }
            appendBubble('assistant', 'Unable to connect to the AI Career Copilot service. Please verify your connection and try again.');
        }

        smartScrollToBottom();
    }

    // Expose global regeneration handler
    window.regenerateLastChatMessage = function() {
        if (lastUserMessageText) {
            sendChatMessage(lastUserMessageText);
        }
    };

    // --------------------------------------------------------------------------
    // UI Helpers & Renderers
    // --------------------------------------------------------------------------
    function renderWelcomeState() {
        if (!messagesContainer) return;
        messagesContainer.innerHTML = `
            <div class="chatbot-welcome-screen">
                <div class="welcome-sparkle-box">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                        <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"></path>
                    </svg>
                </div>
                <h3 class="welcome-title">Your Career Copilot</h3>
                <p class="welcome-subtitle">
                    ${activeChatContext 
                        ? `How can I help with your <strong>${activeChatContext.company}</strong> application?` 
                        : 'What would you like to work on today?'}
                </p>
                
                <div class="welcome-action-grid">
                    <button type="button" class="welcome-action-card" data-prompt="${activeChatContext ? `Help me prepare for my ${activeChatContext.company} interview for ${activeChatContext.role}.` : 'Prepare me for my upcoming interviews with technical and behavioral questions.'}">
                        <div class="card-icon-wrap">🎯</div>
                        <div class="card-text-wrap">
                            <strong>Interview Prep</strong>
                            <span>Mock questions &amp; strategy</span>
                        </div>
                    </button>
                    <button type="button" class="welcome-action-card" data-prompt="${activeChatContext ? `How should I tailor my resume bullet points for ${activeChatContext.role} at ${activeChatContext.company}?` : 'Review my resume and suggest high-impact keywords and bullet points.'}">
                        <div class="card-icon-wrap">📄</div>
                        <div class="card-text-wrap">
                            <strong>Resume Review</strong>
                            <span>Skill keywords &amp; impact</span>
                        </div>
                    </button>
                    <button type="button" class="welcome-action-card" data-prompt="${activeChatContext ? `Draft a polite follow-up email for my ${activeChatContext.company} application.` : 'Draft a professional follow-up email to recruiters after applying.'}">
                        <div class="card-icon-wrap">✉️</div>
                        <div class="card-text-wrap">
                            <strong>Follow-up Email</strong>
                            <span>Polite &amp; effective templates</span>
                        </div>
                    </button>
                    <button type="button" class="welcome-action-card" data-prompt="Analyze my overall application pipeline and recommend my top 3 next priority steps.">
                        <div class="card-icon-wrap">📊</div>
                        <div class="card-text-wrap">
                            <strong>Pipeline Summary</strong>
                            <span>Status analysis &amp; advice</span>
                        </div>
                    </button>
                </div>
            </div>
        `;

        // Attach Click Listeners to Action Cards
        messagesContainer.querySelectorAll('.welcome-action-card').forEach(card => {
            card.addEventListener('click', () => {
                const prompt = card.dataset.prompt;
                if (prompt) sendChatMessage(prompt);
            });
        });
    }

    function renderSuggestedPrompts() {
        const container = document.getElementById('chatbot-quick-prompts');
        if (!container) return;

        let prompts = [];
        if (activeChatContext && activeChatContext.company) {
            prompts = [
                { label: `🎯 ${activeChatContext.company} Prep`, prompt: `Give me a focused interview preparation plan for ${activeChatContext.company} - ${activeChatContext.role}.` },
                { label: `❓ Top Interview Questions`, prompt: `What are the most common technical and behavioral questions asked at ${activeChatContext.company}?` },
                { label: `✉️ Follow-up Draft`, prompt: `Draft a professional follow-up email for my ${activeChatContext.company} application.` },
                { label: `📄 Resume Tailoring`, prompt: `What specific keywords and experiences should I highlight for ${activeChatContext.company}?` }
            ];
        } else {
            prompts = [
                { label: '🎯 Interview Prep', prompt: 'Prepare me for my upcoming interviews with company-tailored questions.' },
                { label: '📊 Pipeline Summary', prompt: 'Summarize my current applications status and recommended next steps.' },
                { label: '✉️ Follow-up Email', prompt: 'Draft a polite follow-up email for my latest job application.' },
                { label: '📄 Resume Tips', prompt: 'What key technical skills and formatting should I highlight on my resume?' },
                { label: '💡 Job Strategy', prompt: 'How can I optimize my application response rate and stand out to recruiters?' }
            ];
        }

        container.innerHTML = '';
        prompts.forEach(p => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'quick-prompt-pill';
            btn.textContent = p.label;
            btn.dataset.prompt = p.prompt;
            btn.addEventListener('click', () => {
                sendChatMessage(p.prompt);
            });
            container.appendChild(btn);
        });
    }

    function rotateInputPlaceholder() {
        if (!input) return;
        currentPlaceholderIndex = (currentPlaceholderIndex + 1) % CHAT_PLACEHOLDERS.length;
        input.placeholder = CHAT_PLACEHOLDERS[currentPlaceholderIndex];
    }

    function appendBubble(role, content) {
        if (!messagesContainer) return;

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'bot-bubble'}`;

        if (role === 'user') {
            const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
            bubble.innerHTML = `
                <div class="bubble-content">${escaped}</div>
            `;
        } else {
            const formattedText = formatMarkdownMessage(content);
            bubble.innerHTML = `
                <div class="bubble-avatar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                        <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"></path>
                    </svg>
                </div>
                <div class="bubble-content-wrap">
                    <div class="bubble-content">${formattedText}</div>
                    <div class="bubble-actions">
                        <button type="button" class="bubble-action-btn" onclick="copyChatMessage(this)" title="Copy message">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                            <span>Copy</span>
                        </button>
                        <button type="button" class="bubble-action-btn" onclick="regenerateLastChatMessage()" title="Regenerate response">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="1 4 1 10 7 10"></polyline>
                                <polyline points="23 20 23 14 17 14"></polyline>
                                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
                            </svg>
                            <span>Regenerate</span>
                        </button>
                    </div>
                </div>
            `;
        }

        messagesContainer.appendChild(bubble);
        smartScrollToBottom();
    }

    function showTypingIndicator() {
        if (!messagesContainer) return;
        const typingElem = document.createElement('div');
        typingElem.id = 'chatbot-typing-indicator';
        typingElem.className = 'chat-bubble bot-bubble';
        typingElem.innerHTML = `
            <div class="bubble-avatar">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                    <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"></path>
                </svg>
            </div>
            <div class="bubble-content-wrap">
                <div class="bubble-content typing-content">
                    <div class="typing-dots">
                        <span></span><span></span><span></span>
                    </div>
                    <span class="typing-label">Thinking...</span>
                </div>
            </div>
        `;
        messagesContainer.appendChild(typingElem);
        smartScrollToBottom();
    }

    function removeTypingIndicator() {
        const typingElem = document.getElementById('chatbot-typing-indicator');
        if (typingElem) typingElem.remove();
    }

    function smartScrollToBottom(force = false) {
        if (!messagesContainer) return;
        const distanceFromBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight;
        
        // If user is near bottom or force is true, scroll down automatically
        if (force || distanceFromBottom < 100) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            if (scrollDownBtn) scrollDownBtn.classList.add('hidden');
        } else if (scrollDownBtn) {
            scrollDownBtn.classList.remove('hidden');
        }
    }
}

// --------------------------------------------------------------------------
// Global Markdown Parser & Clipboard Helpers (Safe & Robust Engine)
// --------------------------------------------------------------------------
function formatMarkdownMessage(md) {
    if (!md) return '';
    try {
        let text = md.trim();

        // 1. Normalize line endings
        text = text.replace(/\r\n/g, '\n');

        // 2. Pre-Sanitize dangerous executable HTML
        text = text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
        text = text.replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '');
        text = text.replace(/<object\b[^<]*(?:(?!<\/object>)<[^<]*)*<\/object>/gi, '');
        text = text.replace(/<embed\b[^<]*(?:(?!<\/embed>)<[^<]*)*<\/embed>/gi, '');
        text = text.replace(/on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '');
        text = text.replace(/javascript:[^\s"'>]+/gi, '#');

        const protectedBlocks = [];

        // 3. Extract and protect Code Blocks (```lang ... ```)
        text = text.replace(/```([a-zA-Z0-9_\-\.\+]*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            const id = `__PROTECTED_BLOCK_${protectedBlocks.length}__`;
            const cleanCode = code.replace(/^\n+|\n+$/g, '');
            const escapedCode = escapeText(cleanCode);
            protectedBlocks.push(`
                <div class="chat-code-block">
                    <div class="code-block-header">
                        <span>${lang || 'code'}</span>
                        <button type="button" class="btn-copy-code" onclick="copyCodeBlock(this)">Copy</button>
                    </div>
                    <pre><code>${escapedCode}</code></pre>
                </div>
            `);
            return id;
        });

        // 4. Extract and protect existing HTML table wrappers or raw tables
        text = text.replace(/<div class="chat-table-wrapper">[\s\S]*?<\/div>/gi, (match) => {
            const id = `__PROTECTED_BLOCK_${protectedBlocks.length}__`;
            protectedBlocks.push(match);
            return id;
        });

        text = text.replace(/<table[\s\S]*?<\/table>/gi, (match) => {
            const id = `__PROTECTED_BLOCK_${protectedBlocks.length}__`;
            protectedBlocks.push(`<div class="chat-table-wrapper">${match}</div>`);
            return id;
        });

        // 5. Parse Markdown Tables
        const tableRegex = /((?:^[ \t]*\|[^\n]+\|[ \t]*\n)(?:^[ \t]*\|[ \t]*(?::?[-]+:?[ \t]*\|)+[ \t]*\n)(?:^[ \t]*\|[^\n]+\|[ \t]*(?:\n|$))+)/gm;
        text = text.replace(tableRegex, (match) => {
            const lines = match.trim().split('\n').map(l => l.trim()).filter(l => l.length > 0);
            if (lines.length < 2) return match;

            const headerRow = lines[0];
            const alignRow = lines[1];
            const dataRows = lines.slice(2);

            const alignCols = alignRow.split('|').slice(1, -1).map(col => {
                col = col.trim();
                if (col.startsWith(':') && col.endsWith(':')) return 'center';
                if (col.endsWith(':')) return 'right';
                return 'left';
            });

            const headerCells = headerRow.split('|').slice(1, -1);
            const thHtml = headerCells.map((cell, i) => {
                const align = alignCols[i] || 'left';
                const content = parseInlineMarkdown(escapeText(cell.trim()));
                return `<th style="text-align: ${align};">${content}</th>`;
            }).join('');

            const trHtml = dataRows.map(row => {
                const cells = row.split('|').slice(1, -1);
                const tdHtml = cells.map((cell, i) => {
                    const align = alignCols[i] || 'left';
                    const content = parseInlineMarkdown(escapeText(cell.trim()));
                    return `<td style="text-align: ${align};">${content}</td>`;
                }).join('');
                return `<tr>${tdHtml}</tr>`;
            }).join('');

            const tableHtml = `
                <div class="chat-table-wrapper">
                    <table class="chat-markdown-table">
                        <thead><tr>${thHtml}</tr></thead>
                        <tbody>${trHtml}</tbody>
                    </table>
                </div>
            `;

            const id = `__PROTECTED_BLOCK_${protectedBlocks.length}__`;
            protectedBlocks.push(tableHtml);
            return id;
        });

        // Helper for inline markdown replacements
        function parseInlineMarkdown(str) {
            return str
                .replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>')
                .replace(/`([^`\n]+)`/g, '<code class="chat-inline-code">$1</code>')
                .replace(/\*\*\*([\s\S]+?)\*\*\*/g, '<strong><em>$1</em></strong>')
                .replace(/___([\s\S]+?)___/g, '<strong><em>$1</em></strong>')
                .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
                .replace(/__([\s\S]+?)__/g, '<strong>$1</strong>')
                .replace(/\*([^\*\n]+)\*/g, '<em>$1</em>')
                .replace(/_([a-zA-Z0-9\s]+)_/g, '<em>$1</em>')
                .replace(/~~(.+?)~~/g, '<del>$1</del>');
        }

        // 6. Escape plain text outside protected blocks
        const parts = text.split(/(__PROTECTED_BLOCK_\d+__)/);
        text = parts.map(part => {
            if (/^__PROTECTED_BLOCK_\d+__$/.test(part)) return part;
            return escapeText(part);
        }).join('');

        // 7. Parse Block Elements
        const rawBlocks = text.split(/\n{2,}/);
        const parsedBlocks = [];

        for (let block of rawBlocks) {
            block = block.trim();
            if (!block) continue;

            if (/^__PROTECTED_BLOCK_\d+__$/.test(block)) {
                parsedBlocks.push(block);
                continue;
            }

            if (/^(?:---|___|\*\*\*)$/.test(block)) {
                parsedBlocks.push('<hr class="chat-hr">');
                continue;
            }

            if (/^####\s*(.+)$/.test(block)) {
                parsedBlocks.push(`<h5 class="chat-h5">${parseInlineMarkdown(block.replace(/^####\s*/, ''))}</h5>`);
                continue;
            }
            if (/^###\s*(.+)$/.test(block)) {
                parsedBlocks.push(`<h4 class="chat-h4">${parseInlineMarkdown(block.replace(/^###\s*/, ''))}</h4>`);
                continue;
            }
            if (/^##\s*(.+)$/.test(block)) {
                parsedBlocks.push(`<h3 class="chat-h3">${parseInlineMarkdown(block.replace(/^##\s*/, ''))}</h3>`);
                continue;
            }
            if (/^#\s*(.+)$/.test(block)) {
                parsedBlocks.push(`<h2 class="chat-h2">${parseInlineMarkdown(block.replace(/^#\s*/, ''))}</h2>`);
                continue;
            }

            if (/^>\s*(.*)$/m.test(block)) {
                const quoteLines = block.split('\n').map(l => l.replace(/^>\s*/, '')).join('<br>');
                parsedBlocks.push(`<blockquote class="chat-quote">${parseInlineMarkdown(quoteLines)}</blockquote>`);
                continue;
            }

            if (/^[ \t]*[\*\-]\s+/m.test(block)) {
                const items = block.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                const liHtml = items.map(l => {
                    const itemContent = l.replace(/^[\*\-]\s+/, '');
                    return `<li class="chat-li">${parseInlineMarkdown(itemContent)}</li>`;
                }).join('');
                parsedBlocks.push(`<ul class="chat-ul">${liHtml}</ul>`);
                continue;
            }

            if (/^[ \t]*\d+\.\s+/m.test(block)) {
                const items = block.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                const liHtml = items.map(l => {
                    const itemContent = l.replace(/^\d+\.\s+/, '');
                    return `<li class="chat-li">${parseInlineMarkdown(itemContent)}</li>`;
                }).join('');
                parsedBlocks.push(`<ol class="chat-ol">${liHtml}</ol>`);
                continue;
            }

            const formattedParagraph = parseInlineMarkdown(block.replace(/\n/g, '<br>'));
            parsedBlocks.push(`<p class="chat-p">${formattedParagraph}</p>`);
        }

        let resultHtml = parsedBlocks.join('');

        // 8. Restore Protected Blocks
        protectedBlocks.forEach((content, index) => {
            resultHtml = resultHtml.replace(new RegExp(`__PROTECTED_BLOCK_${index}__`, 'g'), content);
        });

        // 9. Safety net: never leak internal placeholder tokens into the UI.
        resultHtml = resultHtml.replace(/__PROTECTED_BLOCK_\d+__/g, '');

        return resultHtml;
    } catch (err) {
        console.error('Markdown rendering error:', err);
        return `<p class="chat-p">${escapeText(md).replace(/\n/g, '<br>')}</p>`;
    }
}

function escapeText(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

window.copyChatMessage = function(btn) {
    if (!btn) return;
    const bubbleContent = btn.closest('.bubble-content-wrap')?.querySelector('.bubble-content');
    if (!bubbleContent) return;

    const textToCopy = bubbleContent.innerText || bubbleContent.textContent;
    navigator.clipboard.writeText(textToCopy).then(() => {
        const span = btn.querySelector('span');
        if (span) {
            const orig = span.textContent;
            span.textContent = 'Copied!';
            setTimeout(() => span.textContent = orig, 1800);
        }
    }).catch(err => console.error('Copy failed:', err));
};

window.copyCodeBlock = function(btn) {
    if (!btn) return;
    const codeEl = btn.closest('.chat-code-block')?.querySelector('pre code');
    if (!codeEl) return;

    navigator.clipboard.writeText(codeEl.innerText).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = orig, 1800);
    }).catch(err => console.error('Code copy failed:', err));
};


// --------------------------------------------------------------------------
// 14. Enhanced Profile & Comprehensive Settings Handlers
// --------------------------------------------------------------------------
function initProfileAndSettingsEvents() {
    // 1. Settings Tab Navigation
    document.querySelectorAll('.settings-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.tab;
            document.querySelectorAll('.settings-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.settings-tab-content').forEach(c => c.classList.add('hidden'));

            btn.classList.add('active');
            const targetElem = document.getElementById(targetTab);
            if (targetElem) targetElem.classList.remove('hidden');
        });
    });

    // 2. Profile Form Submission
    const profileForm = document.getElementById('profile-form');
    if (profileForm) {
        profileForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const statusElem = document.getElementById('profile-save-status');
            if (statusElem) {
                statusElem.className = 'save-status-text';
                statusElem.innerText = 'Saving...';
            }

            const payload = {
                full_name: document.getElementById('profile-full-name').value.trim(),
                phone: document.getElementById('profile-phone').value.trim(),
                location: document.getElementById('profile-location').value.trim(),
                headline: document.getElementById('profile-headline').value.trim(),
                university: document.getElementById('profile-university').value.trim(),
                grad_year: document.getElementById('profile-grad-year').value.trim()
            };

            try {
                const response = await fetch('/api/profile', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();
                if (response.ok && data.success) {
                    if (statusElem) {
                        statusElem.className = 'save-status-text save-status-success';
                        statusElem.innerText = 'Saved Profile Changes!';
                        setTimeout(() => statusElem.innerText = '', 2500);
                    }

                    // Update UI preview header
                    const user = data.user || {};
                    const headerName = document.getElementById('profile-header-name');
                    const headerHeadline = document.getElementById('profile-header-headline');
                    const avatarPreview = document.getElementById('profile-avatar-preview');

                    if (headerName) headerName.innerText = user.full_name || user.username || 'User';
                    if (headerHeadline) headerHeadline.innerText = user.headline || 'Computer Science Student | Python & AI/ML';
                    if (avatarPreview && user.avatar_url) {
                        avatarPreview.innerHTML = `<img src="${user.avatar_url}" alt="Avatar" class="avatar-img">`;
                    }
                } else {
                    if (statusElem) {
                        statusElem.className = 'save-status-text save-status-error';
                        statusElem.innerText = data.error || 'Failed to update profile.';
                    }
                }
            } catch (err) {
                console.error('Error saving profile:', err);
                if (statusElem) {
                    statusElem.className = 'save-status-text save-status-error';
                    statusElem.innerText = 'Error connecting to server.';
                }
            }
        });
    }

    // 3. Settings Form Auto-Save & Loading
    const settingsInputs = [
        'setting-notify-followup', 'setting-notify-interview', 'setting-reminder-time',
        'setting-email-notifications', 'setting-theme', 'setting-dashboard-view',
        'setting-card-density', 'setting-show-stats', 'setting-show-warnings', 'setting-show-interview-dates'
    ];

    settingsInputs.forEach(id => {
        const elem = document.getElementById(id);
        if (elem) {
            elem.addEventListener('change', saveUserSettings);
        }
    });

    async function loadUserSettings() {
        try {
            const response = await fetch('/api/settings');
            if (response.ok) {
                const settings = await response.json();
                
                const setChecked = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.checked = val === 1 || val === true;
                };
                const setValue = (id, val) => {
                    const el = document.getElementById(id);
                    if (el && val !== undefined) el.value = val;
                };

                setChecked('setting-notify-followup', settings.notify_followup);
                setChecked('setting-notify-interview', settings.notify_interview);
                setValue('setting-reminder-time', settings.reminder_time);
                setChecked('setting-email-notifications', settings.email_notifications);
                setValue('setting-theme', settings.theme);
                setValue('setting-dashboard-view', settings.dashboard_view);
                setValue('setting-card-density', settings.card_density);
                setChecked('setting-show-stats', settings.show_stats);
                setChecked('setting-show-warnings', settings.show_warnings);
                setChecked('setting-show-interview-dates', settings.show_interview_dates);

                // Apply density class live
                if (settings.card_density === 'compact') {
                    document.body.classList.add('density-compact');
                    document.body.classList.remove('density-spacious');
                } else if (settings.card_density === 'spacious') {
                    document.body.classList.add('density-spacious');
                    document.body.classList.remove('density-compact');
                } else {
                    document.body.classList.remove('density-compact', 'density-spacious');
                }

                // Apply theme
                const moonIcon = document.getElementById('theme-icon-moon');
                const sunIcon = document.getElementById('theme-icon-sun');
                if (settings.theme === 'dark') {
                    document.body.setAttribute('data-theme', 'dark');
                    localStorage.setItem('app-theme', 'dark');
                    if (moonIcon) moonIcon.classList.add('hidden');
                    if (sunIcon) sunIcon.classList.remove('hidden');
                } else {
                    document.body.removeAttribute('data-theme');
                    localStorage.setItem('app-theme', 'light');
                    if (moonIcon) moonIcon.classList.remove('hidden');
                    if (sunIcon) sunIcon.classList.add('hidden');
                }
            }
        } catch (err) {
            console.error('Error loading user settings:', err);
        }
    }

    // Call it immediately on init
    loadUserSettings();

    async function saveUserSettings() {
        const payload = {
            notify_followup: document.getElementById('setting-notify-followup')?.checked,
            notify_interview: document.getElementById('setting-notify-interview')?.checked,
            reminder_time: document.getElementById('setting-reminder-time')?.value,
            email_notifications: document.getElementById('setting-email-notifications')?.checked,
            theme: document.getElementById('setting-theme')?.value,
            dashboard_view: document.getElementById('setting-dashboard-view')?.value,
            card_density: document.getElementById('setting-card-density')?.value,
            show_stats: document.getElementById('setting-show-stats')?.checked,
            show_warnings: document.getElementById('setting-show-warnings')?.checked,
            show_interview_dates: document.getElementById('setting-show-interview-dates')?.checked
        };

        // Apply density class live
        if (payload.card_density === 'compact') {
            document.body.classList.add('density-compact');
            document.body.classList.remove('density-spacious');
        } else if (payload.card_density === 'spacious') {
            document.body.classList.add('density-spacious');
            document.body.classList.remove('density-compact');
        } else {
            document.body.classList.remove('density-compact', 'density-spacious');
        }

        try {
            await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (err) {
            console.error('Error saving user settings:', err);
        }
    }

    // 4. Change Password Form
    const pwForm = document.getElementById('change-password-form');
    if (pwForm) {
        pwForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const statusElem = document.getElementById('password-status-text');
            const current_password = document.getElementById('current-password').value;
            const new_password = document.getElementById('new-password').value;
            const confirm_password = document.getElementById('confirm-new-password').value;

            if (statusElem) {
                statusElem.className = 'save-status-text';
                statusElem.innerText = 'Updating password...';
            }

            try {
                const response = await fetch('/api/account/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password, new_password, confirm_password })
                });

                const data = await response.json();
                if (response.ok && data.success) {
                    pwForm.reset();
                    if (statusElem) {
                        statusElem.className = 'save-status-text save-status-success';
                        statusElem.innerText = 'Password updated successfully!';
                        setTimeout(() => statusElem.innerText = '', 3000);
                    }
                } else {
                    if (statusElem) {
                        statusElem.className = 'save-status-text save-status-error';
                        statusElem.innerText = data.error || 'Failed to update password.';
                    }
                }
            } catch (err) {
                console.error('Error updating password:', err);
                if (statusElem) {
                    statusElem.className = 'save-status-text save-status-error';
                    statusElem.innerText = 'Error connecting to server.';
                }
            }
        });
    }

    // 5. Logout All Devices
    const btnLogoutAll = document.getElementById('btn-logout-all');
    if (btnLogoutAll) {
        btnLogoutAll.addEventListener('click', () => {
            if (confirm('Are you sure you want to log out from all devices?')) {
                window.location.href = '/logout';
            }
        });
    }

    // 6. Delete Account
    const btnDeleteAcc = document.getElementById('btn-delete-account-trigger');
    if (btnDeleteAcc) {
        btnDeleteAcc.addEventListener('click', async () => {
            const confirmed = confirm('WARNING: Are you sure you want to permanently delete your account and all application data? This action CANNOT be undone.');
            if (!confirmed) return;

            try {
                const response = await fetch('/api/account/delete', { method: 'POST' });
                const data = await response.json();
                if (response.ok && data.success) {
                    window.location.href = data.redirect || '/welcome';
                } else {
                    alert(data.error || 'Failed to delete account.');
                }
            } catch (err) {
                console.error('Error deleting account:', err);
                alert('Error connecting to server.');
            }
        });
    }
}

// --------------------------------------------------------------------------
// 15. Fit Score & Skill Gap Analysis Handlers
// --------------------------------------------------------------------------
function toggleMissingSkills(e, appId) {
    if (e) e.stopPropagation();
    const drawer = document.getElementById(`missing-skills-drawer-${appId}`);
    if (drawer) {
        drawer.classList.toggle('hidden');
    }
}

function initFitScoreEvents() {
    const dropzone = document.getElementById('resume-dropzone');
    const fileInput = document.getElementById('resume-file-input');
    const btnUploadNew = document.getElementById('btn-fit-score-upload-new');
    const btnDelete = document.getElementById('btn-delete-resume');
    const btnTogglePreview = document.getElementById('btn-toggle-extracted-text');
    const versionSelect = document.getElementById('fit-score-version-select');

    if (btnUploadNew && dropzone) {
        btnUploadNew.addEventListener('click', () => {
            dropzone.classList.toggle('hidden');
        });
    }

    if (versionSelect) {
        versionSelect.addEventListener('change', async (e) => {
            const versionId = e.target.value;
            const statusElem = document.getElementById('resume-upload-status');
            if (statusElem) {
                statusElem.className = 'save-status-text';
                statusElem.innerText = 'Switching active resume version & recalculating fit scores...';
            }

            try {
                const res = await fetch('/api/fit-score/select-version', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ version_id: versionId })
                });

                if (res.ok) {
                    if (statusElem) {
                        statusElem.className = 'save-status-text save-status-success';
                        statusElem.innerText = 'Fit scores updated for selected resume version!';
                        setTimeout(() => statusElem.innerText = '', 3000);
                    }
                    loadFitScorePage();
                }
            } catch (err) {
                console.error('Error selecting resume version:', err);
            }
        });
    }

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', (e) => {
            if (!e.target.closest('input[type="text"]')) {
                fileInput.click();
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                uploadResumeFile(e.target.files[0]);
            }
        });

        // Drag and Drop Events
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('drag-active');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('drag-active');
            }, false);
        });

        dropzone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            if (dt && dt.files && dt.files[0]) {
                uploadResumeFile(dt.files[0]);
            }
        });
    }

    if (btnDelete) {
        btnDelete.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to remove your master resume? This will reset application fit scores.')) return;
            try {
                const res = await fetch('/api/resume', { method: 'DELETE' });
                if (res.ok) {
                    loadFitScorePage();
                }
            } catch (err) {
                console.error('Error deleting resume:', err);
            }
        });
    }

    if (btnTogglePreview) {
        btnTogglePreview.addEventListener('click', () => {
            const drawer = document.getElementById('extracted-text-drawer');
            if (drawer) {
                drawer.classList.toggle('hidden');
            }
        });
    }
}

async function uploadResumeFile(file) {
    const statusElem = document.getElementById('resume-upload-status');
    const fileInput = document.getElementById('resume-file-input');
    const quickVersionNameElem = document.getElementById('quick-version-name-input');
    const versionName = quickVersionNameElem ? quickVersionNameElem.value.trim() : '';

    if (statusElem) {
        statusElem.className = 'save-status-text';
        statusElem.innerText = 'Extracting document text & computing fit scores...';
    }

    const formData = new FormData();
    formData.append('resume_file', file);
    if (versionName) {
        formData.append('version_name', versionName);
    }

    try {
        const endpoint = versionName ? '/api/resume-versions' : '/api/resume/upload';
        const res = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        if (res.status === 401) {
            window.location.href = '/welcome';
            return;
        }

        const contentType = res.headers.get('content-type') || '';
        let data = {};
        if (contentType.includes('application/json')) {
            data = await res.json();
        }

        if (res.ok) {
            if (statusElem) {
                statusElem.className = 'save-status-text save-status-success';
                statusElem.innerText = versionName ? `Saved "${versionName}" & fit scores updated!` : 'Resume uploaded & fit scores updated!';
                setTimeout(() => statusElem.innerText = '', 3000);
            }
            if (quickVersionNameElem) quickVersionNameElem.value = '';
            populateResumeVersionSelects();
            loadFitScorePage();
        } else {
            const errorMsg = data.error || (res.status === 413 ? 'File too large to upload.' : 'Failed to process resume file.');
            if (statusElem) {
                statusElem.className = 'save-status-text save-status-error';
                statusElem.innerText = errorMsg;
            }
        }
    } catch (err) {
        console.error('Error uploading resume file:', err);
        if (statusElem) {
            statusElem.className = 'save-status-text save-status-error';
            statusElem.innerText = 'Network error uploading file to server.';
        }
    } finally {
        if (fileInput) fileInput.value = '';
    }
}

async function loadFitScorePage() {
    const uploadedCard = document.getElementById('uploaded-resume-card');
    const filenameElem = document.getElementById('uploaded-filename');
    const versionBadgeElem = document.getElementById('uploaded-version-badge');
    const previewContainer = document.getElementById('extracted-text-preview-container');
    const previewTextarea = document.getElementById('extracted-resume-textarea');

    // 1. Populate Version Select Dropdown
    await populateFitScoreVersionDropdown();

    // 2. Fetch current active resume details
    try {
        const res = await fetch('/api/resume');
        if (res.ok) {
            const resumeData = await res.json();
            if (resumeData.resume_text) {
                if (uploadedCard) uploadedCard.classList.remove('hidden');
                if (filenameElem) filenameElem.innerText = resumeData.resume_filename || 'Master_Resume.pdf';
                if (versionBadgeElem) versionBadgeElem.innerText = 'Active Resume Text';
                if (previewContainer) previewContainer.classList.remove('hidden');
                if (previewTextarea) previewTextarea.value = resumeData.resume_text;
            } else {
                if (previewContainer) previewContainer.classList.add('hidden');
                if (previewTextarea) previewTextarea.value = '';
            }
        }
    } catch (err) {
        console.error('Error fetching resume info:', err);
    }

    // 3. Load Application Fit Scores List
    const container = document.getElementById('fit-score-apps-list');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center; padding: 1.5rem; color: var(--text-muted);">Loading fit scores...</div>';

    try {
        const res = await fetch('/applications');
        if (!res.ok) return;

        const apps = await res.json();

        apps.sort((a, b) => {
            const scoreA = a.fit_score !== null && a.fit_score !== undefined ? a.fit_score : -1;
            const scoreB = b.fit_score !== null && b.fit_score !== undefined ? b.fit_score : -1;
            return scoreB - scoreA;
        });

        if (apps.length === 0) {
            container.innerHTML = '<div class="empty-state">No applications found. Create applications to see fit score analysis!</div>';
            return;
        }

        container.innerHTML = '';

        apps.forEach(app => {
            const item = document.createElement('div');
            item.className = 'fit-score-app-item';

            let badgeClass = 'fit-score-none';
            let badgeText = 'Fit Score: --';

            if (app.fit_score !== null && app.fit_score !== undefined) {
                if (app.fit_score >= 70) badgeClass = 'fit-score-high';
                else if (app.fit_score >= 40) badgeClass = 'fit-score-med';
                else badgeClass = 'fit-score-low';
                badgeText = `Fit Score: ${app.fit_score}%`;
            }

            const skillsList = app.missing_skills_list || [];
            let skillsHTML = '';
            if (skillsList.length > 0) {
                skillsHTML = skillsList.map(s => `<span class="skill-tag-pill">${s}</span>`).join(' ');
            } else {
                skillsHTML = '<span class="skill-tag-none">No skill gaps identified</span>';
            }

            item.innerHTML = `
                <div class="fit-score-app-info">
                    <h5>${app.company_name} — ${app.job_title}</h5>
                    <p>Status: <strong>${app.status}</strong> | Job Type: ${app.job_type || 'Full-time'}</p>
                    <div style="margin-top: 0.4rem; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                        <span style="font-size: 0.75rem; font-weight: 700; color: var(--text-secondary);">Missing Skills:</span>
                        ${skillsHTML}
                    </div>
                </div>
                <div>
                    <span class="fit-score-badge ${badgeClass}" style="font-size: 0.85rem; padding: 0.35rem 0.65rem;">${badgeText}</span>
                </div>
            `;

            container.appendChild(item);
        });

    } catch (err) {
        console.error('Error loading fit score page:', err);
        container.innerHTML = '<div style="color:#ef4444; padding: 1rem;">Failed to load fit score analysis.</div>';
    }
}

async function populateFitScoreVersionDropdown() {
    const versionSelect = document.getElementById('fit-score-version-select');
    if (!versionSelect) return;

    try {
        const res = await fetch('/api/resume-versions');
        if (!res.ok) return;

        const versions = await res.json();
        const currentVal = versionSelect.value || 'master';

        versionSelect.innerHTML = '<option value="master">Master Resume (Default)</option>';

        versions.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            const docBadge = v.filename ? ` (${v.filename})` : '';
            opt.innerText = `${v.version_name}${docBadge}`;
            versionSelect.appendChild(opt);
        });

        versionSelect.value = currentVal;
    } catch (err) {
        console.error('Error populating fit score version select:', err);
    }
}

// --------------------------------------------------------------------------
// 16. Resume Versions A/B Tracking Handlers
// --------------------------------------------------------------------------
function initResumeVersionsEvents() {
    const btnFileSelect = document.getElementById('btn-select-version-file');
    const fileInput = document.getElementById('version-file-input');
    const fileLabel = document.getElementById('version-file-label');
    const addVersionForm = document.getElementById('add-version-form');

    if (btnFileSelect && fileInput) {
        btnFileSelect.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                if (fileLabel) fileLabel.innerText = e.target.files[0].name;
            }
        });
    }

    if (addVersionForm) {
        addVersionForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const nameInput = document.getElementById('new-version-input');
            const version_name = nameInput ? nameInput.value.trim() : '';

            if (!version_name) {
                alert('Please enter a version name.');
                return;
            }

            const formData = new FormData();
            formData.append('version_name', version_name);
            if (fileInput && fileInput.files && fileInput.files[0]) {
                formData.append('resume_file', fileInput.files[0]);
            }

            const btnSave = document.getElementById('btn-add-version');
            if (btnSave) {
                btnSave.disabled = true;
                btnSave.innerText = 'Saving...';
            }

            try {
                const res = await fetch('/api/resume-versions', {
                    method: 'POST',
                    body: formData
                });

                if (res.ok) {
                    if (nameInput) nameInput.value = '';
                    if (fileInput) fileInput.value = '';
                    if (fileLabel) fileLabel.innerText = 'Attach File (.pdf, .docx)';
                    loadResumeVersionsPage();
                    populateResumeVersionSelects();
                    populateFitScoreVersionDropdown();
                } else {
                    const err = await res.json();
                    alert(err.error || 'Failed to add version.');
                }
            } catch (err) {
                console.error('Error adding version:', err);
                alert('Network error adding resume version.');
            } finally {
                if (btnSave) {
                    btnSave.disabled = false;
                    btnSave.innerText = 'Save Version';
                }
            }
        });
    }
}

async function populateResumeVersionSelects() {
    try {
        const res = await fetch('/api/resume-versions');
        if (!res.ok) return;

        const versions = await res.json();
        const selects = document.querySelectorAll('.resume-version-select');

        selects.forEach(select => {
            const currentVal = select.value;
            select.innerHTML = '<option value="">(None / Default)</option>';
            versions.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.version_name;
                opt.innerText = v.version_name;
                select.appendChild(opt);
            });
            if (currentVal) select.value = currentVal;
        });
    } catch (err) {
        console.error('Error populating version selects:', err);
    }
}

async function loadResumeVersionsPage() {
    const pillsList = document.getElementById('versions-pills-list');
    const chartContainer = document.getElementById('versions-performance-container');
    const analyticsChart = document.getElementById('analytics-versions-chart');

    // 1. Render Saved Versions Cards
    if (pillsList) {
        try {
            const res = await fetch('/api/resume-versions');
            if (res.ok) {
                const versions = await res.json();
                if (versions.length === 0) {
                    pillsList.innerHTML = '<span class="skill-tag-none">No versions added yet. Upload or create one above!</span>';
                } else {
                    pillsList.innerHTML = '';
                    versions.forEach(v => {
                        const card = document.createElement('div');
                        card.className = 'version-card-item';

                        const fileTag = v.filename 
                            ? `<span class="version-file-tag"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg> ${v.filename}</span>`
                            : '<span class="skill-tag-none">No file attached</span>';

                        card.innerHTML = `
                            <div class="version-card-header">
                                <span class="version-title-text">${v.version_name}</span>
                                <button type="button" class="version-delete-btn" onclick="deleteResumeVersion(${v.id})" title="Delete Version">&times;</button>
                            </div>
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                ${fileTag}
                            </div>
                        `;
                        pillsList.appendChild(card);
                    });
                }
            }
        } catch (err) {
            console.error('Error fetching resume versions:', err);
        }
    }

    // 2. Render Conversion Performance Bars
    const renderStatsBars = (container, stats) => {
        if (!container) return;
        if (!stats || stats.length === 0) {
            container.innerHTML = '<div style="color: var(--text-muted); padding: 1rem;">No conversion data recorded yet.</div>';
            return;
        }

        container.innerHTML = '';
        stats.forEach(st => {
            const row = document.createElement('div');
            row.className = 'version-stat-bar-row';
            row.innerHTML = `
                <div class="version-stat-header">
                    <span class="version-stat-name">${st.version_name}</span>
                    <span class="version-stat-rate">Interview Rate: ${st.interview_rate}%</span>
                </div>
                <div class="version-progress-bg">
                    <div class="version-progress-fill" style="width: ${st.interview_rate}%;"></div>
                </div>
                <div class="version-stat-details">
                    <span>Total Apps: <strong>${st.total}</strong></span>
                    <span>Interviewing: <strong>${st.interviewing}</strong></span>
                    <span>Offered: <strong>${st.offered}</strong></span>
                    <span>Offer Rate: <strong>${st.offer_rate}%</strong></span>
                </div>
            `;
            container.appendChild(row);
        });
    };

    try {
        const res = await fetch('/api/analytics/resume-versions');
        if (res.ok) {
            const stats = await res.json();
            renderStatsBars(chartContainer, stats);
            renderStatsBars(analyticsChart, stats);
        }
    } catch (err) {
        console.error('Error fetching version analytics:', err);
    }
}

async function deleteResumeVersion(versionId) {
    if (!confirm('Are you sure you want to delete this resume version tag?')) return;
    try {
        const res = await fetch(`/api/resume-versions/${versionId}`, { method: 'DELETE' });
        if (res.ok) {
            loadResumeVersionsPage();
            populateResumeVersionSelects();
            populateFitScoreVersionDropdown();
        }
    } catch (err) {
        console.error('Error deleting resume version:', err);
    }
}

// --------------------------------------------------------------------------
// 17. Email Intelligence Integration & Application Timeline Handlers
// --------------------------------------------------------------------------
let emailIntelligenceCache = {
    connected: false,
    email_address: null,
    last_synced_at: null,
    emails: [],
    stats: {},
    activeFilter: 'all'
};

async function loadEmailIntelligencePage() {
    try {
        const statusRes = await fetch('/api/email-intelligence/status');
        if (statusRes.ok) {
            const statusData = await statusRes.json();
            emailIntelligenceCache.connected = statusData.connected;
            emailIntelligenceCache.email_address = statusData.email_address;
            emailIntelligenceCache.last_synced_at = statusData.last_synced_at;
            renderEmailConnectionState(statusData);
        }

        if (emailIntelligenceCache.connected) {
            const [statsRes, emailsRes] = await Promise.all([
                fetch('/api/email-intelligence/stats'),
                fetch('/api/email-intelligence/emails')
            ]);

            if (statsRes.ok) {
                const stats = await statsRes.json();
                emailIntelligenceCache.stats = stats;
                renderEmailStats(stats);
            }

            if (emailsRes.ok) {
                const emailsData = await emailsRes.json();
                emailIntelligenceCache.emails = emailsData.emails || [];
                renderEmailUpdatesList(emailIntelligenceCache.emails, emailIntelligenceCache.activeFilter);
            }
        }
    } catch (err) {
        console.error('Error loading Email Intelligence page:', err);
    }
}

function showEmailIntelligenceAlert(type, title, message, actions = []) {
    const alertBox = document.getElementById('email-intel-alert-box');
    const titleEl = document.getElementById('email-alert-title');
    const msgEl = document.getElementById('email-alert-message');
    const actionsEl = document.getElementById('email-alert-actions');
    if (!alertBox || !titleEl || !msgEl) return;

    alertBox.className = `email-intel-alert-box alert-box-${type}`;
    titleEl.innerText = title;
    msgEl.innerText = message;

    if (actionsEl) {
        actionsEl.innerHTML = '';
        actions.forEach(act => {
            if (act.action === 'reconnect') {
                const btn = document.createElement('a');
                btn.href = '/auth/google/gmail/connect';
                btn.className = 'btn-alert-action btn-alert-reconnect';
                btn.innerText = act.label || 'Reconnect Gmail';
                actionsEl.appendChild(btn);
            } else if (act.action === 'retry') {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn-alert-action btn-alert-retry';
                btn.innerText = act.label || 'Retry Sync';
                btn.onclick = () => triggerEmailSync();
                actionsEl.appendChild(btn);
            }
        });

        // Always add a small dismiss button
        const dismissBtn = document.createElement('button');
        dismissBtn.type = 'button';
        dismissBtn.className = 'btn-alert-action btn-alert-retry';
        dismissBtn.innerText = 'Dismiss';
        dismissBtn.onclick = () => hideEmailIntelligenceAlert();
        actionsEl.appendChild(dismissBtn);
    }

    alertBox.classList.remove('hidden');
}

function hideEmailIntelligenceAlert() {
    const alertBox = document.getElementById('email-intel-alert-box');
    if (alertBox) alertBox.classList.add('hidden');
}

function renderEmailConnectionState(statusData) {
    const statusPill = document.getElementById('email-connection-status-pill');
    const statusText = document.getElementById('email-status-text');
    const disconnectedContainer = document.getElementById('email-disconnected-container');
    const connectedContainer = document.getElementById('email-connected-container');
    const syncBtn = document.getElementById('btn-sync-emails');
    const disconnectBtn = document.getElementById('btn-disconnect-gmail');

    if (statusData.connected) {
        const connStatus = statusData.status || 'connected';
        if (statusPill && statusText) {
            if (connStatus === 'connected') {
                statusPill.className = 'email-status-pill status-pill-connected';
                statusText.innerText = `● Gmail Connected (${statusData.email_address || 'Google'})`;
            } else if (connStatus === 'api_disabled') {
                statusPill.className = 'email-status-pill status-pill-error';
                statusText.innerText = `● Gmail API Disabled`;
                showEmailIntelligenceAlert(
                    'error',
                    'Gmail API Not Enabled',
                    'Google Gmail access is not configured correctly. Gmail API is not enabled in your Google Cloud Project. Please enable it in Google Cloud Console.',
                    [{ label: 'Retry Sync', action: 'retry' }]
                );
            } else if (connStatus === 'insufficient_permissions') {
                statusPill.className = 'email-status-pill status-pill-auth-required';
                statusText.innerText = `● Permission Required`;
                showEmailIntelligenceAlert(
                    'warning',
                    'Gmail Read-Only Permission Required',
                    'Gmail read-only permission was not granted. Please reconnect and check the box to grant Gmail access.',
                    [{ label: 'Reconnect Gmail', action: 'reconnect' }]
                );
            } else if (connStatus === 'auth_expired') {
                statusPill.className = 'email-status-pill status-pill-auth-required';
                statusText.innerText = `● Authorization Required`;
                showEmailIntelligenceAlert(
                    'warning',
                    'Gmail Authorization Expired',
                    'Your Gmail authorization has expired or was revoked. Please reconnect Gmail.',
                    [{ label: 'Reconnect Gmail', action: 'reconnect' }]
                );
            } else {
                statusPill.className = 'email-status-pill status-pill-connected';
                statusText.innerText = `● Gmail Connected (${statusData.email_address || 'Google'})`;
            }
        }

        if (disconnectedContainer) disconnectedContainer.classList.add('hidden');
        if (connectedContainer) connectedContainer.classList.remove('hidden');
        if (syncBtn) syncBtn.classList.remove('hidden');
        if (disconnectBtn) disconnectBtn.classList.remove('hidden');
    } else {
        if (statusPill && statusText) {
            statusPill.className = 'email-status-pill status-pill-disconnected';
            statusText.innerText = '○ Gmail Not Connected';
        }
        if (disconnectedContainer) disconnectedContainer.classList.remove('hidden');
        if (connectedContainer) connectedContainer.classList.add('hidden');
        if (syncBtn) syncBtn.classList.add('hidden');
        if (disconnectBtn) disconnectBtn.classList.add('hidden');
        hideEmailIntelligenceAlert();
    }
}

async function triggerEmailSync() {
    const syncBtn = document.getElementById('btn-sync-emails');
    const syncText = document.getElementById('btn-sync-text');
    const banner = document.getElementById('email-sync-status-banner');
    const bannerText = document.getElementById('email-sync-status-text');
    const statusPill = document.getElementById('email-connection-status-pill');
    const statusText = document.getElementById('email-status-text');

    if (syncBtn) syncBtn.disabled = true;
    if (syncText) syncText.innerText = 'Syncing...';
    if (banner) banner.classList.remove('hidden');
    if (bannerText) bannerText.innerText = 'Scanning inbox for job-related recruitment emails...';

    if (statusPill && statusText) {
        statusPill.className = 'email-status-pill status-pill-syncing';
        statusText.innerText = '● Syncing Gmail...';
    }

    hideEmailIntelligenceAlert();

    try {
        const res = await fetch('/api/email-intelligence/sync', { method: 'POST' });
        const data = await res.json();

        if (res.ok && data.success) {
            if (bannerText) bannerText.innerText = data.message || 'Sync completed!';
            showEmailIntelligenceAlert('success', 'Sync Completed', data.message || 'Inbox scanned and career updates synchronized successfully.');
            setTimeout(() => {
                if (banner) banner.classList.add('hidden');
                hideEmailIntelligenceAlert();
            }, 4000);
            await loadEmailIntelligencePage();
            loadDashboardEmailUpdates();
        } else {
            if (banner) banner.classList.add('hidden');

            const errType = data.error_type || 'SYNC_FAILED';
            if (errType === 'GMAIL_API_NOT_ENABLED') {
                if (statusPill && statusText) {
                    statusPill.className = 'email-status-pill status-pill-error';
                    statusText.innerText = '● Gmail API Disabled';
                }
                showEmailIntelligenceAlert(
                    'error',
                    'Gmail API Not Configured in Google Cloud',
                    data.error || 'Google Gmail access is not configured correctly. Gmail API has not been enabled in your Google Cloud project.',
                    [{ label: 'Retry Sync', action: 'retry' }]
                );
            } else if (errType === 'INSUFFICIENT_PERMISSIONS') {
                if (statusPill && statusText) {
                    statusPill.className = 'email-status-pill status-pill-auth-required';
                    statusText.innerText = '● Authorization Required';
                }
                showEmailIntelligenceAlert(
                    'warning',
                    'Gmail Permission Missing',
                    data.error || 'Gmail read-only permission was not granted. Please reconnect and allow read-only Gmail access.',
                    [{ label: 'Reconnect Gmail', action: 'reconnect' }]
                );
            } else if (errType === 'AUTH_EXPIRED') {
                if (statusPill && statusText) {
                    statusPill.className = 'email-status-pill status-pill-auth-required';
                    statusText.innerText = '● Authorization Required';
                }
                showEmailIntelligenceAlert(
                    'warning',
                    'Gmail Authorization Expired',
                    data.error || 'Your Gmail authorization has expired. Please reconnect Gmail.',
                    [{ label: 'Reconnect Gmail', action: 'reconnect' }]
                );
            } else if (errType === 'RATE_LIMIT_EXCEEDED') {
                if (statusPill && statusText) {
                    statusPill.className = 'email-status-pill status-pill-warning';
                    statusText.innerText = '● Rate Limited';
                }
                showEmailIntelligenceAlert(
                    'warning',
                    'Gmail Rate Limit Exceeded',
                    data.error || 'Gmail API rate limit reached. Please wait a few moments and try again.',
                    [{ label: 'Retry', action: 'retry' }]
                );
            } else {
                if (statusPill && statusText) {
                    statusPill.className = 'email-status-pill status-pill-error';
                    statusText.innerText = '● Gmail Sync Failed';
                }
                showEmailIntelligenceAlert(
                    'error',
                    'Gmail Sync Failed',
                    data.error || 'Could not sync Gmail right now. Please try again.',
                    [{ label: 'Retry', action: 'retry' }, { label: 'Reconnect Gmail', action: 'reconnect' }]
                );
            }
        }
    } catch (err) {
        console.error('Error syncing emails:', err);
        if (banner) banner.classList.add('hidden');
        if (statusPill && statusText) {
            statusPill.className = 'email-status-pill status-pill-error';
            statusText.innerText = '● Network Error';
        }
        showEmailIntelligenceAlert(
            'error',
            'Connection Error',
            'Unable to reach server to sync Gmail. Please check your internet connection and try again.',
            [{ label: 'Retry', action: 'retry' }]
        );
    } finally {
        if (syncBtn) syncBtn.disabled = false;
        if (syncText) syncText.innerText = 'Sync Now';
    }
}

function renderEmailStats(stats) {
    const elTotal = document.getElementById('stat-career-emails');
    const elInterviews = document.getElementById('stat-interviews');
    const elAssessments = document.getElementById('stat-assessments');
    const elOffers = document.getElementById('stat-offers');
    const elReview = document.getElementById('stat-needs-review');

    if (elTotal) elTotal.innerText = stats.total_career_emails || 0;
    if (elInterviews) elInterviews.innerText = stats.interviews || 0;
    if (elAssessments) elAssessments.innerText = stats.assessments || 0;
    if (elOffers) elOffers.innerText = stats.offers || 0;
    if (elReview) elReview.innerText = stats.needs_review || 0;
}

function renderEmailUpdatesList(emails, filter = 'all') {
    const listContainer = document.getElementById('email-updates-cards-list');
    const emptyCard = document.getElementById('email-no-updates-card');

    if (!listContainer) return;

    let filtered = emails || [];
    if (filter === 'interviews') {
        filtered = filtered.filter(e => ['INTERVIEW_INVITATION', 'INTERVIEW_UPDATE'].includes(e.classification));
    } else if (filter === 'assessments') {
        filtered = filtered.filter(e => e.classification === 'ASSESSMENT');
    } else if (filter === 'offers') {
        filtered = filtered.filter(e => e.classification === 'OFFER');
    } else if (filter === 'rejections') {
        filtered = filtered.filter(e => e.classification === 'REJECTION');
    } else if (filter === 'needs_review') {
        filtered = filtered.filter(e => e.classification === 'NEEDS_REVIEW' || e.confidence_score < 0.75 || (!e.matched_application_id && e.match_status === 'pending'));
    }

    if (!filtered || filtered.length === 0) {
        listContainer.innerHTML = '';
        if (emptyCard) emptyCard.classList.remove('hidden');
        return;
    }

    if (emptyCard) emptyCard.classList.add('hidden');
    listContainer.innerHTML = '';

    filtered.forEach(email => {
        const ext = email.extracted_data || {};
        const card = document.createElement('div');
        card.className = `email-update-card classification-${(email.classification || 'other').toLowerCase()}`;
        card.id = `email-card-${email.message_id}`;

        // Classification badge and icon
        let iconSvg = '📝';
        let badgeColor = 'badge-applied';
        if (email.classification === 'INTERVIEW_INVITATION' || email.classification === 'INTERVIEW_UPDATE') {
            iconSvg = '🎤';
            badgeColor = 'badge-interviewing';
        } else if (email.classification === 'ASSESSMENT') {
            iconSvg = '⚡';
            badgeColor = 'badge-amber';
        } else if (email.classification === 'OFFER') {
            iconSvg = '🏆';
            badgeColor = 'badge-offered';
        } else if (email.classification === 'REJECTION') {
            iconSvg = '❌';
            badgeColor = 'badge-rejected';
        } else if (email.classification === 'RECRUITER_MESSAGE') {
            iconSvg = '💬';
            badgeColor = 'badge-purple';
        }

        const formattedCls = (email.classification || 'Update').replace(/_/g, ' ');
        const companyName = ext.company_name || email.matched_company_name || 'Recruitment Update';
        const roleTitle = ext.job_title || email.matched_job_title || 'Position';
        const displayDate = email.received_at ? email.received_at.split(' ')[0] : 'Recent';

        // Proposed match pill
        let matchProposalHtml = '';
        if (email.matched_application_id) {
            const oldStatus = email.matched_current_status || 'Applied';
            const proposedStatus = ext.proposed_status || oldStatus;
            const diffHtml = oldStatus !== proposedStatus ? 
                `<span class="status-diff-pill">${oldStatus} &rarr; <strong>${proposedStatus}</strong></span>` : 
                `<span class="status-diff-pill">${oldStatus}</span>`;

            matchProposalHtml = `
                <div class="email-match-box">
                    <div class="match-info">
                        <span class="match-icon">✓</span>
                        <span>Matched to existing application: <strong>${email.matched_company_name}</strong> · ${email.matched_job_title}</span>
                        ${diffHtml}
                    </div>
                </div>
            `;
        } else if (email.match_status === 'pending') {
            matchProposalHtml = `
                <div class="email-match-box match-box-unmatched">
                    <span class="match-unmatched-text">No existing application linked yet.</span>
                </div>
            `;
        }

        // Action Buttons
        let actionButtonsHtml = '';
        if (email.match_status === 'confirmed') {
            actionButtonsHtml = `<span class="badge-confirmed-pill">✓ Application Updated</span>`;
        } else if (email.match_status === 'ignored') {
            actionButtonsHtml = `<span class="badge-ignored-pill">Proposal Ignored</span>`;
        } else {
            const hasAppMatch = !!email.matched_application_id;
            const targetStatus = ext.proposed_status || (email.classification === 'INTERVIEW_INVITATION' ? 'Interviewing' : (email.classification === 'OFFER' ? 'Offered' : (email.classification === 'REJECTION' ? 'Rejected' : null)));

            if (hasAppMatch && targetStatus && targetStatus !== email.matched_current_status) {
                actionButtonsHtml += `
                    <button type="button" class="btn btn-primary btn-sm btn-action-confirm" 
                        onclick="openConfirmUpdateModal('${email.message_id}', ${email.matched_application_id}, '${companyName.replace(/'/g, "\\'")}', '${roleTitle.replace(/'/g, "\\'")}', '${email.matched_current_status}', '${targetStatus}', '${(ext.key_summary || email.subject).replace(/'/g, "\\'")}')">
                        Update Application
                    </button>
                `;
            }

            if (ext.interview_date) {
                actionButtonsHtml += `
                    <button type="button" class="btn btn-outline btn-sm" 
                        onclick="addEmailCalendarEvent('${email.message_id}', ${email.matched_application_id || 0}, '${ext.interview_date}', 'interview')">
                        📅 Add to Calendar
                    </button>
                `;
            } else if (ext.assessment_deadline) {
                actionButtonsHtml += `
                    <button type="button" class="btn btn-outline btn-sm" 
                        onclick="addEmailCalendarEvent('${email.message_id}', ${email.matched_application_id || 0}, '${ext.assessment_deadline}', 'assessment')">
                        ⚡ Add to Calendar
                    </button>
                `;
            }

            if (email.classification === 'RECRUITER_MESSAGE' || email.classification === 'FOLLOW_UP' || email.classification === 'INTERVIEW_INVITATION') {
                actionButtonsHtml += `
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openDraftReplyModal('${email.message_id}')">
                        Draft Reply
                    </button>
                `;
            }

            actionButtonsHtml += `
                <button type="button" class="btn btn-text btn-sm text-muted" onclick="ignoreEmailAction('${email.message_id}')">
                    Ignore
                </button>
            `;
        }

        card.innerHTML = `
            <div class="email-card-header">
                <div class="email-card-title-group">
                    <span class="email-type-badge ${badgeColor}">${iconSvg} ${formattedCls}</span>
                    <h4 class="email-card-company">${companyName}</h4>
                    <span class="email-card-role">${roleTitle}</span>
                </div>
                <div class="email-card-meta">
                    <span class="email-date-text">${displayDate}</span>
                    <button type="button" class="btn-text btn-sm view-details-link" onclick="openEmailDetailsModal('${email.message_id}')">
                        View Details &rarr;
                    </button>
                </div>
            </div>

            <p class="email-card-snippet">${email.snippet || email.subject}</p>

            ${matchProposalHtml}

            <div class="email-card-actions">
                ${actionButtonsHtml}
            </div>
        `;

        listContainer.appendChild(card);
    });
}

async function openEmailDetailsModal(messageId) {
    const modal = document.getElementById('email-details-modal');
    if (!modal) return;

    try {
        const res = await fetch('/api/email-intelligence/emails');
        if (!res.ok) return;
        const data = await res.json();
        const email = (data.emails || []).find(e => e.message_id === messageId);
        if (!email) return;

        const ext = email.extracted_data || {};

        document.getElementById('email-modal-badge').innerText = (email.classification || 'CAREER UPDATE').replace(/_/g, ' ');
        document.getElementById('email-modal-subject').innerText = email.subject || 'No Subject';
        document.getElementById('email-modal-meta').innerText = `From: ${email.sender_name || ''} <${email.sender_email}> · ${email.received_at}`;

        document.getElementById('email-modal-company').innerText = ext.company_name || email.matched_company_name || 'Not specified';
        document.getElementById('email-modal-role').innerText = ext.job_title || email.matched_job_title || 'Not specified';
        document.getElementById('email-modal-status').innerText = ext.proposed_status || email.matched_current_status || 'Applied';
        
        const intDate = ext.interview_date ? `${ext.interview_date} ${ext.interview_time || ''}`.trim() : (ext.assessment_deadline ? `Deadline: ${ext.assessment_deadline}` : 'None detected');
        document.getElementById('email-modal-interview').innerText = intDate;

        const meetingWrap = document.getElementById('email-modal-meeting-wrap');
        const meetingLink = document.getElementById('email-modal-meeting');
        if (ext.meeting_link) {
            meetingWrap.classList.remove('hidden');
            meetingLink.href = ext.meeting_link;
            meetingLink.innerText = ext.meeting_link;
        } else {
            meetingWrap.classList.add('hidden');
        }

        document.getElementById('email-modal-confidence').innerText = `${Math.round((email.confidence_score || 0.85) * 100)}%`;

        // Render sanitized email HTML safely or fallback to text
        const bodyContainer = document.getElementById('email-modal-body-html');
        if (bodyContainer) {
            if (email.body_html_sanitized) {
                bodyContainer.innerHTML = email.body_html_sanitized;
            } else {
                bodyContainer.innerText = email.body_text || email.snippet || 'No email content available.';
            }
        }

        // Configure actions in modal
        const draftBtn = document.getElementById('email-modal-draft-reply-btn');
        if (draftBtn) {
            draftBtn.onclick = () => {
                modal.classList.add('hidden');
                openDraftReplyModal(messageId);
            };
        }

        const updateBtn = document.getElementById('email-modal-confirm-update-btn');
        if (updateBtn) {
            if (email.matched_application_id && email.match_status === 'pending') {
                updateBtn.classList.remove('hidden');
                updateBtn.onclick = () => {
                    modal.classList.add('hidden');
                    openConfirmUpdateModal(
                        messageId,
                        email.matched_application_id,
                        ext.company_name || email.matched_company_name,
                        ext.job_title || email.matched_job_title,
                        email.matched_current_status,
                        ext.proposed_status || 'Interviewing',
                        ext.key_summary || email.subject
                    );
                };
            } else {
                updateBtn.classList.add('hidden');
            }
        }

        modal.classList.remove('hidden');
    } catch (err) {
        console.error('Error opening email details modal:', err);
    }
}

async function openDraftReplyModal(messageId) {
    const modal = document.getElementById('email-draft-modal');
    const textarea = document.getElementById('email-draft-textarea');
    const copyText = document.getElementById('email-draft-copy-text');
    if (!modal) return;

    if (textarea) textarea.value = 'Generating AI recruiter reply draft...';
    if (copyText) copyText.innerText = 'Copy to Clipboard';
    modal.classList.remove('hidden');

    try {
        const res = await fetch('/api/email-intelligence/draft-reply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: messageId })
        });
        if (res.ok) {
            const data = await res.json();
            if (textarea) textarea.value = data.draft || '';
        } else {
            if (textarea) textarea.value = 'Could not generate draft reply.';
        }
    } catch (err) {
        console.error('Error drafting reply:', err);
        if (textarea) textarea.value = 'Error generating draft reply.';
    }
}

function openConfirmUpdateModal(messageId, appId, company, role, oldStatus, newStatus, reason) {
    const modal = document.getElementById('email-confirm-update-modal');
    if (!modal) return;

    document.getElementById('confirm-update-company').innerText = company;
    document.getElementById('confirm-update-role').innerText = role;
    document.getElementById('confirm-update-old-status').innerText = oldStatus;
    document.getElementById('confirm-update-new-status').innerText = newStatus;
    document.getElementById('confirm-update-reason').innerText = `"${reason || 'Update detected in recruitment email.'}"`;

    const submitBtn = document.getElementById('confirm-update-submit-btn');
    if (submitBtn) {
        submitBtn.onclick = () => confirmUpdateAction(messageId, appId, newStatus);
    }

    modal.classList.remove('hidden');
}

async function confirmUpdateAction(messageId, appId, newStatus) {
    const modal = document.getElementById('email-confirm-update-modal');
    try {
        const res = await fetch('/api/email-intelligence/confirm-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message_id: messageId,
                application_id: appId,
                new_status: newStatus
            })
        });
        if (res.ok) {
            if (modal) modal.classList.add('hidden');
            showEmailIntelligenceAlert('success', 'Application Updated', 'Successfully updated application status from email update.');
            setTimeout(() => hideEmailIntelligenceAlert(), 3500);
            loadEmailIntelligencePage();
            loadDashboardEmailUpdates();
        } else {
            const err = await res.json();
            showEmailIntelligenceAlert('error', 'Update Failed', err.error || 'Failed to update application.');
        }
    } catch (err) {
        console.error('Error confirming match:', err);
    }
}

async function ignoreEmailAction(messageId) {
    try {
        const res = await fetch('/api/email-intelligence/ignore-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: messageId })
        });
        if (res.ok) {
            const card = document.getElementById(`email-card-${messageId}`);
            if (card) {
                card.style.opacity = '0.5';
                const actions = card.querySelector('.email-card-actions');
                if (actions) actions.innerHTML = '<span class="badge-ignored-pill">Proposal Ignored</span>';
            }
        }
    } catch (err) {
        console.error('Error ignoring email update:', err);
    }
}

async function addEmailCalendarEvent(messageId, appId, date, eventType) {
    try {
        const res = await fetch('/api/email-intelligence/add-calendar-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message_id: messageId,
                application_id: appId,
                event_date: date,
                event_type: eventType
            })
        });
        const data = await res.json();
        if (res.ok) {
            showEmailIntelligenceAlert('success', 'Event Added', data.message || 'Event added to calendar.');
            setTimeout(() => hideEmailIntelligenceAlert(), 3500);
            loadEmailIntelligencePage();
        } else {
            showEmailIntelligenceAlert('error', 'Failed to Add Event', data.error || 'Failed to add calendar event.');
        }
    } catch (err) {
        console.error('Error adding calendar event:', err);
    }
}

async function loadApplicationTimeline(appId) {
    const container = document.getElementById('details-timeline-container');
    if (!container) return;

    try {
        const res = await fetch(`/api/applications/${appId}/timeline`);
        if (!res.ok) return;
        const data = await res.json();
        const events = data.timeline || [];

        if (events.length === 0) {
            container.innerHTML = '<div class="timeline-empty-text">No activity events recorded yet.</div>';
            return;
        }

        container.innerHTML = '';
        events.forEach((ev, idx) => {
            const item = document.createElement('div');
            item.className = 'timeline-item';
            const isLast = idx === events.length - 1;

            let iconChar = '✓';
            if (ev.event_type && ev.event_type.includes('INTERVIEW')) iconChar = '🎤';
            else if (ev.event_type && ev.event_type.includes('ASSESSMENT')) iconChar = '⚡';
            else if (ev.event_type && ev.event_type.includes('OFFER')) iconChar = '🏆';
            else if (ev.event_type && ev.event_type.includes('REJECTION')) iconChar = '❌';

            item.innerHTML = `
                <div class="timeline-dot ${isLast ? 'timeline-dot-active' : ''}">${iconChar}</div>
                <div class="timeline-content">
                    <div class="timeline-header">
                        <strong class="timeline-title">${ev.event_title}</strong>
                        <span class="timeline-date">${ev.event_date ? ev.event_date.split(' ')[0] : ''}</span>
                    </div>
                    ${ev.event_description ? `<p class="timeline-desc">${ev.event_description}</p>` : ''}
                    <span class="timeline-source-badge">${ev.source || 'MANUAL'}</span>
                </div>
            `;
            container.appendChild(item);
        });
    } catch (err) {
        console.error('Error loading application timeline:', err);
    }
}

async function loadDashboardEmailUpdates() {
    const container = document.getElementById('dashboard-email-updates-container');
    if (!container) return;

    try {
        const statusRes = await fetch('/api/email-intelligence/status');
        if (!statusRes.ok) return;
        const statusData = await statusRes.json();

        if (!statusData.connected) {
            container.innerHTML = `
                <div class="upcoming-empty-card" style="cursor: pointer;" onclick="switchView('email-intelligence')">
                    <span class="upcoming-empty-text">📬 Connect Gmail to detect real-time recruiter emails, interviews, and updates &rarr;</span>
                </div>
            `;
            return;
        }

        const res = await fetch('/api/email-intelligence/emails');
        if (!res.ok) return;
        const data = await res.json();
        const emails = (data.emails || []).slice(0, 4);

        if (emails.length === 0) {
            container.innerHTML = `
                <div class="upcoming-empty-card">
                    <span class="upcoming-empty-text">No recent career updates detected in inbox.</span>
                </div>
            `;
            return;
        }

        container.innerHTML = '';
        emails.forEach(email => {
            const ext = email.extracted_data || {};
            const card = document.createElement('div');
            card.className = 'dashboard-email-mini-card';
            card.onclick = () => switchView('email-intelligence');

            let iconEmoji = '📝';
            if (email.classification === 'INTERVIEW_INVITATION' || email.classification === 'INTERVIEW_UPDATE') iconEmoji = '🎤';
            else if (email.classification === 'ASSESSMENT') iconEmoji = '⚡';
            else if (email.classification === 'OFFER') iconEmoji = '🏆';
            else if (email.classification === 'REJECTION') iconEmoji = '❌';

            const comp = ext.company_name || email.matched_company_name || 'Recruiter';
            const role = ext.job_title || email.matched_job_title || '';
            const cls = (email.classification || 'Update').replace(/_/g, ' ');

            card.innerHTML = `
                <div class="mini-card-icon">${iconEmoji}</div>
                <div class="mini-card-info">
                    <strong class="mini-card-company">${comp}</strong>
                    <span class="mini-card-role">${role || cls}</span>
                    <span class="mini-card-time">${email.received_at ? email.received_at.split(' ')[0] : 'Recent'}</span>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        console.error('Error loading dashboard email updates:', err);
    }
}

function initEmailIntelligenceEvents() {
    // 1. Sync button handler
    const syncBtn = document.getElementById('btn-sync-emails');
    if (syncBtn) {
        syncBtn.addEventListener('click', triggerEmailSync);
    }

    // 2. Disconnect modal handlers
    const disconnectBtn = document.getElementById('btn-disconnect-gmail');
    const disconnectModal = document.getElementById('email-disconnect-modal');
    const disconnectClose = document.getElementById('email-disconnect-close');
    const disconnectCancel = document.getElementById('email-disconnect-cancel-btn');
    const disconnectConfirm = document.getElementById('email-disconnect-confirm-btn');

    if (disconnectBtn && disconnectModal) {
        disconnectBtn.addEventListener('click', () => disconnectModal.classList.remove('hidden'));
    }
    if (disconnectClose && disconnectModal) {
        disconnectClose.addEventListener('click', () => disconnectModal.classList.add('hidden'));
    }
    if (disconnectCancel && disconnectModal) {
        disconnectCancel.addEventListener('click', () => disconnectModal.classList.add('hidden'));
    }
    if (disconnectConfirm) {
        disconnectConfirm.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/email-intelligence/disconnect', { method: 'POST' });
                if (res.ok) {
                    if (disconnectModal) disconnectModal.classList.add('hidden');
                    loadEmailIntelligencePage();
                    loadDashboardEmailUpdates();
                }
            } catch (err) {
                console.error('Error disconnecting Gmail:', err);
            }
        });
    }

    // 3. Filter pills handlers
    const filterPills = document.querySelectorAll('#email-filter-pills .filter-pill');
    filterPills.forEach(pill => {
        pill.addEventListener('click', () => {
            filterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const filterType = pill.dataset.filter || 'all';
            emailIntelligenceCache.activeFilter = filterType;
            renderEmailUpdatesList(emailIntelligenceCache.emails, filterType);
        });
    });

    // 4. Modal close handlers
    const detailsModal = document.getElementById('email-details-modal');
    const detailsClose = document.getElementById('email-modal-close-btn');
    if (detailsClose && detailsModal) {
        detailsClose.addEventListener('click', () => detailsModal.classList.add('hidden'));
    }

    const draftModal = document.getElementById('email-draft-modal');
    const draftClose = document.getElementById('email-draft-close-btn');
    const draftCancel = document.getElementById('email-draft-cancel-btn');
    const draftCopy = document.getElementById('email-draft-copy-btn');
    const draftTextarea = document.getElementById('email-draft-textarea');
    const draftCopyText = document.getElementById('email-draft-copy-text');

    if (draftClose && draftModal) draftClose.addEventListener('click', () => draftModal.classList.add('hidden'));
    if (draftCancel && draftModal) draftCancel.addEventListener('click', () => draftModal.classList.add('hidden'));
    if (draftCopy && draftTextarea) {
        draftCopy.addEventListener('click', () => {
            draftTextarea.select();
            navigator.clipboard.writeText(draftTextarea.value);
            if (draftCopyText) draftCopyText.innerText = 'Copied!';
            setTimeout(() => {
                if (draftCopyText) draftCopyText.innerText = 'Copy to Clipboard';
            }, 2000);
        });
    }

    const confirmUpdateModal = document.getElementById('email-confirm-update-modal');
    const confirmUpdateClose = document.getElementById('email-confirm-update-close');
    const confirmUpdateCancel = document.getElementById('confirm-update-cancel-btn');
    if (confirmUpdateClose && confirmUpdateModal) confirmUpdateClose.addEventListener('click', () => confirmUpdateModal.classList.add('hidden'));
    if (confirmUpdateCancel && confirmUpdateModal) confirmUpdateCancel.addEventListener('click', () => confirmUpdateModal.classList.add('hidden'));

    // 5. Check if navigated with ?view=email-intelligence or URL params
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('view') === 'email-intelligence') {
        switchView('email-intelligence');
    }
}



