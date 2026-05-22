/* Gestión de sesión (token + usuario actual). */
const Auth = {
  user() {
    try { return JSON.parse(localStorage.getItem('riskhub_user') || 'null'); }
    catch { return null; }
  },
  token() { return localStorage.getItem('riskhub_token'); },
  isAuthenticated() { return !!Auth.token(); },
  isAdmin() { const u = Auth.user(); return u && u.role === 'admin'; },
  canEdit() { const u = Auth.user(); return u && (u.role === 'admin' || u.role === 'analyst'); },
  logout() {
    localStorage.removeItem('riskhub_token');
    localStorage.removeItem('riskhub_user');
    window.location.href = '/login';
  },
  requireAuth() {
    if (!Auth.isAuthenticated()) {
      window.location.href = '/login';
      return false;
    }
    return true;
  },
};
