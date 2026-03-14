const STATUS_LABELS = {
  new: 'Новая', in_progress: 'В работе', done: 'Выполнена', cancelled: 'Отменена'
};

async function loadStats() {
  const res = await fetch('/api/stats');
  const d = await res.json();

  document.getElementById('s-today').textContent = d.today_count;
  document.getElementById('s-week').textContent = d.week_count;
  document.getElementById('s-clients').textContent = d.clients_count;
  document.getElementById('s-rating').textContent = d.avg_rating ? `${d.avg_rating} ★` : '—';

  function fmtRub(v) {
    if (!v) return '0 ₽';
    if (v >= 1000000) return (v / 1000000).toFixed(1) + ' млн ₽';
    if (v >= 1000) return (v / 1000).toFixed(0) + ' тыс ₽';
    return v + ' ₽';
  }
  document.getElementById('s-today-rev').textContent = fmtRub(d.today_revenue);
  document.getElementById('s-month-rev').textContent = fmtRub(d.month_revenue);

  const statuses = ['new', 'in_progress', 'done', 'cancelled'];
  statuses.forEach(s => {
    const el = document.getElementById(`st-${s}`);
    if (el) el.textContent = d.statuses[s] || 0;
  });

  // График по дням
  const revMap = {};
  (d.revenue_data || []).forEach(r => { revMap[r.day] = r.revenue; });
  const daysCtx = document.getElementById('chart-days').getContext('2d');
  new Chart(daysCtx, {
    type: 'line',
    data: {
      labels: d.days_data.map(x => {
        const dt = new Date(x.day);
        return dt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
      }),
      datasets: [
        {
          label: 'Заявки',
          data: d.days_data.map(x => x.count),
          borderColor: '#4f46e5',
          backgroundColor: 'rgba(79,70,229,0.08)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointBackgroundColor: '#4f46e5',
          pointRadius: 4,
          yAxisID: 'y',
        },
        {
          label: 'Выручка (₽)',
          data: d.days_data.map(x => revMap[x.day] || 0),
          borderColor: '#10b981',
          backgroundColor: 'transparent',
          borderWidth: 2,
          fill: false,
          tension: 0.4,
          pointBackgroundColor: '#10b981',
          pointRadius: 4,
          yAxisID: 'y1',
        }
      ]
    },
    options: {
      plugins: { legend: { display: true, labels: { font: { size: 11 } } } },
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: '#f1f5f9' }, position: 'left' },
        y1: {
          beginAtZero: true,
          grid: { display: false },
          position: 'right',
          ticks: { callback: v => v >= 1000 ? (v/1000).toFixed(0)+'k' : v }
        },
        x: { grid: { display: false } }
      }
    }
  });

  // Диаграмма услуг
  const svcCtx = document.getElementById('chart-services').getContext('2d');
  const colors = ['#4f46e5','#06b6d4','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#64748b'];
  new Chart(svcCtx, {
    type: 'doughnut',
    data: {
      labels: d.services_data.map(x => x.service.length > 22 ? x.service.slice(0,22)+'…' : x.service),
      datasets: [{
        data: d.services_data.map(x => x.count),
        backgroundColor: colors,
        borderWidth: 0,
      }]
    },
    options: {
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 10 } }
      },
      cutout: '60%',
    }
  });

  // Средний чек
  const avgCheckEl = document.getElementById('s-avg-check');
  if (avgCheckEl) avgCheckEl.textContent = d.avg_check ? fmtRub(d.avg_check) : '—';

  // Воронка конверсии
  const f = d.funnel || {};
  const funnelSteps = [
    { label: 'Лидов (написали боту)', value: f.leads || 0, color: 'bg-indigo-500', pct: 100 },
    { label: `Заявок оформлено (${f.conv_order || 0}%)`, value: f.orders || 0, color: 'bg-blue-500', pct: f.conv_order || 0 },
    { label: `Выполнено (${f.conv_done || 0}% от заявок)`, value: f.done || 0, color: 'bg-emerald-500', pct: f.orders ? Math.round(f.done / f.leads * 100) : 0 },
    { label: 'Отменено', value: f.cancelled || 0, color: 'bg-red-400', pct: f.leads ? Math.round((f.cancelled || 0) / f.leads * 100) : 0 },
  ];
  const funnelContainer = document.getElementById('funnel-container');
  if (funnelContainer) {
    funnelContainer.innerHTML = funnelSteps.map(step => `
      <div>
        <div class="flex justify-between text-xs text-slate-600 mb-1">
          <span>${step.label}</span>
          <span class="font-semibold">${step.value}</span>
        </div>
        <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div class="${step.color} h-2 rounded-full transition-all" style="width:${Math.min(step.pct, 100)}%"></div>
        </div>
      </div>
    `).join('');
  }

  // Топ клиентов по LTV
  const ltvList = document.getElementById('ltv-list');
  if (ltvList) {
    if (!d.top_clients || !d.top_clients.length) {
      ltvList.innerHTML = '<div class="text-sm text-slate-400 text-center py-4">Нет данных</div>';
    } else {
      const maxLtv = d.top_clients[0].ltv || 1;
      ltvList.innerHTML = d.top_clients.map((c, i) => `
        <div class="flex items-center gap-3">
          <div class="text-xs text-slate-400 w-4 shrink-0">${i + 1}</div>
          <div class="flex-1 min-w-0">
            <div class="flex justify-between text-xs mb-0.5">
              <span class="font-medium text-slate-700 truncate">${c.name || '—'}</span>
              <span class="text-emerald-600 font-semibold shrink-0 ml-2">${fmtRub(c.ltv)}</span>
            </div>
            <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div class="bg-emerald-400 h-1.5 rounded-full" style="width:${Math.round(c.ltv / maxLtv * 100)}%"></div>
            </div>
            <div class="text-xs text-slate-400 mt-0.5">${c.orders} заказ · ср. чек ${fmtRub(c.avg_check)}</div>
          </div>
        </div>
      `).join('');
    }
  }

}

