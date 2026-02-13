/* ── AutoMinds Command Center — Logic + Particle Background ── */
const API_BASE = window.location.origin;
let userId = null;
let activePanel = 'inbox';
let inboxLoaded = false;
let cachedEmails = [];

// ── Particle Background ──
(function initParticles() {
    const canvas = document.getElementById('bg-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, particles = [];
    const COLORS = ['rgba(59,130,246,0.3)', 'rgba(168,85,247,0.25)', 'rgba(34,197,94,0.2)'];

    function resize() { w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight; }
    window.addEventListener('resize', resize);
    resize();

    for (let i = 0; i < 60; i++) {
        particles.push({
            x: Math.random() * w, y: Math.random() * h,
            vx: (Math.random() - 0.5) * 0.3, vy: (Math.random() - 0.5) * 0.3,
            r: Math.random() * 1.5 + 0.5,
            color: COLORS[Math.floor(Math.random() * COLORS.length)]
        });
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(p => {
            p.x += p.vx; p.y += p.vy;
            if (p.x < 0) p.x = w; if (p.x > w) p.x = 0;
            if (p.y < 0) p.y = h; if (p.y > h) p.y = 0;
            ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = p.color; ctx.fill();
        });
        // connection lines
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 120) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(255,255,255,${0.03 * (1 - dist / 120)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(draw);
    }
    draw();
})();

// ── Panel switching ──
const panelMeta = {
    cortex: { title: 'Cortex', sub: 'Chat with your documents. Powered by RAG.', iconBg: 'rgba(59,130,246,0.08)',
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>' },
    inbox: { title: 'Inbox Pilot', sub: 'Automated email intelligence and briefings.', iconBg: 'rgba(34,197,94,0.08)',
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22C55E" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>' },
    echo: { title: 'Echo', sub: 'Your digital clone. Coming soon.', iconBg: 'rgba(168,85,247,0.08)',
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#A855F7" stroke-width="2"><path d="M12 3a9 9 0 019 9 9 9 0 01-9 9"/><path d="M12 7a5 5 0 015 5 5 5 0 01-5 5"/><circle cx="12" cy="12" r="1"/></svg>' },
    activity: { title: 'Activity Feed', sub: 'Everything your AI agent did — transparent and auditable.', iconBg: 'rgba(245,158,11,0.08)',
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>' },
    rules: { title: 'Email Rules', sub: 'If this happens, then do that — automatically.', iconBg: 'rgba(239,68,68,0.08)',
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>' },
    automations: { title: 'Schedules', sub: 'Recurring automations — weekly digests, monthly reports, cleanup.', iconBg: 'rgba(20,184,166,0.08)',
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#14B8A6" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' }
};

function switchPanel(panel) {
    activePanel = panel;
    const m = panelMeta[panel];
    document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
    document.getElementById('panel-' + panel).classList.remove('hidden');
    const icon = document.getElementById('topbar-icon');
    icon.innerHTML = m.svg; icon.style.background = m.iconBg;
    document.getElementById('topbar-title').textContent = m.title;
    document.getElementById('topbar-sub').textContent = m.sub;
    document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.panel === panel));
    // Auto-load inbox data when switching to Inbox Pilot
    if (panel === 'inbox' && userId && !inboxLoaded) {
        loadEmails();
        inboxLoaded = true;
    }
    if (panel === 'activity') loadActivity();
    if (panel === 'rules') loadRules();
    if (panel === 'automations') loadAutomations();
}

function logout() {
    localStorage.removeItem('autominds_user_id');
    localStorage.removeItem('autominds_email');
    localStorage.removeItem('autominds_name');
    window.location.href = '/auth/logout';
}

// ── Chat ──
function addMsg(sender, text, isUser) {
    const c = document.getElementById('chat-messages');
    const d = document.createElement('div');
    d.className = 'msg ' + (isUser ? 'msg-user' : 'msg-ai');
    d.innerHTML = `<div class="msg-header"><span class="msg-label ${isUser ? 'user-label' : 'ai-label'}">${isUser ? '' : '⚡ '}${sender}</span></div><div class="msg-body">${text}</div>`;
    c.appendChild(d);
    c.scrollTop = c.scrollHeight;
}

async function indexDocuments() {
    const folderId = document.getElementById('folder-id-input').value.trim();
    if (!folderId) { alert('Paste a Google Drive Folder ID first.'); return; }
    const btn = document.getElementById('index-btn');
    const status = document.getElementById('index-status');
    btn.disabled = true; btn.textContent = 'Indexing...';
    status.textContent = 'Connecting to Drive...'; status.className = 'idx-status';
    try {
        const res = await fetch(`${API_BASE}/ami/knowledge/sync`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, folder_id: folderId })
        });
        const data = await res.json();
        if (data.success) {
            status.textContent = `✓ ${data.files_processed} file(s) indexed`; status.className = 'idx-status success';
            addMsg('Cortex', `Index complete — <strong>${data.files_processed}</strong> document(s) ingested:\n• ${(data.files_indexed || []).join('\n• ')}\n\nYour knowledge base is ready.`, false);
        } else { status.textContent = `✗ ${data.detail || data.error}`; status.className = 'idx-status error'; }
    } catch (err) { status.textContent = `✗ ${err.message}`; status.className = 'idx-status error'; }
    finally { btn.disabled = false; btn.textContent = 'Index'; }
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const q = input.value.trim();
    if (!q) return;
    addMsg('You', q, true); input.value = '';
    addMsg('Cortex', '⏳ Searching knowledge base...', false);
    try {
        const res = await fetch(`${API_BASE}/ami/knowledge/query`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, question: q })
        });
        const data = await res.json();
        const c = document.getElementById('chat-messages');
        c.removeChild(c.lastChild);
        addMsg('Cortex', data.answer || 'No response received.', false);
    } catch (err) {
        const c = document.getElementById('chat-messages');
        c.removeChild(c.lastChild);
        addMsg('Cortex', `Error: ${err.message}`, false);
    }
}

