let allOrders = [];
let allWorkers = [];
let currentOrderId = null;
let dragCard = null;

const COLUMNS = ['new', 'in_progress', 'done', 'cancelled'];

// ─── Загрузка заявок ─────────────────────────────────────────────────────────

async function loadOrders() {
  const res = await fetch('/api/orders');
  allOrders = await res.json();
  renderBoard();
}

async function loadWorkers() {
  const res = await fetch('/api/workers');
  allWorkers = await res.json();
}

// ─── Рендер доски ────────────────────────────────────────────────────────────

function renderBoard() {
  COLUMNS.forEach(status => {
    const container = document.getElementById(`cards-${status}`);
    const col = document.getElementById(`col-${status}`);
    const badge = col.querySelector('.count-badge');
    const orders = allOrders.filter(o => o.status === status);
    badge.textContent = orders.length;

    if (!orders.length) {
      container.innerHTML = '<div class="text-xs text-slate-400 text-center py-4 px-2">Нет заявок</div>';
    } else {
      container.innerHTML = orders.map(o => renderCard(o)).join('');
      // навесить события
      container.querySelectorAll('.kanban-card').forEach(card => {
        card.addEventListener('dragstart', onDragStart);
        card.addEventListener('dragend', onDragEnd);
        card.addEventListener('click', () => openModal(parseInt(card.dataset.id)));
      });
    }

    // drop-zone
    container.addEventListener('dragover', onDragOver);
    container.addEventListener('dragleave', onDragLeave);
    container.addEventListener('drop', e => onDrop(e, status));
  });
}

function renderCard(o) {
  const stars = o.rating ? '★'.repeat(o.rating) : '';
  const date = o.date || '—';
  const created = o.created_at ? new Date(o.created_at).toLocaleDateString('ru-RU') : '';
  const service = (o.service || '').length > 35 ? (o.service || '').slice(0,35)+'…' : (o.service || '—');
  const executorBadge = o.executor
    ? `<div class="text-xs text-indigo-600 mt-1.5">👤 ${o.executor}</div>` : '';
  return `
    <div class="kanban-card" draggable="true" data-id="${o.id}">
      <div class="flex items-start justify-between">
        <div class="card-name">${o.name || '—'}</div>
        <div class="text-xs text-slate-400">#${o.id}</div>
      </div>
      <div class="card-service">${service}</div>
      <div class="card-meta">
        ${o.phone ? `<span>📞 ${o.phone}</span>` : ''}
        ${date !== '—' ? `<span>📅 ${date}</span>` : ''}
        ${created ? `<span class="text-slate-300">${created}</span>` : ''}
      </div>
      ${executorBadge}
      ${stars ? `<div class="card-rating mt-2">${stars}</div>` : ''}
    </div>
  `;
}

// ─── Drag & Drop ──────────────────────────────────────────────────────────────

function onDragStart(e) {
  dragCard = e.currentTarget;
  dragCard.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', dragCard.dataset.id);
}

function onDragEnd() {
  if (dragCard) dragCard.classList.remove('dragging');
  document.querySelectorAll('.kanban-cards').forEach(c => c.classList.remove('drop-target'));
  dragCard = null;
}

function onDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('drop-target');
}

function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    e.currentTarget.classList.remove('drop-target');
  }
}

async function onDrop(e, newStatus) {
  e.preventDefault();
  e.currentTarget.classList.remove('drop-target');
  const id = parseInt(e.dataTransfer.getData('text/plain'));
  if (!id) return;
  await updateStatus(id, newStatus);
}

// ─── Обновление статуса ───────────────────────────────────────────────────────

