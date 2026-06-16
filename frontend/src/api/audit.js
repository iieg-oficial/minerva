import client from './client';

export async function listLogs(params) {
    const res = await client.get('/audit', { params });
    return res.data;
}
