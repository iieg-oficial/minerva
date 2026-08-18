import {
  createDocument,
  getAdministration,
  getConfig,
  getDocuments,
  getSession,
} from '/assets/api.js';
import {
  renderAccount,
  renderAdministration,
  renderChrome,
  renderConfig,
  renderDocuments,
  renderError,
  renderHome,
  showDocumentCreated,
  showGlobalError,
} from '/assets/views.js';

let config = { ok: false, values: {} };
let session = { authenticated: false };

function detail(body, fallback) {
  return typeof body.detail === 'string' ? body.detail : fallback;
}

function renderHttpError(response, body, permission = '') {
  if (response.status === 401) {
    renderError({
      status: 401,
      title: 'Necesitas iniciar sesión',
      detail: detail(body, 'La sesión no existe o ya venció.'),
      login: true,
    });
    return;
  }
  if (response.status === 403) {
    renderError({
      status: 403,
      title: 'No tienes permiso para esta sección',
      detail: detail(body, 'Tu cuenta sí tiene acceso al sistema, pero no a esta operación.'),
      permission,
    });
    return;
  }
  renderError({
    status: response.status,
    title: 'No fue posible cargar esta sección',
    detail: detail(body, 'El sistema devolvió una respuesta inesperada.'),
  });
}

async function openDocuments() {
  const { response, body } = await getDocuments();
  if (!response.ok) return renderHttpError(response, body, 'portal_demo.documents.view');
  renderDocuments(body);
}

async function openAdministration() {
  const { response, body } = await getAdministration();
  if (!response.ok) return renderHttpError(response, body, 'portal_demo.system.manage');
  renderAdministration(body);
}

function openAccount() {
  if (!session.authenticated) {
    renderError({
      status: 401,
      title: 'Necesitas iniciar sesión',
      detail: 'La cuenta y sus permisos solo existen después del login con Minerva.',
      login: true,
    });
    return;
  }
  renderAccount(session);
}

const routes = {
  '/inicio': () => renderHome(session),
  '/documentos': openDocuments,
  '/administracion': openAdministration,
  '/cuenta': openAccount,
  '/configuracion': () => renderConfig(config),
  '/demo/401': () => renderError({
    status: 401,
    title: 'Necesitas iniciar sesión',
    detail: 'Ejemplo de la vista mostrada cuando una ruta protegida no recibe una sesión.',
    preview: true,
    login: true,
  }),
  '/demo/403': () => renderError({
    status: 403,
    title: 'No tienes permiso para esta operación',
    detail: 'La cuenta entró al sistema, pero el permiso requerido no forma parte de sus asignaciones.',
    permission: 'portal_demo.documents.create',
    preview: true,
  }),
  '/demo/sin-acceso': () => renderError({
    status: 403,
    title: 'Tu cuenta no tiene acceso a Portal Demo',
    detail: 'Minerva autenticó al usuario, pero no encontró una asignación activa para esta aplicación.',
    preview: true,
  }),
};

async function route() {
  showGlobalError('');
  const path = location.hash.slice(1) || '/inicio';
  await (routes[path] || routes['/inicio'])();
}

document.getElementById('create-document').addEventListener('click', async () => {
  try {
    const { response, body } = await createDocument();
    if (!response.ok) return renderHttpError(response, body, 'portal_demo.documents.create');
    showDocumentCreated(body);
  } catch (error) {
    showGlobalError(error.message);
  }
});

window.addEventListener('hashchange', () => route().catch((error) => showGlobalError(error.message)));

async function start() {
  const [configResult, sessionResult] = await Promise.all([getConfig(), getSession()]);
  config = configResult.body;
  session = sessionResult.body;
  renderChrome(config, session);

  const oauthError = new URLSearchParams(location.search).get('error');
  if (oauthError) {
    renderError({
      status: 403,
      title: oauthError.includes('No tienes acceso')
        ? 'Tu cuenta no tiene acceso a Portal Demo'
        : 'No fue posible iniciar sesión',
      detail: oauthError,
      login: true,
    });
    return;
  }
  await route();
}

start().catch((error) => showGlobalError(error.message));