async function updateStatus(orderId, newStatus) {
  const res = await fetch(`/api/orders/${orderId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: newStatus })
  });
  const data = await res.json();
  if (data.ok) {
    const order = allOrders.find(o => o.id === orderId);
    if (order) order.status = newStatus;
    renderBoard();
    if (currentOrderId === orderId) {
      updateModalButtons(newStatus);
    }
  }
}

// ─── Модальное окно ───────────────────────────────────────────────────────────

function openModal(orderId) {
  const o = allOrders.find(x => x.id === orderId);
  if (!o) return;
  currentOrderId = orderId;

  document.getElementById('modal-name').textContent = o.name || '—';
  document.getElementById('modal-service').textContent = o.service || '—';
  document.getElementById('modal-phone').textContent = o.phone || '—';
  document.getElementById('modal-address').textContent = o.address || '—';
  document.getElementById('modal-date').textContent = o.date || '—';
  document.getElementById('modal-created').textContent = o.created_at
    ? new Date(o.created_at).toLocaleString('ru-RU') : '—';
  document.getElementById('modal-rating').textContent = o.rating
    ? '★'.repeat(o.rating) + ` (${o.rating}/5)` : '—';

  // Заполнить список исполнителей
  const sel = document.getElementById('modal-executor-select');
  sel.innerHTML = '<option value="">— Не назначен —</option>'
    + allWorkers.map(w => `<option value="${w.id}" ${o.executor === w.name ? 'selected' : ''}>${w.name}</option>`).join('');
  document.getElementById('modal-assign-result').textContent = '';

  updateModalButtons(o.status);
  document.getElementById('card-modal').classList.remove('hidden');
}

function updateModalButtons(currentStatus) {
  document.querySelectorAll('.status-btn').forEach(btn => {
    btn.classList.toggle('ring-2', btn.dataset.status === currentStatus);
    btn.classList.toggle('ring-indigo-500', btn.dataset.status === currentStatus);
  });
}

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('card-modal').classList.add('hidden');
  currentOrderId = null;
});

document.getElementById('card-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('card-modal')) {
    document.getElementById('card-modal').classList.add('hidden');
    currentOrderId = null;
  }
});

document.querySelectorAll('.status-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!currentOrderId) return;
    await updateStatus(currentOrderId, btn.dataset.status);
  });
});

// ─── Исполнитель ──────────────────────────────────────────────────────────────

async function assignExecutor() {
  if (!currentOrderId) return;
  const sel = document.getElementById('modal-executor-select');
  const workerId = sel.value ? parseInt(sel.value) : null;
  const btn = document.getElementById('modal-assign-btn');
  btn.disabled = true;

  const res = await fetch(`/api/orders/${currentOrderId}/executor`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ worker_id: workerId }),
  });
  const d = await res.json();
  const resultEl = document.getElementById('modal-assign-result');
  if (d.ok) {
    const order = allOrders.find(o => o.id === currentOrderId);
    if (order) order.executor = d.executor;
    renderBoard();
    resultEl.innerHTML = d.executor
      ? `<span class="text-green-600">Назначен: ${d.executor}</span>`
      : '<span class="text-slate-500">Исполнитель снят</span>';
  } else {
    resultEl.innerHTML = `<span class="text-red-500">${d.error}</span>`;
  }
  btn.disabled = false;
}

// ─── Сотрудники ───────────────────────────────────────────────────────────────

function openWorkersModal() {
  renderWorkersList();
  const m = document.getElementById('workers-modal');
  m.classList.remove('hidden');
  m.classList.add('flex');
}

function closeWorkersModal() {
  const m = document.getElementById('workers-modal');
  m.classList.add('hidden');
  m.classList.remove('flex');
}

function renderWorkersList() {
  const el = document.getElementById('workers-list');
  if (!allWorkers.length) {
    el.innerHTML = '<div class="text-sm text-slate-400 text-center py-2">Сотрудников пока нет</div>';
    return;
  }
  el.innerHTML = allWorkers.map(w => `
    <div class="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2">
      <div>
        <div class="text-sm font-medium text-slate-800">${w.name}</div>
        ${w.telegram_id ? `<div class="text-xs text-slate-400">TG: ${w.telegram_id}</div>` : ''}
      </div>
      <button onclick="deleteWorker(${w.id})" class="text-slate-300 hover:text-red-500 transition ml-2">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>
  `).join('');
}

async function addWorker() {
  const name = document.getElementById('worker-name').value.trim();
  const tgRaw = document.getElementById('worker-tg').value.trim();
  if (!name) return;
  const telegram_id = tgRaw ? parseInt(tgRaw) : null;

  const res = await fetch('/api/workers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, telegram_id }),
  });
  const d = await res.json();
  if (d.ok) {
    document.getElementById('worker-name').value = '';
    document.getElementById('worker-tg').value = '';
    await loadWorkers();
    renderWorkersList();
  }
}

async function deleteWorker(id) {
  await fetch(`/api/workers/${id}`, { method: 'DELETE' });
  await loadWorkers();
  renderWorkersList();
}

// ─── Инициализация ────────────────────────────────────────────────────────────

loadWorkers();
loadOrders();
setInterval(loadOrders, 15000);
