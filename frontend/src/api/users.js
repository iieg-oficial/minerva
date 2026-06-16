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

export async function updateUserStatus(userId, status) {
    const res = await client.patch(`/users/${userId}/status`, { status });
    return res.data;
}
