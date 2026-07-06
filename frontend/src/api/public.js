import client from './client';

// Branding público de una aplicación (sin auth): lo usa la pantalla de login
// para mostrar a qué sistema está entrando el usuario. Devuelve null si la app
// no existe o no tiene branding consultable.
export async function getAppBranding(clientId) {
    const res = await client.get(`/public/apps/${clientId}/branding`);
    return res.data;
}
