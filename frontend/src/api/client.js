import axios from 'axios';
import { clearCache, getCsrf } from './session';

const client = axios.create({
    baseURL: import.meta.env?.VITE_API_URL || '/api',
    timeout: 30000,
    // Envía la cookie de sesión del panel (HttpOnly) en cada petición.
    withCredentials: true,
    headers: { 'Content-Type': 'application/json' },
});

const UNSAFE_METHODS = ['post', 'put', 'patch', 'delete'];

// Adjunta el token CSRF (synchronizer) en las mutaciones del panel. El backend lo
// exige junto con la cookie; en login/register (que crean la sesión) aún no hay
// token y el backend los exime.
client.interceptors.request.use((config) => {
    if (UNSAFE_METHODS.includes((config.method || '').toLowerCase())) {
        const csrf = getCsrf();
        if (csrf) config.headers['X-CSRF-Token'] = csrf;
    }
    return config;
});

// Evita que una ráfaga de 401 concurrentes (el panel dispara ~6 queries al montar)
// dispare múltiples redirects a la vez; basta uno.
let redirectingToLogin = false;

client.interceptors.response.use(
    (response) => response,
    (error) => {
        // El sondeo `GET /auth/session` responde 401 sin sesión: es esperado en /login
        // y /authorize; no debe forzar un redirect (rompería el flujo con `next=`).
        const isSessionProbe = (error.config?.url || '').includes('/auth/session');
        if (error.response?.status === 401 && !isSessionProbe) {
            clearCache();
            if (!redirectingToLogin && window.location.pathname !== '/login') {
                redirectingToLogin = true;
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default client;
