/* ── AutoMinds Command Center — Logic + Particle Background ── */
const API_BASE = window.location.origin;
let userId = null;
let activePanel = 'cortex';

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

// ── Init ──
document.addEventListener('DOMContentLoaded', function() {
    // Verify server-side session first
    fetch(`${API_BASE}/auth/check`, { credentials: 'same-origin' })
        .then(r => {
            if (!r.ok) {
                // No valid session — redirect to OAuth
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
            // Sync localStorage with session data
            localStorage.setItem('autominds_user_id', data.user_id);
            localStorage.setItem('autominds_email', data.email);
            localStorage.setItem('autominds_name', displayName);
            document.getElementById('user-display-name').textContent = displayName;
            document.getElementById('user-display-email').textContent = data.email || '';
            document.getElementById('user-avatar').textContent = (displayName.charAt(0) || '?').toUpperCase();
            document.getElementById('briefing-link').href = `/briefing?user_id=${userId}`;
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
