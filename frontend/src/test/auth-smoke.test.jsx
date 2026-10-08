/**
 * Smoke E2E de la autenticación web del panel.
 *
 * Los tests de `features/auth` mockean `@/api/*`: prueban cada página por separado,
 * pero nadie prueba el cableado que las une —la cookie opaca, el token CSRF, los
 * parámetros que llegan al `/authorize` y la navegación entre rutas—. Aquí se monta
 * la app COMPLETA (rutas reales, `SessionProvider`, `@/api/*` y los interceptores de
 * axios de verdad) y se sustituye únicamente el transporte HTTP por una Minerva
 * simulada que exige los mismos invariantes que el backend.
 *
 * Herramienta: vitest + jsdom, lo que el CI ya ejecuta con `npm test`. Un runner de
 * navegador (Playwright) pediría descargar navegadores y levantar backend, Postgres y
 * Redis en el CI para cubrir esta misma jornada; el gate que falta se sostiene con lo
 * que ya hay.
 *
 * Cubre una jornada crítica y sus fallos:
 *  1. login con cookie + CSRF,
 *  2. /authorize transporta `state` y `max_age`,
 *  3. cambiar de cuenta aísla al consumidor,
 *  4. un logout fallido no navega ni finge haber cerrado la sesión,
 *  5. tras cerrar sesión, la cuenta no se reactiva sin contraseña.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '@/App';
import client from '@/api/client';
import { clearCache, getActive } from '@/api/session';

// antd las necesita en jsdom y no existen ahí.
window.matchMedia = vi.fn(() => ({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
}));
globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
};

const ANA = {
    sub: 'u-ana',
    email: 'ana@iieg.gob.mx',
    name: 'Ana Analista',
    password: 'Secreta123',
    is_admin: true,
};
const BETO = {
    sub: 'u-beto',
    email: 'beto@iieg.gob.mx',
    name: 'Beto Bravo',
    password: 'Secreta456',
    is_admin: true,
};

const REDIRECT_URI = 'https://portal-demo.iieg.gob.mx/callback';
const CONSULTA_CONSUMIDOR = `client_id=portal_demo&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&response_type=code&state=xyz`;

const METODOS_MUTANTES = ['POST', 'PUT', 'PATCH', 'DELETE'];
// Crean la sesión, así que se autentican con credenciales y no con la sesión previa:
// cuando se llaman todavía no existe token CSRF. Igual que `_CSRF_EXEMPT_PREFIXES`
// del middleware del backend, acotado a lo que usa el panel.
const EXENTAS_DE_CSRF = ['/auth/login', '/auth/register'];

function descriptor(cuenta, cerrada = false) {
    return {
        sub: cuenta.sub,
        email: cuenta.email,
        name: cuenta.name,
        is_admin: !!cuenta.is_admin,
        exp: cerrada ? 0 : (cuenta.exp ?? Math.floor(Date.now() / 1000) + 3600),
        expired: cerrada || !!cuenta.expired,
        signed_out: cerrada,
    };
}

function leerCabecera(config, nombre) {
    const cabeceras = config.headers;
    if (!cabeceras) return null;
    if (typeof cabeceras.get === 'function') return cabeceras.get(nombre) ?? null;
    return cabeceras[nombre] ?? null;
}

/**
 * Minerva simulada como adaptador de axios: responde con las formas reales del
 * backend y aplica sus mismas reglas —cookie de sesión, rotación del CSRF en cada
 * login y rechazo de las mutaciones sin token—, para que romper el cableado del
 * cliente rompa este smoke en vez de pasar inadvertido.
 *
 * `fallos` fuerza el status de una ruta concreta (`'POST /auth/logout': 500`).
 */
