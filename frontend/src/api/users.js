import client from './client';

export async function listUsers(params) {
    const res = await client.get('/users', { params });
    return res.data;
}

export async function getUser(userId) {
    const res = await client.get(`/users/${userId}`);
    return res.data;
}

export async function createUser(data) {
    const res = await client.post('/users', data);
    return res.data;
}

export async function updateUser(userId, data) {
    const res = await client.patch(`/users/${userId}`, data);
    return res.data;
}

// Enlace de un solo uso para que la persona fije su contraseña: invitación si sigue
// pendiente, restablecimiento si no. Invalida los enlaces anteriores del usuario. Con
// `applicationId`, al guardar la contraseña la persona sigue a esa aplicación.
export async function createCredentialLink(userId, applicationId = null) {
    const body = applicationId ? { application_id: applicationId } : undefined;
    const res = await client.post(`/users/${userId}/credential-link`, body);
    return res.data;
}

// Aplicaciones a las que puede llevar el enlace: las que la persona usa y tienen inicio.
export async function listCredentialDestinations(userId) {
    const res = await client.get(`/users/${userId}/credential-destinations`);
    return res.data;
}

export async function updateUserStatus(userId, status) {
    const res = await client.patch(`/users/${userId}/status`, { status });
    return res.data;
}