// ─── Таблица заявок с пагинацией ─────────────────────────────────────────────

let currentPage = 1;

async function loadRecent(page) {
  currentPage = page;
  const res = await fetch(`/api/recent?page=${page}`);
  const d = await res.json();
  const tbody = document.getElementById('recent-tbody');
  const totalPages = Math.ceil(d.total / d.per_page);

  document.getElementById('recent-info').textContent =
    `${d.total} заявок · стр. ${d.page} из ${totalPages || 1}`;

  if (!d.orders.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-slate-400">Заявок пока нет</td></tr>';
  } else {
    tbody.innerHTML = d.orders.map(r => `
      <tr>
        <td class="text-slate-400">#${r.id}</td>
        <td>
          <div class="font-medium">${r.name || '—'}</div>
          <div class="text-xs text-slate-400">${r.phone || ''}</div>
        </td>
        <td class="text-slate-600">${r.service || '—'}</td>
        <td class="text-slate-500 text-xs">${r.address || '—'}</td>
        <td class="text-slate-500 text-xs">${r.date || '—'}</td>
        <td><span class="badge badge-${r.status}">${STATUS_LABELS[r.status] || r.status}</span></td>
        <td class="text-amber-500">${r.rating ? '★'.repeat(r.rating) : '—'}</td>
      </tr>
    `).join('');
  }

  document.getElementById('page-prev').disabled = page <= 1;
  document.getElementById('page-next').disabled = page >= totalPages;

  const nums = document.getElementById('page-numbers');
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, start + 4);
  nums.innerHTML = Array.from({ length: end - start + 1 }, (_, i) => start + i).map(p => `
    <button onclick="loadRecent(${p})"
      class="w-8 h-8 text-xs rounded-lg ${p === page ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}">
      ${p}
    </button>
  `).join('');
}

function changePage(delta) {
  loadRecent(currentPage + delta);
}

loadStats();
loadRecent(1);
setInterval(loadStats, 30000);
