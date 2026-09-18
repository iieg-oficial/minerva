import client from './client';
import { fetchSession } from './session';

// Enlaces de un solo uso para fijar la contraseña (invitación, restablecimiento o cambio
// obligatorio). Son públicos: la credencial es el token del enlace, no la sesión del panel.

export async function inspectCredential(token) {
    const { data } = await client.post('/auth/credential/inspect', { token });
    return data;
}

export async function setCredential(token, password) {
    const { data } = await client.post('/auth/credential', { token, password });
    // Fijar la contraseña revoca las sesiones del usuario en el backend; sin refrescar el
    // caché, el selector se queda con el estado viejo y cicla (login → selector → login).
    await fetchSession().catch(() => {});
    return data;
}
