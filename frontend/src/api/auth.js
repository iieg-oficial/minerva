import client from './client';

export async function login(email, password) {
    const response = await client.post('/auth/login', { email, password });
    const { access_token } = response.data;
    localStorage.setItem('access_token', access_token);
    const profile = await getMyProfile();
    const user = profile.user || profile;
    localStorage.setItem('user', JSON.stringify(user));
    const admin = (profile.roles || []).some((r) => r.slug === 'minerva.admin');
    localStorage.setItem('is_admin', JSON.stringify(admin));
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

export async function logout() {
    try {
        await client.post('/auth/logout');
    } finally {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('is_admin');
    }
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
export async function authorizeUrl({ clientId, redirectUri, state, scope, responseType = 'code' }) {
    const response = await client.get('/auth/authorize/url', {
        params: {
            client_id: clientId,
            redirect_uri: redirectUri,
            state,
            scope,
            response_type: responseType,
        },
    });
    return response.data.redirect_url;
}
