import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { App as AntApp } from 'antd';
import LoginPage from './LoginPage';

vi.mock('@/api/auth', () => ({ login: vi.fn() }));
vi.mock('@/api/public', () => ({ getAppBranding: vi.fn() }));
vi.mock('@features/auth/SessionContext', () => ({ useSession: vi.fn() }));
vi.mock('../components/AccountSelector', () => ({ default: () => <div>Selector de cuentas</div> }));
vi.mock('../components/AuthShell', () => ({
    default: ({ children }) => <>{children}</>,
    BRAND: { purple: '#5C2472', orange: '#FF8300' },
}));

const authAPI = await import('@/api/auth');
const { useSession } = await import('@features/auth/SessionContext');

// antd las necesita en jsdom y no existen ahí (mismo shim que auth-smoke.test.jsx).
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

beforeEach(() => {
    useSession.mockReturnValue({ accounts: [], loading: false, refresh: vi.fn() });
});

afterEach(() => {
    vi.clearAllMocks();
});

function ActivarProbe() {
    const location = useLocation();
    return (
        <div>
            activar [{location.hash}] {location.state?.credentialToken} {location.state?.email}
        </div>
    );
}

function renderLogin() {
    return render(
        <MemoryRouter initialEntries={['/login']}>
            <AntApp>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/activar" element={<ActivarProbe />} />
                    <Route path="/admin" element={<div>panel</div>} />
                </Routes>
            </AntApp>
        </MemoryRouter>
    );
}

describe('LoginPage — cambio obligatorio de contraseña', () => {
    it('lleva a /activar con el token de un solo uso, sin abrir sesión', async () => {
        authAPI.login.mockRejectedValue({
            response: {
                status: 403,
                data: {
                    detail: 'Debes cambiar tu contraseña antes de continuar',
                    code: 'password_change_required',
                    credential_token: 'tok-1',
                },
            },
        });
        renderLogin();

        const email = screen.getByLabelText(/Correo electrónico/);
        await userEvent.clear(email);
        await userEvent.type(email, 'persona@iieg.gob.mx');
        await userEvent.type(screen.getByLabelText(/^Contraseña/), 'temporal123');
        await userEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }));

        expect(
            // El token viaja en el state, nunca en la URL (el fragmento queda vacío).
            await screen.findByText('activar [] tok-1 persona@iieg.gob.mx')
        ).toBeInTheDocument();
        expect(screen.queryByText('panel')).not.toBeInTheDocument();
    });
});