function crearMinervaFalsa({ usuarios = [], sesionPrevia = null, fallos = {} } = {}) {
    const estado = {
        cuentas: sesionPrevia ? [...sesionPrevia.cuentas] : [],
        activa: sesionPrevia?.activa ?? null,
        // Cuentas cerradas con «Cerrar sesión»: siguen listadas, pero su token se revocó.
        cerradas: new Set(),
        csrf: sesionPrevia ? 'csrf-inicial' : '',
        // La cookie es HttpOnly: JS nunca la ve. Se simula del lado del servidor
        // porque es justo lo que el navegador reenviaría en cada petición.
        cookie: sesionPrevia ? 'sid-inicial' : null,
    };
    const peticiones = [];
    const noRuteadas = [];
    let rotaciones = 0;
    let codigos = 0;

    function responder(config, status, data) {
        if (status >= 200 && status < 300) {
            return { data, status, statusText: 'OK', headers: {}, config };
        }
        const error = new Error(`Request failed with status code ${status}`);
        error.isAxiosError = true;
        error.config = config;
        error.response = { data, status, headers: {}, config };
        return Promise.reject(error);
    }

    async function adaptador(config) {
        const metodo = (config.method || 'get').toUpperCase();
        const ruta = config.url;
        const csrfEnviado = leerCabecera(config, 'X-CSRF-Token');
        const cuerpo =
            typeof config.data === 'string' ? JSON.parse(config.data) : (config.data ?? null);
        peticiones.push({
            metodo,
            ruta,
            params: config.params ?? null,
            csrf: csrfEnviado,
            withCredentials: config.withCredentials === true,
            cuerpo,
        });

        // Ninguna respuesta llega en el mismo microtask que la petición, y una mutación
        // tarda más que una lectura. Modelarlo hace determinista lo que en producción
        // sería una carrera intermitente: si la SPA pidiera el code sin esperar a que el
        // cambio de cuenta llegue al servidor, aquí fallaría siempre, no de vez en cuando.
        await new Promise((resolve) =>
            setTimeout(resolve, METODOS_MUTANTES.includes(metodo) ? 20 : 0)
        );

        // Sin `withCredentials` el navegador no manda la cookie opaca (ni guarda el
        // Set-Cookie del login): para Minerva la petición es anónima.
        if (config.withCredentials !== true) {
            return responder(config, 401, { detail: 'No autenticado' });
        }
        const conSesion = estado.cookie !== null;

        const forzado = fallos[`${metodo} ${ruta}`];
        if (forzado) return responder(config, forzado, { detail: 'Fallo simulado' });

        if (
            METODOS_MUTANTES.includes(metodo) &&
            conSesion &&
            !EXENTAS_DE_CSRF.some((prefijo) => ruta.startsWith(prefijo)) &&
            csrfEnviado !== estado.csrf
        ) {
            return responder(config, 403, { detail: 'Token CSRF inválido o ausente' });
        }

        if (metodo === 'POST' && ruta === '/auth/login') {
            const usuario = usuarios.find(
                (u) => u.email === cuerpo?.email && u.password === cuerpo?.password
            );
            if (!usuario)
                return responder(config, 401, { detail: 'Usuario o contraseña incorrectos' });
            // El backend rota sid y CSRF en cada login (fijación de sesión).
            rotaciones += 1;
            estado.cookie = `sid-${rotaciones}`;
            estado.csrf = `csrf-${rotaciones}`;
            if (!estado.cuentas.some((c) => c.sub === usuario.sub)) estado.cuentas.push(usuario);
            estado.cerradas.delete(usuario.sub);
            estado.activa = usuario.sub;
            return responder(config, 200, { active: descriptor(usuario), csrf: estado.csrf });
        }

        if (metodo === 'GET' && ruta === '/auth/session') {
            if (!conSesion) return responder(config, 401, { detail: 'No autenticado' });
            const activa = estado.cuentas.find((c) => c.sub === estado.activa);
            return responder(config, 200, {
                accounts: estado.cuentas.map((c) => descriptor(c, estado.cerradas.has(c.sub))),
                active: activa ? descriptor(activa) : null,
                csrf: estado.csrf,
            });
        }

        if (metodo === 'POST' && ruta === '/auth/session/active') {
            if (!conSesion) return responder(config, 401, { detail: 'No autenticado' });
            const cuenta = estado.cuentas.find((c) => c.sub === cuerpo?.sub);
            if (!cuenta)
                return responder(config, 404, {
                    detail: 'La cuenta no está iniciada en este navegador',
                });
            if (estado.cerradas.has(cuenta.sub))
                return responder(config, 409, {
                    detail: 'La sesión de esta cuenta está cerrada; ingresa tu contraseña para continuar',
                });
            estado.activa = cuenta.sub;
            return responder(config, 200, descriptor(cuenta));
        }

        if (metodo === 'POST' && ruta === '/auth/logout') {
            if (!conSesion) return responder(config, 401, { detail: 'No autenticado' });
            // Revoca la activa: sigue en el contenedor, pero ya no se activa sin contraseña.
            if (estado.activa) estado.cerradas.add(estado.activa);
            estado.activa = null;
            return responder(config, 200, { message: 'Sesión cerrada' });
        }

        if (metodo === 'GET' && ruta === '/auth/authorize/url') {
            if (!conSesion || !estado.activa)
                return responder(config, 401, { detail: 'No autenticado' });
            codigos += 1;
            const destino = new URL(config.params.redirect_uri);
            // El code se emite para la cuenta ACTIVA en el servidor: si la SPA pidiera
            // el code antes de cambiarla, aquí saldría el de la cuenta anterior.
            destino.searchParams.set('code', `codigo-${estado.activa}-${codigos}`);
            destino.searchParams.set('state', config.params.state);
            return responder(config, 200, { redirect_url: destino.toString() });
        }

        if (metodo === 'GET' && ruta.startsWith('/public/apps/')) {
            return responder(config, 200, {
                name: 'portal_demo',
                display_name: 'Portal Demo',
                brand_color: '#5C2472',
            });
        }

        noRuteadas.push(`${metodo} ${ruta}`);
        return responder(config, 501, { detail: 'Ruta no simulada' });
    }

    return { adaptador, peticiones, noRuteadas, estado };
}

