let allOrders = [];
let currentOrderId = null;
let dragCard = null;

const COLUMNS = ['new', 'in_progress', 'done', 'cancelled'];

// ─── Загрузка заявок ─────────────────────────────────────────────────────────

async function loadOrders() {
  const res = await fetch('/api/orders');
  allOrders = await res.json();
  renderBoard();
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

// ─── Инициализация ────────────────────────────────────────────────────────────

loadOrders();
setInterval(loadOrders, 15000);
