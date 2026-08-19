export async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('application/json')
    ? await response.json()
    : { detail: await response.text() };
  return { response, body };
}

export const getConfig = () => requestJson('/api/config');
export const getSession = () => requestJson('/api/session');
export const getDocuments = () => requestJson('/api/documents');
export const createDocument = () => requestJson('/api/documents', { method: 'POST' });
export const getAdministration = () => requestJson('/api/admin');
