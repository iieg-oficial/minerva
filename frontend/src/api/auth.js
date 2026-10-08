import client from './client';
import {
    deactivate,
    fetchSession,
    getActive,
    logoutAll as sessionLogoutAll,
    setCsrf,
} from './session';

// Login del panel: el backend fija la cookie de sesión (Set-Cookie) y devuelve el
// descriptor de la cuenta activa + el token CSRF (nunca el JWT). Refrescamos el
// caché multi-cuenta para reflejar la cuenta recién iniciada.
export async function login(email, password) {
    const { data } = await client.post('/auth/login', { email, password });
    setCsrf(data.csrf);
    await fetchSession();
    return data.active;
}

// ¿La cuenta activa es administradora de Minerva? Se lee del descriptor verificado
// por el backend (no de un valor persistido en el navegador).
export function isAdmin() {
    return !!getActive()?.is_admin;
}

export async function getMe() {
    const { data } = await client.get('/auth/me');
    return data.user || data;
}

// Devuelve el payload completo de /auth/me: { user, roles, permissions }
export async function getMyProfile() {
    const { data } = await client.get('/auth/me');
    return data;
}

// Cierra la sesión de la cuenta activa y revoca su token: volver a ella pide
// contraseña. "Cerrar todas las sesiones" (logoutAll) y quitar una cuenta
// (removeSession) además la sacan del navegador.
export function logout() {
    return deactivate();
}

// Cierra TODAS las cuentas del navegador; el backend revoca cada token y destruye
// el contenedor de sesión.
export function logoutAll() {
    return sessionLogoutAll();
}

// Cambio de contraseña propio: exige la actual. El backend invalida todas las sesiones del
// usuario y saca su cuenta del navegador, así que después hay que volver a iniciar sesión.
export async function changePassword(currentPassword, newPassword) {
    await client.post('/auth/password', {
        current_password: currentPassword,
        new_password: newPassword,
    });
    // Refleja en el caché que la cuenta salió; si falla, el cambio ya quedó hecho igual.
    await fetchSession().catch(() => {});
}

export async function register(full_name, email, password) {
    const { data } = await client.post('/auth/register', { full_name, email, password });
    setCsrf(data.csrf);
    await fetchSession();
    return data;
}

// Flujo OAuth2: pide a Minerva la URL de redirección (con el `code`) hacia el
// sistema consumidor. Usa la cookie de sesión del panel (la envía withCredentials).
export async function authorizeUrl({
    clientId,
    redirectUri,
    state,
    scope,
    responseType = 'code',
    codeChallenge,
    codeChallengeMethod,
    nonce,
    prompt,
    maxAge,
}) {
    const response = await client.get('/auth/authorize/url', {
        params: {
            client_id: clientId,
            redirect_uri: redirectUri,
            state,
            scope,
            response_type: responseType,
            // PKCE: solo se envían si el consumidor los mandó (clientes públicos).
            ...(codeChallenge ? { code_challenge: codeChallenge } : {}),
            ...(codeChallengeMethod ? { code_challenge_method: codeChallengeMethod } : {}),
            ...(nonce ? { nonce } : {}),
            ...(prompt ? { prompt } : {}),
            ...(maxAge !== undefined ? { max_age: maxAge } : {}),
        },
    });
    return response.data.redirect_url;
}