let minerva;
let navegadoA;

function instalar(falsa) {
    minerva = falsa;
    client.defaults.adapter = falsa.adaptador;
    return falsa;
}

function abrir(ruta) {
    return render(
        <MemoryRouter initialEntries={[ruta]}>
            <App />
        </MemoryRouter>
    );
}

// Deja correr los efectos pendientes: una navegación indebida no se materializa en
// el mismo render que la dispara, así que sin esto un "no navega" pasaría siempre.
async function asentar() {
    await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
    });
}

function rutasVistas() {
    return minerva.peticiones.map((p) => `${p.metodo} ${p.ruta}`);
}

function peticion(metodo, ruta) {
    return minerva.peticiones.find((p) => p.metodo === metodo && p.ruta === ruta);
}

beforeEach(() => {
    minerva = null;
    navegadoA = null;
    clearCache(); // el caché de `api/session` es estado de módulo y sobrevive entre tests
    vi.spyOn(window, 'location', 'get').mockReturnValue({
        origin: 'http://localhost:3000',
        pathname: '/login',
        get href() {
            return navegadoA ?? 'http://localhost:3000/';
        },
        set href(valor) {
            navegadoA = valor;
        },
    });
});

afterEach(() => {
    // Una ruta no simulada significa que la jornada tocó un endpoint que este smoke
    // no describe: el test que la provoque debe verlo, no tragársela.
    expect(minerva?.noRuteadas ?? []).toEqual([]);
    vi.restoreAllMocks();
    vi.clearAllMocks();
});

