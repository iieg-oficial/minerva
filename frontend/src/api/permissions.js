import client from './client';

export async function listPermissions(params) {
    const res = await client.get('/permissions', { params });
    return res.data;
}

export async function getPermission(permId) {
    const res = await client.get(`/permissions/${permId}`);
    return res.data;
}

export async function createPermission(applicationId, data) {
    const res = await client.post('/permissions', data, { params: { application_id: applicationId } });
    return res.data;
}

export async function updatePermission(permId, data) {
    const res = await client.patch(`/permissions/${permId}`, data);
    return res.data;
}
