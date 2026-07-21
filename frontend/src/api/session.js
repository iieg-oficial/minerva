// Sesión del panel (patrón BFF). La fuente de verdad de las cuentas iniciadas en
// este navegador ya NO es localStorage: vive en el backend (contenedor en Redis),
// y el navegador solo conserva una cookie opaca HttpOnly (ilegible desde JS).
//
// Este módulo es un cliente + caché en memoria de ese estado:
//  - `fetchSession()` sincroniza el caché con `GET /auth/session`.
//  - los getters (`getSessions`/`getActive`/`isExpired`) leen el caché (síncronos).
//  - los mutadores (`setActive`/`removeSession`/`deactivate`/`logoutAll`) llaman al
//    backend y refrescan el caché.
// El token CSRF (synchronizer) también se guarda aquí en memoria y lo adjunta
// `client.js` en las mutaciones. Nada de esto se persiste en el navegador.

import client from './client';

let _csrf = '';
let _state = { accounts: [], active: null };

export function getCsrf() {
    return _csrf;
}

export function setCsrf(token) {
    _csrf = token || '';
}

export function getSessions() {
    return _state.accounts;
}

export function getActive() {
    return _state.active;
}

// El backend ya marca `expired` en cada descriptor; se conserva el cálculo por `exp`
// como respaldo por si el descriptor viniera sin él.
export function isExpired(session) {
    if (session?.expired !== undefined) return session.expired;
    return !session?.exp || session.exp * 1000 <= Date.now();
}

// Sincroniza el caché con el backend (fuente de verdad). Sin sesión → estado vacío.
export async function fetchSession() {
    try {
        const { data } = await client.get('/auth/session');
        _state = { accounts: data.accounts || [], active: data.active || null };
        if (data.csrf) _csrf = data.csrf;
    } catch {
        _state = { accounts: [], active: null };
    }
    return _state;
}

export async function setActive(sub) {
    await client.post('/auth/session/active', { sub });
    return fetchSession();
}

export async function removeSession(sub) {
    await client.delete(`/auth/session/accounts/${sub}`);
    return fetchSession();
}

// Logout suave: cierra la cuenta activa sin revocar su token; las
// cuentas siguen en el contenedor para reingresar rápido.
export async function deactivate() {
    await client.post('/auth/logout');
    return fetchSession();
}

// Cierra TODAS las cuentas: el backend revoca cada token y destruye el contenedor.
// El error se PROPAGA a propósito: con cookie HttpOnly, JS no puede invalidar la
// sesión por su cuenta; si el backend falla, la sesión sigue viva y el caller NO debe
// aparentar que se cerró (OWASP Session Management: el logout invalida en servidor).
export async function logoutAll() {
    await client.post('/auth/logout-all');
    clearCache();
}

export function clearCache() {
    _state = { accounts: [], active: null };
    _csrf = '';
}
