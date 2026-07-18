// Store multi-sesión en localStorage: la lista de cuentas iniciadas en este
// navegador y cuál está activa (patrón "cambiar de cuenta" de Google/GitHub).
//
// Fuente de verdad de las sesiones. Mantiene sincronizadas las claves legacy
// (access_token/user/is_admin = espejo de la cuenta ACTIVA) para que el
// interceptor de axios (client.js) y ProtectedRoute sigan funcionando sin
// cambios: ellos leen access_token/is_admin y aquí garantizamos que reflejen la
// cuenta activa.

const SESSIONS_KEY = 'minerva_sessions';
const ACTIVE_KEY = 'minerva_active_sub';

// Decodifica el payload de un JWT sin verificar firma (solo para leer claims de
// UI: sub, email, name, exp). Base64url → JSON. Tolera la ausencia de padding y
// caracteres UTF-8 en los nombres.
function decodeJwt(token) {
    try {
        let b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        b64 += '='.repeat((4 - (b64.length % 4)) % 4);
        const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
        return JSON.parse(new TextDecoder().decode(bytes));
    } catch {
        return {};
    }
}

function readSessions() {
    try {
        const raw = JSON.parse(localStorage.getItem(SESSIONS_KEY) || '[]');
        return Array.isArray(raw) ? raw : [];
    } catch {
        return [];
    }
}

function writeSessions(sessions) {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
}

// Refleja la cuenta activa en las claves legacy que ya leen client.js (Bearer) y
// ProtectedRoute (access_token/is_admin). Con `null` limpia el espejo → la app
// queda "sin sesión activa" aunque queden cuentas en el store.
function syncMirror(session) {
    if (!session) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('is_admin');
        localStorage.removeItem(ACTIVE_KEY);
        return;
    }
    localStorage.setItem('access_token', session.token);
    localStorage.setItem('user', JSON.stringify(session.user));
    localStorage.setItem('is_admin', JSON.stringify(!!session.isAdmin));
    localStorage.setItem(ACTIVE_KEY, session.sub);
}

export function getSessions() {
    return readSessions();
}

export function getActive() {
    const activeSub = localStorage.getItem(ACTIVE_KEY);
    return readSessions().find((s) => s.sub === activeSub) || null;
}

// Una sesión está expirada si su `exp` (segundos) ya pasó. Sin exp la tratamos
// como expirada (dato incompleto).
export function isExpired(session) {
    return !session?.exp || session.exp * 1000 <= Date.now();
}

// Agrega (o reemplaza, si ya existía la misma cuenta) una sesión a partir de su
// token + perfil, y la deja activa.
export function addSession({ token, user, isAdmin }) {
    const claims = decodeJwt(token);
    const sub = claims.sub || user?.id;
    const session = {
        sub,
        email: user?.email || claims.email || '',
        name: user?.full_name || claims.name || '',
        token,
        exp: claims.exp || 0,
        user,
        isAdmin: !!isAdmin,
    };
    const sessions = readSessions().filter((s) => s.sub !== sub);
    sessions.push(session);
    writeSessions(sessions);
    syncMirror(session);
    return session;
}

// Cambia la cuenta activa; el interceptor tomará su token del espejo.
export function setActive(sub) {
    const session = readSessions().find((s) => s.sub === sub);
    if (session) syncMirror(session);
    return session || null;
}

// Quita una cuenta del store. Si era la activa, pasa a otra no expirada (o limpia
// el espejo si no quedan).
export function removeSession(sub) {
    const sessions = readSessions().filter((s) => s.sub !== sub);
    writeSessions(sessions);
    if (localStorage.getItem(ACTIVE_KEY) === sub) {
        syncMirror(sessions.find((s) => !isExpired(s)) || sessions[0] || null);
    }
}

export function clearAll() {
    localStorage.removeItem(SESSIONS_KEY);
    syncMirror(null);
}

// Degrada la cuenta activa a expirada (exp=0) y limpia el espejo, sin borrarla:
// tras un 401 la app queda "sin sesión activa" pero el selector la sigue
// mostrando (atenuada, con opción de reingresar).
export function expireActive() {
    const activeSub = localStorage.getItem(ACTIVE_KEY);
    // Si hay cuenta activa, la degrada a expirada (el selector la muestra para
    // reingresar). Pase lo que pase, SIEMPRE limpia el espejo legacy: sin esto,
    // una sesión con `access_token` pero sin `minerva_active_sub` (de una versión
    // previa, o BD reseteada con llaves rotadas) dejaba el token intacto tras el
    // 401 y el panel entraba en loop /admin↔/login.
    if (activeSub) {
        writeSessions(readSessions().map((s) => (s.sub === activeSub ? { ...s, exp: 0 } : s)));
    }
    syncMirror(null);
}