describe('Smoke E2E de autenticación web', () => {
    it('jornada feliz: el consumidor manda a /authorize, el usuario entra y vuelve con su code', async () => {
        instalar(crearMinervaFalsa({ usuarios: [ANA] }));
        const user = userEvent.setup();
        abrir(`/authorize?${CONSULTA_CONSUMIDOR}&max_age=0`);

        // Sin sesión, /authorize reanuda en el login conservando el destino completo:
        // el branding se pide con el client_id extraído de ese `next`.
        const correo = await screen.findByLabelText(/Correo electrónico/);
        await user.clear(correo);
        await user.type(correo, ANA.email);
        await user.type(screen.getByLabelText(/Contraseña/), ANA.password);
        await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }));

        await vi.waitFor(() => expect(navegadoA).not.toBeNull());
        const vuelta = new URL(navegadoA);
        expect(vuelta.origin + vuelta.pathname).toBe(REDIRECT_URI);
        expect(vuelta.searchParams.get('code')).toBe(`codigo-${ANA.sub}-1`);
        expect(vuelta.searchParams.get('state')).toBe('xyz');

        // El login viaja con la cookie y sin CSRF (aún no existe); el backend lo exime.
        const login = peticion('POST', '/auth/login');
        expect(login.withCredentials).toBe(true);
        expect(login.csrf).toBeNull();
        expect(peticion('GET', '/public/apps/portal_demo/branding')).toBeDefined();

        // `state` y `max_age` sobreviven al desvío por el login.
        expect(peticion('GET', '/auth/authorize/url').params).toMatchObject({
            client_id: 'portal_demo',
            redirect_uri: REDIRECT_URI,
            state: 'xyz',
            max_age: 0,
        });

        expect(minerva.peticiones.every((p) => p.withCredentials)).toBe(true);
        // El JWT no toca el navegador: solo la cookie opaca, invisible para JS.
        expect(localStorage.length + sessionStorage.length).toBe(0);
    });

    it('cambiar de cuenta aísla al consumidor: el code se emite para la elegida, no para la última que entró', async () => {
        instalar(
            crearMinervaFalsa({
                usuarios: [BETO],
                sesionPrevia: { cuentas: [ANA], activa: ANA.sub },
            })
        );
        const user = userEvent.setup();
        abrir(`/authorize?${CONSULTA_CONSUMIDOR}&prompt=select_account`);

        // El consumidor pidió elegir cuenta: se agrega una segunda al navegador.
        await user.click(await screen.findByRole('button', { name: /Agregar cuenta/ }));
        const correo = await screen.findByLabelText(/Correo electrónico/);
        await user.clear(correo);
        await user.type(correo, BETO.email);
        await user.type(screen.getByLabelText(/Contraseña/), BETO.password);
        await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }));

        // De vuelta en el selector, con Beto activo, el usuario elige a Ana. El rediseno
        // muestra las cuentas como filas y activa la elegida al pulsarla, sin el paso
        // intermedio de «Ver otras cuentas» y «Continuar».
        await user.click(await screen.findByRole('button', { name: new RegExp(ANA.name) }));

        await vi.waitFor(() => expect(navegadoA).not.toBeNull());
        expect(new URL(navegadoA).searchParams.get('code')).toBe(`codigo-${ANA.sub}-1`);
        expect(minerva.estado.activa).toBe(ANA.sub);

        // La mutación lleva el CSRF que rotó el segundo login, no el de antes.
        const cambio = peticion('POST', '/auth/session/active');
        expect(cambio.cuerpo).toEqual({ sub: ANA.sub });
        expect(cambio.csrf).toBe('csrf-1');
        expect(cambio.csrf).not.toBe('csrf-inicial');
    });

    it('un logout fallido no navega ni finge que la sesión se cerró', async () => {
        instalar(
            crearMinervaFalsa({
                sesionPrevia: { cuentas: [ANA], activa: ANA.sub },
                fallos: { 'POST /auth/logout': 500 },
            })
        );
        abrir('/logout?redirect_uri=/admin/users');

        expect(await screen.findByText('No se pudo cerrar la sesión')).toBeInTheDocument();
        await asentar();
        expect(screen.getByText('No se pudo cerrar la sesión')).toBeInTheDocument();
        expect(navegadoA).toBeNull();
        // Un fallo de logout solo deja el sondeo de sesión y el intento: si navegara al
        // destino, el panel se montaría detrás y pediría sus datos.
        expect(rutasVistas()).toEqual(['GET /auth/session', 'POST /auth/logout']);
        // Con cookie HttpOnly la SPA no puede invalidar nada por su cuenta: si el
        // backend no confirma, la sesión sigue viva en los dos lados.
        expect(getActive()?.sub).toBe(ANA.sub);
        expect(minerva.estado.activa).toBe(ANA.sub);
    });

    it('el logout exitoso cierra la sesión y nunca navega a un destino externo', async () => {
        instalar(crearMinervaFalsa({ sesionPrevia: { cuentas: [ANA], activa: ANA.sub } }));
        abrir('/logout?redirect_uri=https://portal-demo.iieg.gob.mx/adios');

        // Sin `post_logout_redirect_uris` registradas, el destino externo cae al login.
        expect(await screen.findByText('Iniciar sesión con:')).toBeInTheDocument();
        expect(navegadoA).toBeNull();
        expect(peticion('POST', '/auth/logout').csrf).toBe('csrf-inicial');
        expect(getActive()).toBeNull();
        expect(minerva.estado.activa).toBeNull();
    });

    it('tras cerrar sesión, la cuenta sigue en el selector pero pide contraseña para volver', async () => {
        instalar(
            crearMinervaFalsa({
                usuarios: [ANA],
                sesionPrevia: { cuentas: [ANA], activa: ANA.sub },
            })
        );
        const user = userEvent.setup();
        abrir('/logout?redirect_uri=/login');

        expect(await screen.findByText('Pedirá tu contraseña')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: new RegExp(ANA.name) }));

        // Quien llega después al equipo no entra con sólo tocar la cuenta: se pide la
        // contraseña y no se intenta reactivarla.
        const campo = await screen.findByPlaceholderText('Contraseña');
        expect(peticion('POST', '/auth/session/active')).toBeUndefined();
        expect(minerva.estado.activa).toBeNull();

        await user.type(campo, ANA.password);
        await user.click(screen.getByRole('button', { name: 'Entrar' }));

        await vi.waitFor(() => expect(minerva.estado.activa).toBe(ANA.sub));
        expect(peticion('POST', '/auth/login').cuerpo).toEqual({
            email: ANA.email,
            password: ANA.password,
        });
    });
});
