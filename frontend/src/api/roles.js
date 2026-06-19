import client from './client';

export async function listRoles(params) {
    const res = await client.get('/roles', { params });
    return res.data;
}

export async function getRole(roleId) {
    const res = await client.get(`/roles/${roleId}`);
    return res.data;
}

export async function createRole(applicationId, data) {
    const res = await client.post('/roles', data, { params: { application_id: applicationId } });
    return res.data;
}

export async function updateRole(roleId, data) {
    const res = await client.patch(`/roles/${roleId}`, data);
    return res.data;
}

export async function deleteRole(roleId) {
    const res = await client.delete(`/roles/${roleId}`);
    return res.data;
}

export async function getRolePermissions(roleId) {
    const res = await client.get(`/roles/${roleId}/permissions`);
    return res.data;
}

export async function getRoleUsers(roleId) {
    const res = await client.get(`/roles/${roleId}/users`);
    return res.data;
}

export async function assignPermissionToRole(roleId, permissionId) {
    const res = await client.post(`/roles/${roleId}/permissions/${permissionId}`);
    return res.data;
}

export async function removePermissionFromRole(roleId, permissionId) {
    const res = await client.delete(`/roles/${roleId}/permissions/${permissionId}`);
    return res.data;
}
