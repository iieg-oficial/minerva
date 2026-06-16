import client from './client';

export async function checkPermission(data) {
    const res = await client.post('/authorization/check', data);
    return res.data;
}

export async function getMePermissions(applicationSlug) {
    const res = await client.get('/authorization/me/permissions', {
        params: { application_slug: applicationSlug },
    });
    return res.data;
}
