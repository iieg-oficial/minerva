import client from './client';

export async function login(email, password) {
    const response = await client.post('/auth/login', { email, password });
    const { access_token } = response.data;
    localStorage.setItem('access_token', access_token);
    const me = await getMe();
    return me;
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
