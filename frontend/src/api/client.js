import axios from 'axios';
import { expireActive } from './session';

const client = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '/api',
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
});

client.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Evita que una ráfaga de 401 concurrentes (el panel dispara ~6 queries al montar)
// dispare múltiples redirects a la vez; basta uno.
let redirectingToLogin = false;

client.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            // Degrada la cuenta activa a expirada y limpia el espejo (access_token/
            // user/is_admin). El selector la seguirá mostrando para reingresar.
            expireActive();
            if (!redirectingToLogin && window.location.pathname !== '/login') {
                redirectingToLogin = true;
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default client;