// ══════════════════════════════════════════════════════════
// INBOX PILOT — Email, Briefing, Drafts, Agent
// ══════════════════════════════════════════════════════════

function switchInboxTab(tab) {
    document.querySelectorAll('.inbox-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.querySelectorAll('.inbox-content').forEach(c => c.classList.remove('active'));
    const el = document.getElementById('inbox-' + tab);
    if (el) el.classList.add('active');
    if (tab === 'briefing') loadBriefing();
    if (tab === 'drafts') loadDrafts();
    if (tab === 'agent') loadAgentStatus();
}

function refreshInbox() {
    const btn = document.querySelector('.btn-refresh');
    btn.classList.add('spinning');
    inboxLoaded = false;
    loadEmails().finally(() => setTimeout(() => btn.classList.remove('spinning'), 600));
}

function timeAgo(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return 'now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd';
    return d.toLocaleDateString();
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

async function loadEmails() {
    const list = document.getElementById('email-list');
    list.innerHTML = '<div class="inbox-loading"><div class="loader-ring"></div><span>Loading your inbox...</span></div>';
    try {
        const res = await fetch(`${API_BASE}/emails?user_id=${userId}&max_results=20&analyze=false`, { credentials: 'same-origin' });
        if (!res.ok) throw new Error(res.status === 400 ? 'No email accounts connected' : 'Failed to load emails');
        const data = await res.json();
        cachedEmails = data.emails || [];
        document.getElementById('email-count').textContent = cachedEmails.length;
        if (cachedEmails.length === 0) {
            list.innerHTML = '<div class="briefing-empty"><span class="big-emoji">🎉</span>Inbox zero! No unread emails.</div>';
            return;
        }
        list.innerHTML = '';
        cachedEmails.forEach((em, i) => {
            const row = document.createElement('div');
            row.className = 'email-row' + (em.is_read === false ? ' unread' : '');
            const pri = em.priority || 'normal';
            const cat = em.category || '';
            row.innerHTML = `
                <div class="email-priority ${pri}"></div>
                <div class="email-body-col">
                    <div class="email-sender">${esc(em.sender?.name || em.sender?.email || 'Unknown')}${em.is_vip ? ' <span class="vip-badge">VIP</span>' : ''}</div>
                    <div class="email-subject">${esc(em.subject)}</div>
                    <div class="email-preview">${esc(em.snippet || '')}</div>
                    ${cat ? `<span class="email-category cat-${cat}">${cat.replace('_', ' ')}</span>` : ''}
                </div>
                <div class="email-meta">
                    <div class="email-time">${timeAgo(em.date)}</div>
                    <div class="email-actions-row">
                        <button class="email-action-btn draft-btn" title="Draft reply" onclick="event.stopPropagation();draftReply(${i})">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                    </div>
                </div>`;
            row.onclick = () => showEmailDetail(i);
            list.appendChild(row);
        });
    } catch (err) {
        list.innerHTML = `<div class="briefing-empty"><span class="big-emoji">⚠️</span>${esc(err.message)}<br><small>Connect Gmail first via the landing page.</small></div>`;
    }
}

function showEmailDetail(idx) {
    const em = cachedEmails[idx];
    if (!em) return;
    document.getElementById('email-list').style.display = 'none';
    const detail = document.getElementById('email-detail');
    detail.classList.remove('hidden');
    const content = document.getElementById('email-detail-content');
    content.innerHTML = `
        <div class="detail-header">
            <div class="detail-subject">${esc(em.subject)}</div>
            <div class="detail-meta">
                <span class="detail-from">${esc(em.sender?.name || '')} &lt;${esc(em.sender?.email || '')}&gt;</span>
                <span>${timeAgo(em.date)}</span>
            </div>
        </div>
        ${em.summary ? `<div class="detail-summary"><div class="detail-summary-label">AI Summary</div><div class="detail-summary-text">${esc(em.summary)}</div></div>` : ''}
        <div class="detail-body">${esc(em.body_text || em.snippet || 'No body available')}</div>
        <div class="detail-actions">
            <button class="btn-glow green" onclick="draftReply(${idx})">✍️ Draft AI Reply</button>
            <button class="btn-glow" onclick="markRead('${em.id}')">✓ Mark Read</button>
        </div>
        <div id="draft-compose-area"></div>`;
}

function closeEmailDetail() {
    document.getElementById('email-detail').classList.add('hidden');
    document.getElementById('email-list').style.display = '';
}

async function markRead(emailId) {
    try {
        await fetch(`${API_BASE}/emails/${emailId}/read?user_id=${userId}`, { method: 'POST', credentials: 'same-origin' });
        refreshInbox();
    } catch (e) { console.error(e); }
}

async function draftReply(idx) {
    const em = cachedEmails[idx];
    if (!em) return;
    const area = document.getElementById('draft-compose-area') || document.createElement('div');
    area.innerHTML = `
        <div class="draft-compose">
            <h4>Instructions for AI draft reply to: ${esc(em.sender?.email)}</h4>
            <textarea id="draft-instructions" placeholder="e.g. Confirm the meeting for Monday 2pm, keep it brief and professional..."></textarea>
            <div class="draft-btns">
                <button class="btn-glow green" id="gen-draft-btn" onclick="generateDraft('${em.id}')">Generate Draft</button>
            </div>
            <div id="draft-result"></div>
        </div>`;
    // If we're in the list view, show detail first
    if (document.getElementById('email-detail').classList.contains('hidden')) {
        showEmailDetail(idx);
    }
}

async function generateDraft(emailId) {
    const btn = document.getElementById('gen-draft-btn');
    const result = document.getElementById('draft-result');
    const instructions = document.getElementById('draft-instructions')?.value || '';
    btn.disabled = true; btn.textContent = 'Generating...';
    result.innerHTML = '<div class="inbox-loading"><div class="loader-ring"></div><span>AI is drafting...</span></div>';
    try {
        const res = await fetch(`${API_BASE}/drafts?user_id=${userId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ email_id: emailId, instructions: instructions, tone: 'professional' })
        });
        const data = await res.json();
        if (data.draft) {
            result.innerHTML = `
                <div style="margin-top:12px;padding:16px;background:rgba(34,197,94,0.04);border:1px solid rgba(34,197,94,0.12);border-radius:12px;">
                    <div style="font-size:11px;font-weight:700;color:#22C55E;text-transform:uppercase;margin-bottom:8px;">AI Draft</div>
                    <div style="font-size:13px;color:#a1a1aa;line-height:1.7;white-space:pre-wrap;">${esc(data.draft.body)}</div>
                    <div style="display:flex;gap:8px;margin-top:12px;">
                        <button class="draft-btn-approve" onclick="approveDraft('${data.draft.id}')">✓ Send</button>
                        <button class="draft-btn-reject" onclick="rejectDraft('${data.draft.id}')">✗ Discard</button>
                    </div>
                </div>`;
        } else {
            result.innerHTML = `<div style="color:#EF4444;margin-top:8px;">${esc(data.detail || 'Failed to generate draft')}</div>`;
        }
    } catch (err) {
        result.innerHTML = `<div style="color:#EF4444;margin-top:8px;">Error: ${esc(err.message)}</div>`;
    } finally { btn.disabled = false; btn.textContent = 'Generate Draft'; }
}

async function approveDraft(draftId) {
    try {
        const res = await fetch(`${API_BASE}/drafts/${draftId}/approve?user_id=${userId}`, { method: 'POST', credentials: 'same-origin' });
        const data = await res.json();
        if (data.status === 'sent') alert('Email sent successfully!');
        else alert('Error: ' + JSON.stringify(data));
    } catch (e) { alert('Failed: ' + e.message); }
}

async function rejectDraft(draftId) {
    try {
        await fetch(`${API_BASE}/drafts/${draftId}/reject?user_id=${userId}`, { method: 'POST', credentials: 'same-origin' });
        document.getElementById('draft-result').innerHTML = '<div style="color:var(--t3);margin-top:8px;">Draft discarded.</div>';
    } catch (e) { console.error(e); }
}

// ── Briefing ──
async function loadBriefing() {
    const container = document.getElementById('briefing-content');
    container.innerHTML = '<div class="inbox-loading"><div class="loader-ring"></div><span>Loading briefing...</span></div>';
    try {
        const res = await fetch(`${API_BASE}/briefing?user_id=${userId}`, { credentials: 'same-origin' });
        if (!res.ok) throw new Error(res.status === 400 ? 'No email accounts connected' : 'Failed to load briefing');
        const data = await res.json();
        if (data.total_unread === 0 || !data.full_text) {
            container.innerHTML = '<div class="briefing-empty"><span class="big-emoji">🎉</span>Inbox zero! No briefing needed.</div>';
            return;
        }
        const urgent = data.urgent_count || 0;
        const total = data.total_unread || data.emails_analyzed || 0;
        const actionable = data.action_required_count || 0;
        container.innerHTML = `
            <div class="briefing-card">
                <div class="briefing-header">
                    <div class="briefing-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#22C55E" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg></div>
                    <div><div class="briefing-title">Daily Briefing</div><div class="briefing-date">${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</div></div>
                </div>
                <div class="briefing-stats">
                    <div class="b-stat"><div class="b-stat-val blue">${total}</div><div class="b-stat-label">Unread</div></div>
                    <div class="b-stat"><div class="b-stat-val amber">${urgent}</div><div class="b-stat-label">Urgent</div></div>
                    <div class="b-stat"><div class="b-stat-val green">${actionable}</div><div class="b-stat-label">Action Needed</div></div>
                </div>
                <div class="briefing-body">${esc(data.full_text)}</div>
            </div>`;
    } catch (err) {
        container.innerHTML = `<div class="briefing-empty"><span class="big-emoji">⚠️</span>${esc(err.message)}</div>`;
    }
}

// ── Drafts ──
async function loadDrafts() {
    const list = document.getElementById('drafts-list');
    list.innerHTML = '<div class="inbox-loading"><div class="loader-ring"></div><span>Loading drafts...</span></div>';
    try {
        const res = await fetch(`${API_BASE}/drafts?user_id=${userId}`, { credentials: 'same-origin' });
        const data = await res.json();
        const drafts = data.drafts || [];
        document.getElementById('draft-count').textContent = drafts.length;
        if (drafts.length === 0) {
            list.innerHTML = '<div class="drafts-empty">No drafts yet. Open an email and click "Draft AI Reply" to create one.</div>';
            return;
        }
        list.innerHTML = '';
        drafts.forEach(d => {
            const draft = d.draft || d;
            const card = document.createElement('div');
            card.className = 'draft-card';
            const st = draft.status || 'pending';
            card.innerHTML = `
                <div class="draft-to">To: <strong>${esc(draft.to)}</strong></div>
                <div class="draft-subject">${esc(draft.subject)}</div>
                <div class="draft-body-preview">${esc(draft.body)}</div>
                <div style="display:flex;align-items:center;gap:12px;">
                    <span class="draft-status ${st}">${st}</span>
                    ${st === 'pending' ? `
                        <div class="draft-actions">
                            <button class="draft-btn-approve" onclick="approveDraft('${draft.id}')">✓ Send</button>
                            <button class="draft-btn-reject" onclick="rejectDraft('${draft.id}')">✗ Discard</button>
                        </div>` : ''}
                </div>`;
            list.appendChild(card);
        });
    } catch (err) {
        list.innerHTML = `<div class="drafts-empty">Error: ${esc(err.message)}</div>`;
    }
}

// ── Agent ──
async function loadAgentStatus() {
    try {
        const res = await fetch(`${API_BASE}/agent/status`, { credentials: 'same-origin' });
        const data = await res.json();
        document.getElementById('agent-enabled').textContent = data.enabled ? '✓ Active' : '○ Disabled';
        document.getElementById('agent-enabled').style.color = data.enabled ? '#22C55E' : '#a1a1aa';
        const st = data.status || {};
        document.getElementById('agent-last-run').textContent = st.last_run ? timeAgo(st.last_run) + ' ago' : 'Never';
        document.getElementById('agent-processed').textContent = st.total_processed || '0';
    } catch (e) { console.error(e); }
}

async function runAgentNow() {
    const btn = document.getElementById('run-agent-btn');
    btn.disabled = true; btn.textContent = 'Running...';
    try {
        const res = await fetch(`${API_BASE}/agent/run-now?user_id=${userId}`, { method: 'POST', credentials: 'same-origin' });
        const data = await res.json();
        alert('Agent cycle complete! ' + (data.result?.summary || JSON.stringify(data)));
        loadAgentStatus();
        refreshInbox();
    } catch (err) { alert('Error: ' + err.message); }
    finally { btn.disabled = false; btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Agent Now'; }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', function() {
    fetch(`${API_BASE}/auth/check`, { credentials: 'same-origin' })
        .then(r => {
            if (!r.ok) {
                localStorage.removeItem('autominds_user_id');
                window.location.href = '/auth/google';
                return null;
            }
            return r.json();
        })
        .then(data => {
            if (!data) return;
            userId = data.user_id;
            const displayName = data.name || data.email || 'User';
            localStorage.setItem('autominds_user_id', data.user_id);
            localStorage.setItem('autominds_email', data.email);
            localStorage.setItem('autominds_name', displayName);
            document.getElementById('user-display-name').textContent = displayName;
            document.getElementById('user-display-email').textContent = data.email || '';
            document.getElementById('user-avatar').textContent = (displayName.charAt(0) || '?').toUpperCase();
            // Personalize quick actions greeting
            const qaTitle = document.querySelector('.qa-title');
            if (qaTitle) {
                const firstName = displayName.split(' ')[0];
                qaTitle.textContent = `Hey ${firstName}! Here's what I can do`;
            }
            // Check if quick actions were dismissed
            if (localStorage.getItem('autominds_qa_dismissed')) {
                const qa = document.getElementById('quick-actions');
                if (qa) qa.style.display = 'none';
            }
            // Auto-load inbox since it's the default panel
            if (!inboxLoaded) {
                loadEmails();
                inboxLoaded = true;
            }
            return fetch(`${API_BASE}/ami/knowledge/status/${userId}`);
        })
        .then(r => r ? r.json() : null)
        .then(data => {
            if (data && data.has_knowledge_base) {
                document.getElementById('index-status').textContent = '✓ Knowledge base active';
                document.getElementById('index-status').className = 'idx-status success';
            }
        }).catch(() => {});
});

// ══════════════════════════════════════════════════════════════
// QUICK ACTIONS
// ══════════════════════════════════════════════════════════════
function quickAction(action) {
    switch (action) {
        case 'summarize':
            switchInboxTab('briefing');
            break;
        case 'urgent':
            switchInboxTab('emails');
            setTimeout(() => filterEmailsByPriority('urgent'), inboxLoaded ? 100 : 2000);
            break;
        case 'drafts':
            switchInboxTab('drafts');
            break;
        case 'agent':
            switchInboxTab('agent');
            runAgentNow();
            break;
        case 'unread':
            switchInboxTab('emails');
            if (!inboxLoaded) { loadEmails(); inboxLoaded = true; }
            else refreshInbox();
            break;
        case 'weekly':
            switchInboxTab('briefing');
            break;
    }
    // Collapse quick actions after use
    const qa = document.getElementById('quick-actions');
    if (qa) qa.classList.add('qa-collapsed');
}

function dismissQuickActions() {
    const qa = document.getElementById('quick-actions');
    if (qa) {
        qa.style.display = 'none';
        localStorage.setItem('autominds_qa_dismissed', '1');
    }
}

function filterEmailsByPriority(priority) {
    const rows = document.querySelectorAll('.email-row');
    let visibleCount = 0;
    rows.forEach(row => {
        const priDot = row.querySelector('.email-priority');
        if (priDot && priDot.classList.contains(priority)) {
            row.style.display = '';
            visibleCount++;
        } else {
            row.style.display = 'none';
        }
    });
    const list = document.getElementById('email-list');
    let badge = document.getElementById('filter-badge');
    if (!badge) {
        badge = document.createElement('div');
        badge.id = 'filter-badge';
        badge.className = 'filter-badge';
        list.parentNode.insertBefore(badge, list);
    }
    badge.innerHTML = `<span>Showing: <strong>${priority}</strong> emails (${visibleCount})</span><button onclick="clearFilter()" class="filter-clear">✕ Show all</button>`;
    badge.style.display = 'flex';
}

function clearFilter() {
    document.querySelectorAll('.email-row').forEach(row => row.style.display = '');
    const badge = document.getElementById('filter-badge');
    if (badge) badge.style.display = 'none';
}

// ── Activity Feed ──
async function loadActivity() {
    const feed = document.getElementById('activity-feed');
    if (!feed) return;
    feed.innerHTML = '<div class="activity-loading"><div class="spinner-sm"></div> Loading activity...</div>';
    try {
        const res = await fetch(`${API_BASE}/activity?user_id=${userId}&limit=50`);
        if (!res.ok) throw new Error('Failed to load activity');
        const data = await res.json();
        const logs = data.logs || [];
        if (logs.length === 0) {
            feed.innerHTML = '<div class="activity-empty"><p>No activity yet. Your AI agent actions will appear here.</p></div>';
            return;
        }
        feed.innerHTML = '';
        logs.forEach(log => {
            const actions = log.actions_taken || {};
            const items = actions.actions || [];
            const card = document.createElement('div');
            card.className = 'activity-card';
            const time = log.timestamp ? new Date(log.timestamp).toLocaleString() : '';
            const subject = actions.subject || 'Unknown email';
            const from = actions.from_name || actions.from || '';
            const priority = actions.priority || 'normal';
            const priBadge = `<span class="pri-badge pri-${priority}">${priority}</span>`;
            const actionTags = items.map(a => {
                const icons = { labeled: '🏷️', task_created: '✅', draft_created: '📝' };
                return `<span class="action-tag">${icons[a.type] || '⚡'} ${a.type.replace('_', ' ')}${a.label ? ': ' + a.label : ''}</span>`;
            }).join('');
            card.innerHTML = `
                <div class="activity-time">${time}</div>
                <div class="activity-subject">${subject} ${priBadge}</div>
                <div class="activity-from">From: ${from}</div>
                <div class="activity-actions">${actionTags || '<span class="action-tag">📋 Processed</span>'}</div>
            `;
            feed.appendChild(card);
        });
    } catch (e) {
        feed.innerHTML = `<div class="activity-empty"><p>Could not load activity: ${e.message}</p></div>`;
    }
}

// ── Rules ──
let rulesCache = [];

function showRuleBuilder() {
    document.getElementById('rule-builder').classList.remove('hidden');
    document.getElementById('rule-empty')?.classList.add('hidden');
}

function hideRuleBuilder() {
    document.getElementById('rule-builder').classList.add('hidden');
    document.getElementById('rule-name').value = '';
    document.getElementById('rule-trigger').value = 'email_received';
    document.getElementById('rule-condition-input').value = '';
    document.getElementById('rule-action').value = 'label';
    document.getElementById('rule-action-config').value = '';
    if (rulesCache.length === 0) document.getElementById('rule-empty')?.classList.remove('hidden');
}

function updateRuleConditions() {
    const trigger = document.getElementById('rule-trigger').value;
    const input = document.getElementById('rule-condition-input');
    const placeholders = {
        email_received: 'e.g. from:boss@company.com',
        priority_high: 'Auto-triggered for high priority',
        vip_sender: 'VIP senders are auto-detected',
        keyword_match: 'e.g. invoice, payment, urgent'
    };
    input.placeholder = placeholders[trigger] || 'Enter condition...';
    if (trigger === 'priority_high' || trigger === 'vip_sender') {
        input.value = ''; input.disabled = true;
    } else {
        input.disabled = false;
    }
}

function updateRuleActionConfig() {
    const action = document.getElementById('rule-action').value;
    const input = document.getElementById('rule-action-config');
    const placeholders = {
        label: 'Label name, e.g. Important',
        draft_reply: 'Reply instructions, e.g. Thank them and confirm receipt',
        create_task: 'Task description, e.g. Follow up by Friday',
        forward: 'Forward to email, e.g. team@company.com',
        archive: 'No config needed'
    };
    input.placeholder = placeholders[action] || 'Configuration...';
    input.disabled = (action === 'archive');
    if (action === 'archive') input.value = '';
}

async function saveRule() {
    const name = document.getElementById('rule-name').value.trim();
    const trigger = document.getElementById('rule-trigger').value;
    const conditionRaw = document.getElementById('rule-condition-input').value.trim();
    const action = document.getElementById('rule-action').value;
    const actionConfig = document.getElementById('rule-action-config').value.trim();
    if (!name) { alert('Give your rule a name.'); return; }
    const conditions = {};
    if (trigger === 'email_received' && conditionRaw) {
        if (conditionRaw.startsWith('from:')) conditions.from = conditionRaw.replace('from:', '').trim();
        else conditions.contains = conditionRaw;
    } else if (trigger === 'keyword_match' && conditionRaw) {
        conditions.keywords = conditionRaw.split(',').map(k => k.trim());
    }
    const body = {
        name, trigger_type: trigger, conditions,
        action_type: action,
        action_config: actionConfig ? { value: actionConfig } : {},
        enabled: true
    };
    try {
        const res = await fetch(`${API_BASE}/user/rules?user_id=${userId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error('Failed to save rule');
        hideRuleBuilder();
        loadRules();
    } catch (e) { alert('Error saving rule: ' + e.message); }
}

async function deleteRule(ruleId) {
    if (!confirm('Delete this rule?')) return;
    try {
        await fetch(`${API_BASE}/user/rules/${ruleId}?user_id=${userId}`, { method: 'DELETE' });
        loadRules();
    } catch (e) { alert('Error deleting rule: ' + e.message); }
}

async function toggleRule(ruleId) {
    try {
        await fetch(`${API_BASE}/user/rules/${ruleId}/toggle?user_id=${userId}`, { method: 'PUT' });
        loadRules();
    } catch (e) { alert('Error toggling rule: ' + e.message); }
}

async function loadRules() {
    const list = document.getElementById('rules-list');
    const empty = document.getElementById('rule-empty');
    if (!list) return;
    list.innerHTML = '<div class="activity-loading"><div class="spinner-sm"></div> Loading rules...</div>';
    try {
        const res = await fetch(`${API_BASE}/user/rules?user_id=${userId}`);
        if (!res.ok) throw new Error('Failed to load rules');
        const data = await res.json();
        rulesCache = data.rules || [];
        if (rulesCache.length === 0) {
            list.innerHTML = '';
            if (empty) empty.classList.remove('hidden');
            return;
        }
        if (empty) empty.classList.add('hidden');
        list.innerHTML = '';
        rulesCache.forEach(rule => {
            const card = document.createElement('div');
            card.className = 'rule-card';
            const statusClass = rule.enabled ? 'rule-active' : 'rule-disabled';
            const statusText = rule.enabled ? 'Active' : 'Paused';
            card.innerHTML = `
                <div class="rule-card-header">
                    <span class="rule-card-name">${rule.name}</span>
                    <span class="rule-status ${statusClass}">${statusText}</span>
                </div>
                <div class="rule-card-detail">
                    <span class="rule-trigger-badge">${rule.trigger_type.replace('_', ' ')}</span>
                    → <span class="rule-action-badge">${rule.action_type.replace('_', ' ')}</span>
                </div>
                <div class="rule-card-meta">Triggered ${rule.times_triggered || 0} times</div>
                <div class="rule-card-actions">
                    <button onclick="toggleRule('${rule.id}')" class="btn-sm">${rule.enabled ? '⏸ Pause' : '▶ Enable'}</button>
                    <button onclick="deleteRule('${rule.id}')" class="btn-sm btn-danger">🗑 Delete</button>
                </div>
            `;
            list.appendChild(card);
        });
    } catch (e) {
        list.innerHTML = `<div class="activity-empty"><p>Could not load rules: ${e.message}</p></div>`;
    }
}

// ── Automations / Schedules ──
let automationsCache = [];

function showAutoBuilder() {
    document.getElementById('auto-builder').classList.remove('hidden');
    document.getElementById('auto-empty')?.classList.add('hidden');
}

function hideAutoBuilder() {
    document.getElementById('auto-builder').classList.add('hidden');
    document.getElementById('auto-name').value = '';
    document.getElementById('auto-schedule').value = 'weekly';
    document.getElementById('auto-day').value = '1';
    document.getElementById('auto-hour').value = '9';
    document.getElementById('auto-minute').value = '0';
    document.getElementById('auto-action').value = 'weekly_digest';
    if (automationsCache.length === 0) document.getElementById('auto-empty')?.classList.remove('hidden');
}

async function saveAutomation() {
    const name = document.getElementById('auto-name').value.trim();
    const schedule = document.getElementById('auto-schedule').value;
    const day = parseInt(document.getElementById('auto-day').value);
    const hour = parseInt(document.getElementById('auto-hour').value);
    const minute = parseInt(document.getElementById('auto-minute').value);
    const action = document.getElementById('auto-action').value;
    if (!name) { alert('Give your automation a name.'); return; }
    const body = {
        name, schedule_type: schedule, action, hour, minute, enabled: true,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    };
    if (schedule === 'weekly') body.day_of_week = day;
    if (schedule === 'monthly') body.day_of_month = day;
    try {
        const res = await fetch(`${API_BASE}/user/automations?user_id=${userId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error('Failed to save automation');
        hideAutoBuilder();
        loadAutomations();
    } catch (e) { alert('Error saving automation: ' + e.message); }
}

async function deleteAutomation(autoId) {
    if (!confirm('Delete this automation?')) return;
    try {
        await fetch(`${API_BASE}/user/automations/${autoId}?user_id=${userId}`, { method: 'DELETE' });
        loadAutomations();
    } catch (e) { alert('Error deleting automation: ' + e.message); }
}

function quickSchedule(type) {
    const presets = {
        weekly_digest: { name: 'Weekly Digest', schedule: 'weekly', day: 1, hour: 9, minute: 0, action: 'weekly_digest' },
        monthly_report: { name: 'Monthly Report', schedule: 'monthly', day: 1, hour: 9, minute: 0, action: 'monthly_report' },
        followup_alerts: { name: 'Follow-Up Alerts', schedule: 'daily', day: 0, hour: 10, minute: 0, action: 'followup_check' },
        weekend_cleanup: { name: 'Weekend Cleanup', schedule: 'weekly', day: 6, hour: 18, minute: 0, action: 'cleanup' }
    };
    const p = presets[type];
    if (!p) return;
    document.getElementById('auto-name').value = p.name;
    document.getElementById('auto-schedule').value = p.schedule;
    document.getElementById('auto-day').value = p.day;
    document.getElementById('auto-hour').value = p.hour;
    document.getElementById('auto-minute').value = p.minute;
    document.getElementById('auto-action').value = p.action;
    showAutoBuilder();
}

async function loadAutomations() {
    const list = document.getElementById('automations-list');
    const empty = document.getElementById('auto-empty');
    if (!list) return;
    list.innerHTML = '<div class="activity-loading"><div class="spinner-sm"></div> Loading automations...</div>';
    try {
        const res = await fetch(`${API_BASE}/user/automations?user_id=${userId}`);
        if (!res.ok) throw new Error('Failed to load automations');
        const data = await res.json();
        automationsCache = data.automations || [];
        if (automationsCache.length === 0) {
            list.innerHTML = '';
            if (empty) empty.classList.remove('hidden');
            return;
        }
        if (empty) empty.classList.add('hidden');
        list.innerHTML = '';
        automationsCache.forEach(auto => {
            const card = document.createElement('div');
            card.className = 'auto-card';
            const schedDesc = auto.schedule_type === 'daily' ? 'Every day'
                : auto.schedule_type === 'weekly' ? `Every ${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][auto.day_of_week || 0]}`
                : `Day ${auto.day_of_month || 1} of month`;
            const timeStr = `${String(auto.hour || 0).padStart(2,'0')}:${String(auto.minute || 0).padStart(2,'0')}`;
            const lastRun = auto.last_run ? new Date(auto.last_run).toLocaleString() : 'Never';
            card.innerHTML = `
                <div class="auto-card-header">
                    <span class="auto-card-name">${auto.name}</span>
                    <span class="rule-status ${auto.enabled ? 'rule-active' : 'rule-disabled'}">${auto.enabled ? 'Active' : 'Paused'}</span>
                </div>
                <div class="auto-card-detail">
                    <span class="auto-sched-badge">${schedDesc} at ${timeStr}</span>
                    → <span class="rule-action-badge">${auto.action.replace('_', ' ')}</span>
                </div>
                <div class="auto-card-meta">Runs: ${auto.run_count || 0} · Last: ${lastRun}</div>
                <div class="rule-card-actions">
                    <button onclick="deleteAutomation('${auto.id}')" class="btn-sm btn-danger">🗑 Delete</button>
                </div>
            `;
            list.appendChild(card);
        });
    } catch (e) {
        list.innerHTML = `<div class="activity-empty"><p>Could not load automations: ${e.message}</p></div>`;
    }
}
