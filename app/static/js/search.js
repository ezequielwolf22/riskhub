/* Busqueda global con dropdown en el header. */
const Search = (() => {
  const TYPE_CONFIG = {
    asset:         { icon: '🗄️', bg: '#EDD1FF', label: 'Activos' },
    risk:          { icon: '📊', bg: '#FFE6CE', label: 'Riesgos' },
    threat:        { icon: '⚠️', bg: '#FEE2E2', label: 'Amenazas' },
    vulnerability: { icon: '🔍', bg: '#FEF9C3', label: 'Vulnerabilidades' },
    control:       { icon: '🛡️', bg: '#D1FAE5', label: 'Controles' },
  };

  let _debounce = null;
  let _active = false;

  function _el(id) { return document.getElementById(id); }

  function _itemHtml(item) {
    const cfg = TYPE_CONFIG[item.type] || { icon: '•', bg: 'var(--bg-3)', label: '' };
    const subParts = [item.subtitle, item.meta].filter(Boolean);
    return `
      <a class="search-item" href="${UI.esc(item.url)}"
         onclick="Search.close();" tabindex="0">
        <div class="search-item-icon" style="background:${cfg.bg};">${cfg.icon}</div>
        <div class="search-item-body">
          <div class="search-item-title">${UI.esc(item.title)}</div>
          ${subParts.length ? `<div class="search-item-sub">${UI.esc(subParts.join(' · '))}</div>` : ''}
        </div>
        ${item.meta ? `<span class="search-meta">${UI.esc(item.meta)}</span>` : ''}
      </a>`;
  }

  function _render(data) {
    const dd = _el('search-dropdown');
    if (!dd) return;

    const sections = ['assets', 'risks', 'threats', 'vulnerabilities', 'controls'];
    let html = '';
    let total = 0;

    for (const key of sections) {
      const items = data.results[key] || [];
      if (!items.length) continue;
      const cfg = TYPE_CONFIG[items[0].type];
      html += `<div class="search-group-label">${cfg ? cfg.label : key}</div>`;
      html += items.map(_itemHtml).join('');
      total += items.length;
    }

    if (!total) {
      html = `<div class="search-empty">Sin resultados para <strong>"${UI.esc(data.query)}"</strong></div>`;
    }

    dd.innerHTML = html;
    dd.style.display = 'block';
    _active = true;
  }

  async function _search(q) {
    if (!q || q.length < 2) { close(); return; }
    const dd = _el('search-dropdown');
    if (dd) {
      dd.innerHTML = '<div class="search-empty">Buscando...</div>';
      dd.style.display = 'block';
    }
    try {
      const data = await Api.search(q);
      _render(data);
    } catch (_) {
      if (dd) dd.style.display = 'none';
    }
  }

  function close() {
    const dd = _el('search-dropdown');
    if (dd) dd.style.display = 'none';
    _active = false;
  }

  function init() {
    const input = _el('search-input');
    const wrapper = _el('search-wrapper');
    if (!input) return;

    input.addEventListener('input', () => {
      clearTimeout(_debounce);
      const q = input.value.trim();
      if (!q) { close(); return; }
      _debounce = setTimeout(() => _search(q), 280);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { close(); input.blur(); }
      // Arrow-key navigation between items
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const first = _el('search-dropdown')?.querySelector('.search-item');
        if (first) first.focus();
      }
    });

    // Navigate items with arrow keys
    document.addEventListener('keydown', (e) => {
      if (!_active) return;
      const dd = _el('search-dropdown');
      if (!dd || dd.style.display === 'none') return;
      const items = [...dd.querySelectorAll('.search-item')];
      const idx = items.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        items[Math.min(idx + 1, items.length - 1)]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (idx <= 0) input.focus();
        else items[idx - 1]?.focus();
      } else if (e.key === 'Escape') {
        close(); input.focus();
      }
    });

    // Close when clicking outside
    document.addEventListener('mousedown', (e) => {
      if (!wrapper || !wrapper.contains(e.target)) close();
    });

    // Keyboard shortcut: / to focus search (like GitHub)
    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement.tagName !== 'INPUT'
          && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        input.focus();
        input.select();
      }
    });
  }

  return { init, close };
})();
