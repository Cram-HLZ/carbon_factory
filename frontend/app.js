/*
 * app.js —— 前端公共鉴权脚本（登录态守卫 + token 注入 + 角色权限控制）
 *
 * 用法：在需要登录保护的页面 <head> 引入 <script src="app.js"></script>
 * 功能：
 *   1. 自动给所有 /api 请求注入 Authorization: Bearer <token>
 *   2. 后端返回 401 时自动清空会话并跳转 login.html
 *   3. 页面守卫：未登录跳 login.html；users.html 仅 IT管理员可访问
 *   4. 渲染导航栏用户区（#userBar）：账号/角色 + 退出按钮 + 用户管理入口
 */
const API_BASE = 'http://localhost:8001/api';

const ROLE_NAMES = { it_admin: 'IT管理员', management: '管理层', operator: '运维岗' };

const Auth = {
  _tokenKey: 'cf_token',
  _userKey: 'cf_user',

  getToken() { return localStorage.getItem(this._tokenKey); },
  getUser() {
    try { return JSON.parse(localStorage.getItem(this._userKey) || 'null'); }
    catch (e) { return null; }
  },
  setSession(token, user) {
    localStorage.setItem(this._tokenKey, token);
    localStorage.setItem(this._userKey, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(this._tokenKey);
    localStorage.removeItem(this._userKey);
  },
  isLogin() { return !!this.getToken(); },
  hasRole() {
    const u = this.getUser();
    if (!u) return false;
    for (let i = 0; i < arguments.length; i++) if (u.role === arguments[i]) return true;
    return false;
  },
  hasPermission(perm) {
    const u = this.getUser();
    if (!u) return false;
    const ps = u.permissions || [];
    return ps.indexOf('*') !== -1 || ps.indexOf(perm) !== -1;
  },
  logout() {
    fetch(API_BASE + '/auth/logout', { method: 'POST' }).catch(() => {});
    this.clear();
    location.href = 'login.html';
  },
};

window.Auth = Auth;

// —— 给所有 /api 请求注入 token；401 自动跳登录 ——
(function () {
  const _orig = window.fetch;
  window.fetch = function (url, opts) {
    opts = opts || {};
    const isApi = typeof url === 'string' && url.indexOf(API_BASE) === 0;
    if (isApi) {
      const token = Auth.getToken();
      if (token) {
        const headers = new Headers(opts.headers || {});
        if (!headers.has('Authorization')) headers.set('Authorization', 'Bearer ' + token);
        opts.headers = headers;
      }
    }
    return _orig.call(this, url, opts).then(function (resp) {
      if (isApi && resp.status === 401) {
        // 登录页上的 401（如密码错误）交由页面自身提示，不强制刷新跳转
        const pg = ((location.pathname || '').split('/').pop() || '').toLowerCase();
        if (pg !== 'login.html' && pg !== '') {
          Auth.clear();
          location.href = 'login.html';
        }
      }
      return resp;
    });
  };
})();

// —— 页面守卫 ——
(function () {
  const page = ((location.pathname || '').split('/').pop() || '').toLowerCase();
  if (page === 'login.html' || page === '') return;              // 登录页本身不守卫
  if (!Auth.isLogin()) { location.replace('login.html'); return; }  // 未登录 → 登录页
  if (page === 'users.html' && !Auth.hasRole('it_admin')) {         // 用户管理仅 IT管理员
    location.replace('overview.html');
  }
})();

// —— 渲染导航用户区 ——
document.addEventListener('DOMContentLoaded', function () {
  const bar = document.getElementById('userBar');
  if (!bar) return;
  const u = Auth.getUser();
  if (!u) return;
  let html = '<span class="small">' + u.account + '（' + (ROLE_NAMES[u.role] || u.role) + '）</span>';
  if (u.role === 'it_admin') {
    html += '<a class="btn btn-sm btn-outline-light py-0" href="users.html">用户管理</a>';
  }
  html += '<button class="btn btn-sm btn-outline-light py-0" onclick="Auth.logout()">退出</button>';
  bar.innerHTML = html;
});