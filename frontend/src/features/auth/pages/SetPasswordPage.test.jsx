import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom';
import { App as AntApp } from 'antd';
import SetPasswordPage from './SetPasswordPage';

vi.mock('@/api/credentials', () => ({ inspectCredential: vi.fn(), setCredential: vi.fn() }));
vi.mock('../components/AuthShell', () => ({
    default: ({ children }) => <>{children}</>,
    BRAND: { purple: '#5C2472' },
}));

const credentialsAPI = await import('@/api/credentials');

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

const INVITE = { purpose: 'invite', email: 'p***@iieg.gob.mx', expires_at: '2026-09-17T00:00:00Z' };

afterEach(() => {
    vi.clearAllMocks();
});

function LoginProbe() {
    const [params] = useSearchParams();
    return <div>pantalla de login: {params.get('email')}</div>;
}

function renderPage(entry) {
    return render(
        <MemoryRouter initialEntries={[entry]}>
            <AntApp>
                <Routes>
                    <Route path="/activar" element={<SetPasswordPage />} />
                    <Route path="/login" element={<LoginProbe />} />
                </Routes>
            </AntApp>
        </MemoryRouter>
    );
}

async function fillAndSubmit(password, confirm = password) {
    await userEvent.type(screen.getByLabelText('Contraseña nueva'), password);
    await userEvent.type(screen.getByLabelText('Confirma la contraseña nueva'), confirm);
    await userEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));
}

describe('SetPasswordPage', () => {
    it('toma el token del state cuando viene del login', async () => {
        credentialsAPI.inspectCredential.mockResolvedValue({ ...INVITE, purpose: 'forced_change' });
        renderPage({ pathname: '/activar', state: { credentialToken: 'tok-1' } });

        expect(await screen.findByText('Cambia tu contraseña')).toBeInTheDocument();
        expect(credentialsAPI.inspectCredential).toHaveBeenCalledWith('tok-1');
    });

    it('lee el token del fragmento y muestra para qué es el enlace', async () => {
        credentialsAPI.inspectCredential.mockResolvedValue(INVITE);
        renderPage('/activar#token=abc');

        expect(await screen.findByText('Activa tu cuenta')).toBeInTheDocument();
        expect(credentialsAPI.inspectCredential).toHaveBeenCalledWith('abc');
    });

    it('fija la contraseña y manda al login prellenado', async () => {
        credentialsAPI.inspectCredential.mockResolvedValue({ ...INVITE, purpose: 'forced_change' });
        credentialsAPI.setCredential.mockResolvedValue({});
        renderPage({
            pathname: '/activar',
            hash: '#token=abc',
            state: { email: 'persona@iieg.gob.mx' },
        });

        await screen.findByText('Cambia tu contraseña');
        await fillAndSubmit('nueva-clave-123');

        expect(
            await screen.findByText('pantalla de login: persona@iieg.gob.mx')
        ).toBeInTheDocument();
        expect(credentialsAPI.setCredential).toHaveBeenCalledWith('abc', 'nueva-clave-123');
    });

    it('no envía si la confirmación no coincide', async () => {
        credentialsAPI.inspectCredential.mockResolvedValue(INVITE);
        renderPage('/activar#token=abc');

        await screen.findByText('Activa tu cuenta');
        await fillAndSubmit('nueva-clave-123', 'otra-clave-456');

        expect(await screen.findByText('Las contraseñas no coinciden')).toBeInTheDocument();
        expect(credentialsAPI.setCredential).not.toHaveBeenCalled();
    });

    it('muestra el motivo cuando el enlace no sirve', async () => {
        credentialsAPI.inspectCredential.mockRejectedValue({
            response: {
                status: 400,
                data: { detail: 'El enlace no es válido, ya se usó o expiró.' },
            },
        });
        renderPage('/activar#token=viejo');

        expect(
            await screen.findByText('El enlace no es válido, ya se usó o expiró.')
        ).toBeInTheDocument();
        expect(screen.queryByLabelText('Contraseña nueva')).not.toBeInTheDocument();
    });

    it('sin token en el fragmento no llama al backend', async () => {
        renderPage('/activar');

        expect(await screen.findByText(/El enlace está incompleto/)).toBeInTheDocument();
        expect(credentialsAPI.inspectCredential).not.toHaveBeenCalled();
    });
});
