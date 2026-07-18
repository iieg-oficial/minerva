// Self-check del store multi-sesión (session.js). No usa framework de tests:
// stubbea localStorage y corre asserts. Ejecutar con: node src/api/session.selfcheck.mjs
import assert from 'node:assert';

// Stub mínimo de localStorage (session.js solo usa get/set/removeItem).
const store = new Map();
globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
};

const { addSession, setActive, removeSession, clearAll, getSessions, getActive, isExpired, expireActive, deactivate } =
    await import('./session.js');

const tokenFor = (sub, exp) => {
    const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
    return `${b64({ alg: 'RS256' })}.${b64({ sub, exp, email: `${sub}@iieg.gob.mx`, name: sub })}.sig`;
};
const future = Math.floor(Date.now() / 1000) + 3600;
const past = Math.floor(Date.now() / 1000) - 10;

// addSession deja la cuenta activa y sincroniza el espejo legacy.
addSession({ token: tokenFor('ana', future), user: { id: 'ana', email: 'ana@iieg.gob.mx', full_name: 'Ana' }, isAdmin: true });
assert.equal(getActive().sub, 'ana');
assert.equal(localStorage.getItem('access_token'), tokenFor('ana', future));
assert.equal(localStorage.getItem('is_admin'), 'true');

// Segunda cuenta: se agrega y pasa a ser la activa.
addSession({ token: tokenFor('luis', future), user: { id: 'luis', email: 'luis@iieg.gob.mx', full_name: 'Luis' }, isAdmin: false });
assert.equal(getSessions().length, 2);
assert.equal(getActive().sub, 'luis');

// setActive vuelve a Ana y su token queda en el espejo.
assert.equal(setActive('ana').sub, 'ana');
assert.equal(getActive().sub, 'ana');
assert.equal(localStorage.getItem('access_token'), tokenFor('ana', future));

// isExpired según exp.
assert.equal(isExpired({ exp: future }), false);
assert.equal(isExpired({ exp: past }), true);
assert.equal(isExpired({}), true);

// Re-login de una cuenta existente reemplaza su token (no duplica).
addSession({ token: tokenFor('ana', past), user: { id: 'ana', email: 'ana@iieg.gob.mx', full_name: 'Ana' }, isAdmin: true });
assert.equal(getSessions().filter((s) => s.sub === 'ana').length, 1);

// removeSession de la activa cae a otra cuenta.
setActive('luis');
removeSession('luis');
assert.equal(getSessions().length, 1);
assert.equal(getActive().sub, 'ana');

// clearAll limpia store y espejo.
clearAll();
assert.equal(getSessions().length, 0);
assert.equal(localStorage.getItem('access_token'), null);

// Regresión (loop /admin↔/login): un espejo legacy con access_token pero SIN
// minerva_active_sub debe quedar limpio tras expireActive (antes no lo limpiaba).
clearAll();
localStorage.setItem('access_token', tokenFor('viejo', past));
localStorage.setItem('is_admin', 'true');
expireActive();
assert.equal(localStorage.getItem('access_token'), null);
assert.equal(localStorage.getItem('is_admin'), null);

// Logout suave (deactivate): sale de la cuenta pero NO la vence — sigue en el
// store con su exp real y el espejo (access_token) queda limpio para volver rápido.
clearAll();
addSession({ token: tokenFor('sol', future), user: { id: 'sol', email: 'sol@iieg.gob.mx', full_name: 'Sol' }, isAdmin: false });
deactivate();
assert.equal(localStorage.getItem('access_token'), null); // salió: sin sesión activa
assert.equal(getSessions().length, 1); // pero la cuenta sigue guardada
assert.equal(isExpired(getSessions()[0]), false); // y NO quedó vencida

console.log('session.selfcheck OK');
