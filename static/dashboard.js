/* ── AutoMinds Command Center — Logic + Particle Background ── */
const API_BASE = window.location.origin;
let userId = null;
let activePanel = 'cortex';
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
        svg: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#A855F7" stroke-width="2"><path d="M12 3a9 9 0 019 9 9 9 0 01-9 9"/><path d="M12 7a5 5 0 015 5 5 5 0 01-5 5"/><circle cx="12" cy="12" r="1"/></svg>' }
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
