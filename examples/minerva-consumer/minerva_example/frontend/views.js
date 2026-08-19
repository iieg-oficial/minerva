const byId = (id) => document.getElementById(id);
const views = ['loading', 'inicio', 'documentos', 'administracion', 'cuenta', 'configuracion', 'error'];

function fillList(id, values, emptyMessage) {
  const list = byId(id);
  list.replaceChildren();
  for (const value of values.length ? values : [emptyMessage]) {
    const item = document.createElement('li');
    item.textContent = value;
    list.append(item);
  }
}

export function showView(name) {
  for (const view of views) byId(`view-${view}`).hidden = view !== name;
  document.querySelectorAll('[data-route]').forEach((link) => {
    link.toggleAttribute('aria-current', link.dataset.route === name);
  });
  window.scrollTo({ top: 0, behavior: 'instant' });
}

export function renderChrome(config, session) {
  byId('configuration-warning').hidden = config.ok;
  document.querySelectorAll('[data-login]').forEach((link) => {
    link.dataset.loginLabel ||= link.textContent;
    link.href = config.ok ? '/login' : '#/configuracion';
    link.textContent = config.ok ? link.dataset.loginLabel : 'Completar integración';
    link.title = config.ok ? '' : 'Primero completa las credenciales de integración';
  });
  document.querySelectorAll('[data-logout]').forEach((form) => {
    form.hidden = !session.authenticated;
  });
  document.querySelector('.app-header > .session-actions [data-login]').hidden = session.authenticated;
}

export function renderHome(session) {
  byId('home-public').hidden = session.authenticated;
  byId('home-authenticated').hidden = !session.authenticated;
  byId('home-user').textContent = session.user?.name || session.user?.email || 'usuario';
  showView('inicio');
}

export function renderDocuments(data) {
  const body = byId('documents-body');
  body.replaceChildren();
  for (const documentData of data.items) {
    const row = body.insertRow();
    for (const value of [documentData.folio, documentData.subject, documentData.status, documentData.updated_at]) {
      row.insertCell().textContent = value;
    }
  }
  byId('documents-message').textContent = data.message;
  showView('documentos');
}

export function showDocumentCreated(documentData) {
  byId('documents-message').textContent = `${documentData.message}: ${documentData.item.folio}`;
}

export function renderAdministration(data) {
  const stats = byId('admin-stats');
  stats.replaceChildren();
  for (const [label, value] of Object.entries(data.stats)) {
    const card = document.createElement('article');
    const number = document.createElement('strong');
    const caption = document.createElement('span');
    number.textContent = value;
    caption.textContent = label;
    card.append(number, caption);
    stats.append(card);
  }
  showView('administracion');
}

export function renderAccount(session) {
  byId('account-name').textContent = session.user.name || 'Sin nombre en el token';
  byId('account-email').textContent = session.user.email || 'Sin correo en el token';
  byId('account-sub').textContent = session.user.sub;
  fillList('account-roles', session.user.roles, 'Sin roles informativos');
  fillList('account-permissions', session.permissions, 'Sin permisos asignados');
  showView('cuenta');
}

export function renderConfig(config) {
  byId('config-message').textContent = config.message;
  byId('config-message').className = config.ok ? 'ok' : 'bad';
  const rows = byId('config-values');
  rows.replaceChildren();
  for (const [name, value] of Object.entries(config.values)) {
    const row = rows.insertRow();
    const label = document.createElement('strong');
    const code = document.createElement('code');
    label.textContent = name;
    code.textContent = value;
    row.insertCell().append(label);
    row.insertCell().append(code);
  }
  byId('config-login-action').hidden = !config.ok;
  showView('configuracion');
}

export function renderError({ status, title, detail, permission = '', preview = false, login = false }) {
  byId('error-code').textContent = status ? `HTTP ${status}` : '';
  byId('error-preview').hidden = !preview;
  byId('error-title').textContent = title;
  byId('error-detail').textContent = detail;
  byId('error-permission').textContent = permission ? `Permiso requerido: ${permission}` : '';
  byId('error-permission').hidden = !permission;
  byId('error-login').hidden = !login;
  showView('error');
}

export function showGlobalError(message) {
  const error = byId('global-error');
  error.textContent = message;
  error.hidden = !message;
}
