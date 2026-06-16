import client from './client';

export async function listGroups(params) {
    const res = await client.get('/groups', { params });
    return res.data;
}

export async function getGroup(groupId) {
    const res = await client.get(`/groups/${groupId}`);
    return res.data;
}

export async function createGroup(data) {
    const res = await client.post('/groups', data);
    return res.data;
}

export async function updateGroup(groupId, data) {
    const res = await client.patch(`/groups/${groupId}`, data);
    return res.data;
}

export async function addUserToGroup(groupId, userId) {
    const res = await client.post(`/groups/${groupId}/users/${userId}`);
    return res.data;
}

export async function removeUserFromGroup(groupId, userId) {
    const res = await client.delete(`/groups/${groupId}/users/${userId}`);
    return res.data;
}

export async function addRoleToGroup(groupId, roleId) {
    const res = await client.post(`/groups/${groupId}/roles/${roleId}`);
    return res.data;
}

export async function removeRoleFromGroup(groupId, roleId) {
    const res = await client.delete(`/groups/${groupId}/roles/${roleId}`);
    return res.data;
}

export async function assignRoleToUser(userId, roleId) {
    const res = await client.post(`/groups/users/${userId}/roles/${roleId}`);
    return res.data;
}

export async function removeRoleFromUser(userId, roleId) {
    const res = await client.delete(`/groups/users/${userId}/roles/${roleId}`);
    return res.data;
}
