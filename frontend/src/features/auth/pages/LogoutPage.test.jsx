import { StrictMode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LogoutPage, { safePath } from './LogoutPage';

vi.mock('@/api/auth', () => ({ logout: vi.fn() }));
vi.mock('@features/auth/SessionContext', () => ({ useSession: vi.fn() }));

const authAPI = await import('@/api/auth');
const { useSession } = await import('@features/auth/SessionContext');

// Detecta navegaciones fuera del origen: nada debe asignar `window.location.href`.
let assignedHref;

beforeEach(() => {
    assignedHref = null;
    useSession.mockReturnValue({ loading: false, active: { sub: 'u-1' } });
    vi.spyOn(window, 'location', 'get').mockReturnValue({
        origin: 'http://localhost:3000',
        set href(value) {
            assignedHref = value;
        },
    });
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
});

function renderLogout(search) {
    return render(
        <MemoryRouter initialEntries={[`/logout${search}`]}>
            <Routes>
                <Route path="/logout" element={<LogoutPage />} />
                <Route path="/login" element={<div>pantalla de login</div>} />
                <Route path="/admin/users" element={<div>usuarios</div>} />
            </Routes>
        </MemoryRouter>,
    );
}

// `main.jsx` monta la app dentro de <StrictMode>, que remonta cada componente y expone
// los efectos sin guard.
function renderLogoutStrict(search) {
    return render(
        <StrictMode>
            <MemoryRouter initialEntries={[`/logout${search}`]}>
                <Routes>
                    <Route path="/logout" element={<LogoutPage />} />
                    <Route path="/login" element={<div>pantalla de login</div>} />
                    <Route path="/admin/users" element={<div>usuarios</div>} />
                </Routes>
            </MemoryRouter>
        </StrictMode>,
    );
}

describe('safePath', () => {
    it('acepta rutas internas y conserva query y hash', () => {
        expect(safePath('/admin/users')).toBe('/admin/users');
        expect(safePath('/admin/users?page=2#top')).toBe('/admin/users?page=2#top');
    });

    it('rechaza destinos externos y cae al login local', () => {
        // El parser de URLs elimina los tabs, dejando `//evil.org`: host externo.
        const vectores = [
            'https://evil.org',
            'http://evil.org',
            '//evil.org',
            '/\\evil.org',
            '/\t/evil.org',
            '\t//evil.org',
            'javascript:alert(1)',
        ];
        for (const vector of vectores) {
            expect(safePath(vector), `debía rechazar ${JSON.stringify(vector)}`).toBe('/login');
        }
    });

    it('cae al login cuando no hay destino', () => {
        expect(safePath(null)).toBe('/login');
        expect(safePath('')).toBe('/login');
    });
});

describe('LogoutPage', () => {
    it('navega a la ruta local solo después de un logout exitoso', async () => {
        authAPI.logout.mockResolvedValue(undefined);
        renderLogout('?redirect_uri=/admin/users');

        expect(await screen.findByText('usuarios')).toBeInTheDocument();
        expect(authAPI.logout).toHaveBeenCalledTimes(1);
    });

    it('nunca navega a una URL externa: cae al login', async () => {
        authAPI.logout.mockResolvedValue(undefined);
        renderLogout('?redirect_uri=https://example.org');

        expect(await screen.findByText('pantalla de login')).toBeInTheDocument();
        expect(assignedHref).toBeNull();
    });

    it('nunca navega a un destino externo ofuscado con tab', async () => {
        authAPI.logout.mockResolvedValue(undefined);
        // `%09` llega decodificado como TAB desde el querystring.
        renderLogout('?redirect_uri=/%09/evil.org');

        expect(await screen.findByText('pantalla de login')).toBeInTheDocument();
        expect(assignedHref).toBeNull();
    });

    it('ante un fallo de red muestra error y no navega', async () => {
        authAPI.logout.mockRejectedValue(new Error('network error'));
        renderLogout('?redirect_uri=/admin/users');

        expect(await screen.findByText('No se pudo cerrar la sesión')).toBeInTheDocument();
        expect(screen.queryByText('usuarios')).not.toBeInTheDocument();
        expect(assignedHref).toBeNull();
    });

    it('permite reintentar y navega cuando el segundo intento funciona', async () => {
        authAPI.logout
            .mockRejectedValueOnce(new Error('network error'))
            .mockResolvedValueOnce(undefined);
        renderLogout('?redirect_uri=/admin/users');

        await screen.findByText('No se pudo cerrar la sesión');
        await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

        expect(await screen.findByText('usuarios')).toBeInTheDocument();
        expect(authAPI.logout).toHaveBeenCalledTimes(2);
    });

    it('sin cuenta activa no llama al backend y va al destino', async () => {
        useSession.mockReturnValue({ loading: false, active: null });
        renderLogout('?redirect_uri=/admin/users');

        expect(await screen.findByText('usuarios')).toBeInTheDocument();
        expect(authAPI.logout).not.toHaveBeenCalled();
    });

    // Un segundo POST corre sobre una sesión ya cerrada y su resultado puede contradecir
    // al del primero: error falso encima de un logout exitoso.
    it('con doble montaje de StrictMode llama al backend una sola vez', async () => {
        authAPI.logout.mockResolvedValue(undefined);
        renderLogoutStrict('?redirect_uri=/admin/users');

        expect(await screen.findByText('usuarios')).toBeInTheDocument();
        expect(authAPI.logout).toHaveBeenCalledTimes(1);
    });

    it('el reintento dispara exactamente un intento más, aun con StrictMode', async () => {
        authAPI.logout
            .mockRejectedValueOnce(new Error('network error'))
            .mockResolvedValueOnce(undefined);
        renderLogoutStrict('?redirect_uri=/admin/users');

        await screen.findByText('No se pudo cerrar la sesión');
        await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

        expect(await screen.findByText('usuarios')).toBeInTheDocument();
        expect(authAPI.logout).toHaveBeenCalledTimes(2);
    });

    it('espera a que la sesión cargue antes de cerrar', async () => {
        useSession.mockReturnValue({ loading: true, active: null });
        renderLogout('?redirect_uri=/admin/users');

        await waitFor(() => expect(authAPI.logout).not.toHaveBeenCalled());
        expect(screen.getByText('Cerrando sesión…')).toBeInTheDocument();
    });
});
