import { AxiosError } from 'axios';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import client from './client';
import { setCsrf } from './session';

const CSRF_REJECTED = 'Token CSRF inválido o ausente';

function respond(config, status, data) {
    const response = { data, status, statusText: String(status), headers: {}, config };
    if (status >= 400) {
        throw new AxiosError(`HTTP ${status}`, 'ERR_BAD_REQUEST', config, null, response);
    }
    return response;
}

describe('cliente del panel ante un token CSRF rotado', () => {
    const originalAdapter = client.defaults.adapter;
    let calls;

    beforeEach(() => {
        calls = [];
        setCsrf('viejo');
    });

    afterEach(() => {
        client.defaults.adapter = originalAdapter;
        setCsrf('');
    });

    it('relee la sesión y reintenta una vez con el token vigente', async () => {
        client.defaults.adapter = async (config) => {
            calls.push({ method: config.method, url: config.url, csrf: config.headers['X-CSRF-Token'] });
            if (config.url === '/auth/session') {
                return respond(config, 200, { accounts: [], active: null, csrf: 'nuevo' });
            }
            if (config.headers['X-CSRF-Token'] !== 'nuevo') {
                return respond(config, 403, { detail: CSRF_REJECTED });
            }
            return respond(config, 201, { id: 'u1' });
        };

        const { status, data } = await client.post('/users', { email: 'a@b.mx' });

        expect(status).toBe(201);
        expect(data.id).toBe('u1');
        expect(calls.map((c) => `${c.method} ${c.url} ${c.csrf ?? ''}`.trim())).toEqual([
            'post /users viejo',
            'get /auth/session',
            'post /users nuevo',
        ]);
    });

    it('no reintenta más de una vez si el token sigue sin valer', async () => {
        client.defaults.adapter = async (config) => {
            calls.push(config.url);
            if (config.url === '/auth/session') {
                return respond(config, 200, { accounts: [], active: null, csrf: 'otro-invalido' });
            }
            return respond(config, 403, { detail: CSRF_REJECTED });
        };

        await expect(client.post('/users', {})).rejects.toMatchObject({ response: { status: 403 } });
        expect(calls).toEqual(['/users', '/auth/session', '/users']);
    });

    it('no toca un 403 que no es del CSRF', async () => {
        client.defaults.adapter = async (config) => {
            calls.push(config.url);
            return respond(config, 403, { detail: 'Origin no permitido' });
        };

        await expect(client.post('/users', {})).rejects.toMatchObject({ response: { status: 403 } });
        expect(calls).toEqual(['/users']);
    });
});
