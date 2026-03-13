let currentUserId = null;
let allClients = [];
let pollInterval = null;

// ─── Загрузка клиентов ───────────────────────────────────────────────────────

async function loadClients() {
  const res = await fetch('/api/clients');
  allClients = await res.json();
  renderClients(allClients);
}

function renderClients(clients) {
  const container = document.getElementById('clients-list');
  if (!clients.length) {
    container.innerHTML = '<div class="text-center py-10 text-slate-400 text-sm">Диалогов пока нет</div>';
    return;
  }
  container.innerHTML = clients.map(c => {
    const initials = (c.user_name || '?').slice(0,2).toUpperCase();
    const time = c.last_time ? new Date(c.last_time).toLocaleTimeString('ru-RU', {hour:'2-digit',minute:'2-digit'}) : '';
    const preview = (c.last_msg || '').slice(0, 38) + ((c.last_msg || '').length > 38 ? '…' : '');
    const isActive = c.user_id === currentUserId;
    return `
      <div class="client-item ${isActive ? 'active' : ''}" data-uid="${c.user_id}" onclick="selectClient(${c.user_id})">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center text-sm font-bold shrink-0">${initials}</div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between">
              <span class="font-medium text-sm text-slate-800 truncate">${c.user_name || `ID ${c.user_id}`}</span>
              <span class="text-xs text-slate-400 ml-2 shrink-0">${time}</span>
            </div>
            <div class="text-xs text-slate-500 truncate mt-0.5">${preview}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ─── Выбор клиента ───────────────────────────────────────────────────────────

async function selectClient(userId) {
  currentUserId = userId;
  const client = allClients.find(c => c.user_id === userId);

  // активный элемент
  document.querySelectorAll('.client-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.uid) === userId);
  });

  // шапка
  const name = client ? client.user_name : `ID ${userId}`;
  document.getElementById('chat-name').textContent = name;
  document.getElementById('chat-uid').textContent = `Telegram ID: ${userId}`;
  const av = document.getElementById('chat-avatar');
  av.textContent = name.slice(0,2).toUpperCase();
  av.classList.remove('hidden');

  // включить поле ввода
  document.getElementById('msg-input').disabled = false;
  document.getElementById('send-btn').disabled = false;

  await loadMessages(userId);

  // на мобилке переключиться на панель чата
  if (typeof showChat === 'function') showChat();

  // перезапустить поллинг
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(() => loadMessages(currentUserId), 3000);
}

// ─── Сообщения ────────────────────────────────────────────────────────────────

async function loadMessages(userId) {
  const res = await fetch(`/api/messages/${userId}`);
  const msgs = await res.json();
  renderMessages(msgs);
}

function renderMessages(msgs) {
  const area = document.getElementById('messages-area');
  if (!msgs.length) {
    area.innerHTML = '<div class="text-center text-slate-400 text-sm mt-10">Сообщений пока нет</div>';
    return;
  }
  const html = msgs.map(m => {
    const time = new Date(m.timestamp).toLocaleTimeString('ru-RU', {hour:'2-digit',minute:'2-digit'});
    const dir = m.direction === 'out' ? 'out' : 'in';
    const senderLabel = dir === 'out' ? 'ООО ВИД' : (m.user_name || 'Клиент');
    return `
      <div class="bubble-wrap ${dir}">
        <div class="text-xs text-slate-400 px-1">${senderLabel}</div>
        <div class="bubble ${dir}">${escapeHtml(m.text)}</div>
        <div class="bubble-time">${time}</div>
      </div>
    `;
  }).join('');
  area.innerHTML = html;
  area.scrollTop = area.scrollHeight;
}

function escapeHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}

// ─── Отправка сообщения ───────────────────────────────────────────────────────

async function sendMessage() {
  if (!currentUserId) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;

  const btn = document.getElementById('send-btn');
  btn.disabled = true;
  input.disabled = true;

  try {
    const res = await fetch(`/api/send/${currentUserId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    if (data.ok) {
      input.value = '';
      await loadMessages(currentUserId);
    } else {
      alert('Ошибка отправки: ' + (data.error || 'неизвестна'));
    }
  } finally {
    btn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

// ─── Поиск ───────────────────────────────────────────────────────────────────

document.getElementById('search-input').addEventListener('input', function() {
  const q = this.value.toLowerCase();
  const filtered = allClients.filter(c =>
    (c.user_name || '').toLowerCase().includes(q) ||
    String(c.user_id).includes(q)
  );
  renderClients(filtered);
});

// ─── Отправка по Enter ───────────────────────────────────────────────────────

document.getElementById('msg-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
document.getElementById('send-btn').addEventListener('click', sendMessage);

// ─── SSE для новых сообщений ─────────────────────────────────────────────────

const evtSource = new EventSource('/api/events');
evtSource.onmessage = async (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'message') {
    // обновить список клиентов
    await loadClients();
    // если открыт этот клиент — обновить чат
    if (currentUserId === data.user_id) {
      await loadMessages(currentUserId);
    }
  }
};

// ─── Рассылка ─────────────────────────────────────────────────────────────────

const TEMPLATES = {
  promo: "Здравствуйте! 👋\n\nВ этом месяце ООО ВИД проводит акцию:\n✅ Скидка 15% на комплексную уборку при заказе до конца месяца.\n\nЗапишитесь прямо сейчас — просто напишите нам!",
  reminder: "Здравствуйте! 😊\n\nПрошло время с последней уборки вашего объекта.\nПора поддержать чистоту?\n\nНапишите нам — подберём удобное время и выгодные условия.\nС уважением, ООО ВИД 🏢",
  seasonal: "Здравствуйте! 🌿\n\nСезонная генеральная уборка — лучшее время обновить ваш офис или производство.\n\nООО ВИД готовы помочь: выезд, оборудование KARCHER, опытные специалисты.\n\nОставьте заявку — рассчитаем стоимость бесплатно!",
};

function openBroadcast() {
  document.getElementById('broadcast-modal').classList.remove('hidden');
  document.getElementById('broadcast-modal').classList.add('flex');
  document.getElementById('broadcast-text').value = '';
  document.getElementById('bc-result').textContent = '';
  document.getElementById('bc-send-btn').disabled = false;
  updateBroadcastCount();
}

function closeBroadcast() {
  document.getElementById('broadcast-modal').classList.add('hidden');
  document.getElementById('broadcast-modal').classList.remove('flex');
}

function setTemplate(key) {
  document.getElementById('broadcast-text').value = TEMPLATES[key] || '';
  clearBroadcastResult();
}

function clearBroadcastResult() {
  document.getElementById('bc-result').textContent = '';
}

async function updateBroadcastCount() {
  const activeOnly = document.querySelector('input[name="bc-filter"]:checked').value === 'active';
  const res = await fetch(`/api/broadcast/count?active_only=${activeOnly}`);
  const d = await res.json();
  document.getElementById('bc-count').textContent = `Будет отправлено: ${d.count} клиентам`;
}

async function sendBroadcast() {
  const text = document.getElementById('broadcast-text').value.trim();
  if (!text) {
    document.getElementById('bc-result').innerHTML = '<span class="text-red-500">Введите текст сообщения</span>';
    return;
  }
  const activeOnly = document.querySelector('input[name="bc-filter"]:checked').value === 'active';
  const btn = document.getElementById('bc-send-btn');
  btn.disabled = true;
  btn.textContent = 'Отправляю...';
  document.getElementById('bc-result').textContent = '';

  try {
    const res = await fetch('/api/broadcast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, active_only: activeOnly }),
    });
    const d = await res.json();
    if (d.ok) {
      const resultEl = document.getElementById('bc-result');
      resultEl.innerHTML = `<span class="text-green-600 font-medium">Отправлено: ${d.sent}</span>`
        + (d.failed ? `<span class="text-red-500 ml-2">Ошибок: ${d.failed}</span>` : '');
      btn.textContent = 'Готово';
      await loadClients();
    } else {
      document.getElementById('bc-result').innerHTML = `<span class="text-red-500">${d.error}</span>`;
      btn.disabled = false;
      btn.textContent = 'Отправить';
    }
  } catch (e) {
    document.getElementById('bc-result').innerHTML = '<span class="text-red-500">Ошибка сети</span>';
    btn.disabled = false;
    btn.textContent = 'Отправить';
  }
}

// ─── Инициализация ────────────────────────────────────────────────────────────

loadClients();
setInterval(loadClients, 10000);
