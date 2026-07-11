/* Gestión de sesión (token + usuario actual). */
const Auth = {
  user() {
    try { return JSON.parse(localStorage.getItem('riskhub_user') || 'null'); }
    catch { return null; }
  },
  token() { return localStorage.getItem('riskhub_token'); },
  isAuthenticated() { return !!Auth.token(); },
  isAdmin() { const u = Auth.user(); return u && (u.role === 'admin' || u.role === 'superadmin'); },
  isSuperAdmin() { const u = Auth.user(); return u && u.role === 'superadmin'; },
  canEdit() { const u = Auth.user(); return u && (u.role === 'admin' || u.role === 'analyst' || u.role === 'superadmin'); },
  logout() {
    const token = Auth.token();
    if (token) {
      // Revocar el token en el servidor (logout real); keepalive para que
      // la peticion sobreviva a la navegacion inmediata a /login.
      try {
        fetch('/api/auth/logout', {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + token },
          keepalive: true,
        }).catch(() => {});
      } catch (e) { /* sin red: se limpia localmente igual */ }
    }
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
