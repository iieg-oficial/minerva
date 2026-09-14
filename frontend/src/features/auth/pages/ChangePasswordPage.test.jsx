import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom';
import { App as AntApp } from 'antd';
import ChangePasswordPage from './ChangePasswordPage';

vi.mock('@/api/auth', () => ({ changePassword: vi.fn() }));
vi.mock('@features/auth/SessionContext', () => ({ useSession: vi.fn() }));
vi.mock('../components/AuthShell', () => ({
    default: ({ children }) => <>{children}</>,
    BRAND: { purple: '#5C2472' },
}));

const authAPI = await import('@/api/auth');
const { useSession } = await import('@features/auth/SessionContext');
const refresh = vi.fn();

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
    useSession.mockReturnValue({
        active: { sub: 'u-1', email: 'persona@iieg.gob.mx' },
        isAdmin: false,
        refresh,
    });
});

afterEach(() => {
    vi.clearAllMocks();
});

function LoginProbe() {
    const [params] = useSearchParams();
    return <div>pantalla de login: {params.get('email')}</div>;
}

function renderPage() {
    return render(
        <MemoryRouter initialEntries={['/cuenta/contrasena']}>
            <AntApp>
                <Routes>
                    <Route path="/cuenta/contrasena" element={<ChangePasswordPage />} />
                    <Route path="/login" element={<LoginProbe />} />
                    <Route path="/no-access" element={<div>sin acceso</div>} />
                </Routes>
            </AntApp>
        </MemoryRouter>
    );
}

async function fillAndSubmit(current) {
    await userEvent.type(screen.getByLabelText('Contraseña actual'), current);
    await userEvent.type(screen.getByLabelText('Contraseña nueva'), 'nueva-clave-123');
    await userEvent.type(screen.getByLabelText('Confirma la contraseña nueva'), 'nueva-clave-123');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));
}

describe('ChangePasswordPage', () => {
    it('cambia la contraseña y manda a iniciar sesión de nuevo', async () => {
        authAPI.changePassword.mockResolvedValue(undefined);
        renderPage();

        await fillAndSubmit('actual-123');

        expect(
            await screen.findByText('pantalla de login: persona@iieg.gob.mx')
        ).toBeInTheDocument();
        expect(authAPI.changePassword).toHaveBeenCalledWith('actual-123', 'nueva-clave-123');
        expect(refresh).toHaveBeenCalled();
    });

    it('marca la contraseña actual cuando no es correcta', async () => {
        authAPI.changePassword.mockRejectedValue({
            response: { status: 400, data: { detail: 'La contraseña actual no es correcta' } },
        });
        renderPage();

        await fillAndSubmit('equivocada-1');

        expect(await screen.findByText('La contraseña actual no es correcta')).toBeInTheDocument();
        expect(screen.queryByText(/pantalla de login/)).not.toBeInTheDocument();
    });

    it('Volver lleva a la página sin acceso a quien no es admin', async () => {
        renderPage();

        await userEvent.click(screen.getByRole('button', { name: 'Volver' }));

        expect(await screen.findByText('sin acceso')).toBeInTheDocument();
    });
});
