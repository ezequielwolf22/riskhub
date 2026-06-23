/* Motor i18n de RiskHub.
 * Depende de I18N_ES e I18N_EN definidos en i18n/es.js e i18n/en.js,
 * que deben cargarse antes que este archivo.
 */
const I18n = (() => {
  const SUPPORTED = ['es', 'en'];
  const DEFAULT   = 'es';

  function _stored() {
    const v = localStorage.getItem('riskhub_lang');
    return SUPPORTED.includes(v) ? v : DEFAULT;
  }

  const _lang = _stored();
  const _dict = _lang === 'en' ? I18N_EN : I18N_ES;
  const _fallback = I18N_ES;

  function _resolve(obj, key) {
    return key.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), obj);
  }

  function _t(key, params) {
    let val = _resolve(_dict, key);
    if (val === undefined) val = _resolve(_fallback, key);
    if (typeof val !== 'string') return key;
    if (!params) return val;
    return val.replace(/\{(\w+)\}/g, (_, k) => (params[k] !== undefined ? String(params[k]) : `{${k}}`));
  }

  /* Aplica data-i18n / data-i18n-placeholder / data-i18n-title a elementos del DOM. */
  function _applyDataAttrs(root) {
    const el = root || document;
    el.querySelectorAll('[data-i18n]').forEach(node => {
      const val = _t(node.dataset.i18n);
      if (val !== node.dataset.i18n) node.textContent = val;
    });
    el.querySelectorAll('[data-i18n-placeholder]').forEach(node => {
      const val = _t(node.dataset.i18nPlaceholder);
      if (val !== node.dataset.i18nPlaceholder) node.placeholder = val;
    });
    el.querySelectorAll('[data-i18n-title]').forEach(node => {
      const val = _t(node.dataset.i18nTitle);
      if (val !== node.dataset.i18nTitle) node.title = val;
    });
    el.querySelectorAll('[data-i18n-aria-label]').forEach(node => {
      const val = _t(node.dataset.i18nAriaLabel);
      if (val !== node.dataset.i18nAriaLabel) node.setAttribute('aria-label', val);
    });
  }

  return {
    lang()              { return _lang; },
    t(key, params)      { return _t(key, params); },
    applyDataAttrs(el)  { _applyDataAttrs(el); },

    setLang(lang) {
      if (!SUPPORTED.includes(lang)) return;
      localStorage.setItem('riskhub_lang', lang);
      window.location.reload();
    },

    isSupported(lang) { return SUPPORTED.includes(lang); },
  };
})();

/* Atajo global — disponible en todas las vistas. */
window.t = (key, params) => I18n.t(key, params);
