// Kiosk Terminal Real-Time HUD and Audio Feedback
document.addEventListener('DOMContentLoaded', () => {
  startClock();
  loadInitialTicker();
  loadKioskMode();
  connectWebSocket();
});

// 1. Digital Clock
function startClock() {
  const timeEl = document.getElementById('kiosk-time');
  const dateEl = document.getElementById('kiosk-date');

  function update() {
    const now = new Date();
    if (timeEl) {
      timeEl.textContent = now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    }
    if (dateEl) {
      dateEl.textContent = now.toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    }
  }

  update();
  setInterval(update, 1000);
}

// 2. High-Tech Audio Synthesis (No external file needed!)
function playChime(isCheckIn = true) {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    // Check-in: bright double chirp (660Hz -> 880Hz), Check-out: pleasant lower tone (550Hz)
    const freq = isCheckIn ? 880 : 587;
    osc.frequency.setValueAtTime(freq, ctx.currentTime);

    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) {
    console.warn('Audio chime note:', e);
  }
}

let voiceEnabled = true;

function speakVoice(text) {
  if (!voiceEnabled) return;
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel(); // Stop any pending speech
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    utterance.volume = 0.9;
    window.speechSynthesis.speak(utterance);
  }
}

window.toggleAudio = function(btn) {
  voiceEnabled = !voiceEnabled;
  const icon = document.getElementById('audio-icon');
  const text = document.getElementById('audio-text');
  if (voiceEnabled) {
    if (icon) {
      icon.innerHTML = '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>';
    }
    if (text) text.textContent = 'Voice Feedback: Active';
  } else {
    if (icon) {
      icon.innerHTML = '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line>';
    }
    if (text) text.textContent = 'Voice Feedback: Muted';
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
};

window.toggleFullscreen = function() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(err => console.log(err));
  } else {
    document.exitFullscreen().catch(err => console.log(err));
  }
};

// 3. Floating HUD Toast
let toastTimer = null;
function showPunchToast(punch) {
  const toast = document.getElementById('kiosk-toast');
  const nameEl = document.getElementById('kiosk-toast-name');
  const typeEl = document.getElementById('kiosk-toast-type');
  const avatarEl = document.getElementById('kiosk-toast-avatar');

  if (!toast) return;

  nameEl.textContent = punch.employee_name;
  typeEl.textContent = `${punch.punch_type.replace('_', ' ')} CONFIRMED (${punch.confidence} MATCH)`;
  
  if (punch.snapshot_url) {
    avatarEl.src = punch.snapshot_url;
  } else {
    avatarEl.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="%2310b981"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>';
  }

  // Border color based on punch type
  const isCheckIn = punch.punch_type === 'CHECK_IN';
  toast.style.borderColor = isCheckIn ? 'rgba(16, 185, 129, 0.6)' : 'rgba(6, 182, 212, 0.6)';
  typeEl.style.color = isCheckIn ? '#34d399' : '#38bdf8';

  toast.classList.add('active');

  // Play audio chime and speak
  playChime(isCheckIn);
  const voiceMsg = isCheckIn
    ? `Welcome, ${punch.employee_name}. Check-in recorded.`
    : `Goodbye, ${punch.employee_name}. Check-out recorded.`;
  speakVoice(voiceMsg);

  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove('active');
  }, 4200);
}

// 4. Side Ticker Drawer
function prependTickerItem(punch) {
  const list = document.getElementById('kiosk-ticker-list');
  if (!list) return;

  // Remove empty placeholder if present
  const empty = list.querySelector('.empty-ticker');
  if (empty) empty.remove();

  const isCheckIn = punch.punch_type === 'CHECK_IN';
  const badgeClass = isCheckIn ? 'badge-success' : 'badge-info';

  const card = document.createElement('div');
  card.className = 'ticker-card';
  card.innerHTML = `
    ${punch.snapshot_url 
      ? `<img src="${punch.snapshot_url}" class="ticker-avatar" alt="${punch.employee_name}" />` 
      : `<div class="ticker-avatar" style="display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;">${punch.employee_name.charAt(0)}</div>`}
    <div class="ticker-details">
      <div class="ticker-name">${punch.employee_name}</div>
      <div class="ticker-meta">${punch.department} | ${punch.employee_code}</div>
    </div>
    <div class="ticker-badge-col">
      <span class="badge ${badgeClass}">${punch.punch_type}</span>
      <span class="ticker-time">${punch.timestamp}</span>
    </div>
  `;

  list.insertBefore(card, list.firstChild);

  // Keep max 20 items
  while (list.children.length > 20) {
    list.removeChild(list.lastChild);
  }
}

