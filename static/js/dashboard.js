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

  // Таблица
  const tbody = document.getElementById('recent-tbody');
  if (!d.recent.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-slate-400">Заявок пока нет</td></tr>';
    return;
  }
  tbody.innerHTML = d.recent.map(r => `
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

loadStats();
setInterval(loadStats, 30000);
