(() => {
  const root = document.documentElement;
  try { root.dataset.theme = localStorage.getItem('gadget-theme') || 'light'; } catch (_) {}
  document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('gadget-theme', root.dataset.theme); } catch (_) {}
  }));
  document.querySelector('[data-menu]')?.addEventListener('click', () => document.querySelector('.sidebar').classList.toggle('open'));
  document.querySelectorAll('.nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (location.pathname === href || (href !== '/panel/' && location.pathname.startsWith(href))) link.classList.add('active');
  });
  const choices = document.getElementById('id_sources');
  const orderField = document.getElementById('id_ordered_sources');
  if (choices && orderField) {
    const initial = orderField.value.split(',');
    const rows = [...choices.children];
    rows.sort((a,b) => {
      const ai = initial.indexOf(a.querySelector('input').value), bi = initial.indexOf(b.querySelector('input').value);
      return (ai < 0 ? 99999 : ai) - (bi < 0 ? 99999 : bi);
    }).forEach(row => choices.appendChild(row));
    function saveOrder() { orderField.value = [...choices.querySelectorAll('input:checked')].map(input => input.value).join(','); }
    choices.addEventListener('change', saveOrder);
    for (const row of rows) {
      for (const [text, direction] of [['↑', -1], ['↓', 1]]) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = text; button.className = 'order-button';
        button.setAttribute('aria-label', direction < 0 ? 'نمایش زودتر' : 'نمایش دیرتر');
        button.addEventListener('click', () => {
          if (direction < 0 && row.previousElementSibling) choices.insertBefore(row, row.previousElementSibling);
          if (direction > 0 && row.nextElementSibling) choices.insertBefore(row.nextElementSibling, row);
          saveOrder();
        });
        row.appendChild(button);
      }
    }
    saveOrder();
  }
  const live = document.querySelector('[data-live-url]');
  const number = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 8 });
  function formatted(value) { return /^-?\d+(\.\d+)?$/.test(value) ? number.format(Number(value)) : value; }
  function stamp(element, value) {
    element.textContent = value ? new Date(value).toLocaleString('fa-IR') : '—';
  }
  document.querySelectorAll('[data-source-time]').forEach(el => stamp(el, el.textContent === '—' ? '' : el.textContent));
  function expire() {
    document.querySelectorAll('[data-expires]').forEach(el => {
      if (el.dataset.expires && Date.parse(el.dataset.expires) <= Date.now()) {
        el.textContent = 'در انتظار به‌روزرسانی';
        el.classList.add('muted');
        const badge = el.closest('.market-card, tr')?.querySelector('.badge');
        if (badge) { badge.textContent = 'منقضی'; badge.className = 'badge warning'; }
      }
    });
  }
  setInterval(expire, 1000);
  expire();
  if (!live || live.dataset.liveEnabled === 'false') return;
  let interval = 30000;
  async function poll() {
    let enabled = true;
    try {
      const response = await fetch(live.dataset.liveUrl, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw Error('Unavailable');
      const data = await response.json();
      enabled = data.live_updates;
      interval = Math.max(5000, data.poll_after_seconds * 1000);
      for (const source of data.sources) {
        const value = document.querySelector(`[data-source-value="${source.id}"]`);
        if (value) {
          value.textContent = source.data ? formatted(source.data.value) : 'در انتظار به‌روزرسانی';
          value.dataset.expires = source.data?.expires_at || '';
          value.classList.toggle('muted', !source.data);
        }
        const status = document.querySelector(`[data-source-status="${source.id}"]`);
        if (status) { status.textContent = source.data ? 'به‌روز' : 'در انتظار'; status.className = 'badge ' + (source.data ? 'success' : 'warning'); }
        const time = document.querySelector(`[data-source-time="${source.id}"]`);
        if (time) stamp(time, source.data?.observed_at);
      }
      for (const list of data.price_lists) {
        for (const item of list.items) {
          document.querySelectorAll('[data-price-code]').forEach(cell => {
            if (cell.dataset.listId !== String(list.id) || cell.dataset.priceCode !== item.code) return;
            cell.textContent = item.amount === null ? '—' : formatted(item.amount);
            cell.dataset.expires = item.valid_until;
            cell.classList.toggle('muted', item.amount === null);
            const badge = cell.closest('tr').querySelector('.badge');
            if (badge) { badge.textContent = item.status === 'fresh' ? 'معتبر' : 'منقضی'; badge.className = 'badge ' + (item.status === 'fresh' ? 'success' : 'warning'); }
          });
        }
      }
    } catch (_) {
      // Values always expire locally even when the server cannot be reached.
    } finally {
      expire();
      if (enabled) setTimeout(poll, interval);
    }
  }
  setTimeout(poll, interval);
})();
