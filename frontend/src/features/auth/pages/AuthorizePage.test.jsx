import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom';
import { App as AntApp } from 'antd';
import AuthorizePage from './AuthorizePage';

vi.mock('@/api/auth', () => ({ authorizeUrl: vi.fn() }));
vi.mock('@/api/session', () => ({ isExpired: vi.fn(() => false), setActive: vi.fn() }));
vi.mock('@features/auth/SessionContext', () => ({ useSession: vi.fn() }));

const authAPI = await import('@/api/auth');
const { useSession } = await import('@features/auth/SessionContext');

beforeEach(() => {
    useSession.mockReturnValue({
        loading: false,
        active: { sub: 'u-1', email: 'user@iieg.gob.mx' },
        accounts: [{ sub: 'u-1', email: 'user@iieg.gob.mx' }],
    });
    vi.spyOn(window, 'location', 'get').mockReturnValue({ href: '' });
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
});

const baseQuery =
    'client_id=godin&redirect_uri=https://godin.iieg.gob.mx/callback&response_type=code&state=xyz';

function LoginProbe() {
    const [params] = useSearchParams();
    return <div>pantalla de login: {params.get('next')}</div>;
}

function renderAuthorize(search) {
    return render(
        <MemoryRouter initialEntries={[`/authorize?${search}`]}>
            <AntApp>
                <Routes>
                    <Route path="/authorize" element={<AuthorizePage />} />
                    <Route path="/login" element={<LoginProbe />} />
                </Routes>
            </AntApp>
        </MemoryRouter>,
    );
}

describe('AuthorizePage — propagación de max_age', () => {
    it('reenvía max_age=0 al backend', async () => {
        authAPI.authorizeUrl.mockResolvedValue('https://godin.iieg.gob.mx/callback?code=abc');
        renderAuthorize(`${baseQuery}&max_age=0`);

        await vi.waitFor(() => expect(authAPI.authorizeUrl).toHaveBeenCalledTimes(1));
        expect(authAPI.authorizeUrl.mock.calls[0][0]).toMatchObject({ maxAge: 0 });
    });

    it('sin max_age conserva el comportamiento actual (no se manda la clave)', async () => {
        authAPI.authorizeUrl.mockResolvedValue('https://godin.iieg.gob.mx/callback?code=abc');
        renderAuthorize(baseQuery);

        await vi.waitFor(() => expect(authAPI.authorizeUrl).toHaveBeenCalledTimes(1));
        expect(authAPI.authorizeUrl.mock.calls[0][0].maxAge).toBeUndefined();
    });

    it('descarta max_age inválido (negativo o no numérico) en vez de reenviarlo', async () => {
        authAPI.authorizeUrl.mockResolvedValue('https://godin.iieg.gob.mx/callback?code=abc');
        renderAuthorize(`${baseQuery}&max_age=-1`);

        await vi.waitFor(() => expect(authAPI.authorizeUrl).toHaveBeenCalledTimes(1));
        expect(authAPI.authorizeUrl.mock.calls[0][0].maxAge).toBeUndefined();
    });

    it('preserva max_age al reanudar el login (SSO sin cuenta activa)', async () => {
        useSession.mockReturnValue({ loading: false, active: null, accounts: [] });
        renderAuthorize(`${baseQuery}&max_age=0`);

        const login = await screen.findByText(/pantalla de login/);
        expect(login.textContent).toContain('max_age=0');
        expect(authAPI.authorizeUrl).not.toHaveBeenCalled();
    });
});
