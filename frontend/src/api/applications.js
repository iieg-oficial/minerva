import client from './client';

export async function listApplications(params) {
    const res = await client.get('/applications', { params });
    return res.data;
}

export async function getApplication(appId) {
    const res = await client.get(`/applications/${appId}`);
    return res.data;
}

export async function createApplication(data) {
    const res = await client.post('/applications', data);
    return res.data;
}

export async function updateApplication(appId, data) {
    const res = await client.patch(`/applications/${appId}`, data);
    return res.data;
}

export async function deleteApplication(appId) {
    await client.delete(`/applications/${appId}`);
}

export async function regenerateSecret(appId) {
    const res = await client.post(`/applications/${appId}/regenerate-secret`);
    return res.data;
}

export async function listRedirectUris(appId) {
    const res = await client.get(`/applications/${appId}/redirect-uris`);
    return res.data;
}

export async function addRedirectUri(appId, data) {
    const res = await client.post(`/applications/${appId}/redirect-uris`, data);
    return res.data;
}

export async function importManifest(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await client.post('/applications/import-manifest', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
}

export async function updateManifest(appId, file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await client.post(`/applications/${appId}/import-manifest`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
}
