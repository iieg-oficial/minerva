import client from './client';
import { addSession, clearAll, getActive, getSessions, removeSession, setActive } from './session';

export async function login(email, password) {
    const response = await client.post('/auth/login', { email, password });
    const { access_token } = response.data;
    // El interceptor toma el Bearer del espejo: fijamos el token nuevo ANTES de
    // pedir el perfil para que /auth/me responda con la cuenta recién iniciada
    // (no con la que estuviera activa). addSession finaliza y sincroniza el espejo.
    localStorage.setItem('access_token', access_token);
    const profile = await getMyProfile();
    const user = profile.user || profile;
    const isAdmin = (profile.roles || []).some((r) => r.slug === 'minerva.admin');
    addSession({ token: access_token, user, isAdmin });
    return user;
}

// Lee del localStorage si el usuario autenticado es administrador de Minerva.
export function isAdmin() {
    try {
        return JSON.parse(localStorage.getItem('is_admin') || 'false') === true;
    } catch {
        return false;
    }
}

export async function getMe() {
    const response = await client.get('/auth/me');
    const user = response.data.user || response.data;
    localStorage.setItem('user', JSON.stringify(user));
    return user;
}

// Devuelve el payload completo de /auth/me: { user, roles, permissions }
export async function getMyProfile() {
    const response = await client.get('/auth/me');
    return response.data;
}

// Cierra SOLO la cuenta activa. Primero revoca su token en el backend (el
// interceptor usa el Bearer activo), luego la quita del store; si quedan otras
// cuentas, removeSession activa la siguiente no expirada.
export async function logout() {
    const active = getActive();
    try {
        await client.post('/auth/logout');
    } finally {
        if (active) removeSession(active.sub);
        else clearAll();
    }
}

// Cierra TODAS las cuentas del navegador. Revoca cada token con su propio Bearer
// (activándola antes) y limpia el store.
export async function logoutAll() {
    for (const s of getSessions()) {
        setActive(s.sub);
        try {
            await client.post('/auth/logout');
        } catch {
            // Ignora fallos individuales: igual limpiamos el store al final.
        }
    }
    clearAll();
}

export async function register(full_name, email, password) {
    const response = await client.post('/auth/register', {
        full_name,
        email,
        password,
    });
    return response.data;
}

// Flujo OAuth2: pide a Minerva la URL de redirección (con el `code`) hacia el
// sistema consumidor. Requiere sesión activa (el interceptor añade el Bearer).
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
        },
    });
    return response.data.redirect_url;
}