async function loadInitialTicker() {
  const list = document.getElementById('kiosk-ticker-list');
  if (!list) return;

  try {
    const res = await fetch('/api/attendance/ticker');
    const items = await res.json();
    if (!items || items.length === 0) {
      list.innerHTML = `<div class="empty-ticker" style="color: var(--text-muted); font-size: 0.82rem; text-align: center; padding: 30px;">Awaiting attendance punches...</div>`;
      return;
    }
    list.innerHTML = '';
    items.forEach(punch => prependTickerItem(punch));
  } catch (err) {
    console.warn('Initial ticker error:', err);
  }
}

// 5. WebSocket Real-Time Listener
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/api/ws/live-events`;
  const socket = new WebSocket(wsUrl);

  const statusDot = document.getElementById('kiosk-status-dot');
  const statusText = document.getElementById('kiosk-status-text');

  socket.onopen = () => {
    console.log('Kiosk WebSocket connected to server.');
    if (statusDot) statusDot.className = 'pulse-dot green';
    if (statusText) statusText.textContent = 'SYSTEM ONLINE & ACTIVE';
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && data.employee_name) {
        showPunchToast(data);
        prependTickerItem(data);
      }
    } catch (e) {
      console.warn('WS Message parse error:', e);
    }
  };

  socket.onclose = () => {
    console.warn('WebSocket closed. Reconnecting in 3s...');
    if (statusDot) statusDot.className = 'pulse-dot blue';
    if (statusText) statusText.textContent = 'RECONNECTING...';
    setTimeout(connectWebSocket, 3000);
  };

  socket.onerror = (err) => {
    console.error('WebSocket encountered error:', err);
    socket.close();
  };

  // Keep-alive heartbeat ping every 20s
  setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send('ping');
    }
  }, 20000);
}

// 6. Kiosk Punch Mode Control
async function loadKioskMode() {
  try {
    const res = await fetch('/api/attendance/mode');
    const data = await res.json();
    if (data && data.mode) {
      updateModeUI(data.mode);
    }
  } catch (e) {
    console.warn('Failed to load kiosk mode:', e);
  }
}

window.setKioskMode = async function(mode) {
  updateModeUI(mode); // Immediate visual feedback
  try {
    const res = await fetch('/api/attendance/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    });
    const data = await res.json();
    if (data && data.mode) {
      updateModeUI(data.mode);
      const voiceAnnouncement = mode === 'AUTO' 
        ? 'Kiosk set to automatic smart alternation' 
        : (mode === 'CHECK_IN' ? 'Kiosk set to check in only' : 'Kiosk set to check out only');
      speakVoice(voiceAnnouncement);
    }
  } catch (e) {
    console.error('Failed to set kiosk mode:', e);
  }
};

function updateModeUI(mode) {
  const buttons = document.querySelectorAll('.mode-btn');
  buttons.forEach(btn => {
    btn.classList.remove('btn-primary', 'active');
    btn.classList.add('btn-secondary');
  });

  const activeId = mode === 'AUTO' ? 'mode-auto' : (mode === 'CHECK_IN' ? 'mode-in' : 'mode-out');
  const activeBtn = document.getElementById(activeId);
  if (activeBtn) {
    activeBtn.classList.remove('btn-secondary');
    activeBtn.classList.add('btn-primary', 'active');
  }

  const badge = document.getElementById('kiosk-mode-badge');
  if (badge) {
    if (mode === 'AUTO') {
      badge.textContent = 'AUTO FLIP';
      badge.className = 'badge badge-info';
    } else if (mode === 'CHECK_IN') {
      badge.textContent = 'CHECK-IN ONLY';
      badge.className = 'badge badge-success';
    } else {
      badge.textContent = 'CHECK-OUT ONLY';
      badge.className = 'badge badge-warning';
    }
  }
}

