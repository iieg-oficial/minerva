import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AccountSelector from './AccountSelector';

const accounts = [
    { sub: 'u-1', name: 'Cuenta principal', email: 'principal@iieg.gob.mx', expired: false },
    { sub: 'u-2', name: 'Cuenta alterna', email: 'alterna@iieg.gob.mx', expired: false },
];

vi.mock('@/api/session', () => ({
    fetchSession: vi.fn(),
    getActive: vi.fn(),
    getSessions: vi.fn(),
    isExpired: vi.fn(),
    removeSession: vi.fn(),
    setActive: vi.fn(),
}));

const sessionAPI = await import('@/api/session');

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
    vi.clearAllMocks();
    sessionAPI.getActive.mockReturnValue(accounts[0]);
    sessionAPI.getSessions.mockReturnValue(accounts);
    sessionAPI.isExpired.mockReturnValue(false);
    sessionAPI.setActive.mockResolvedValue(undefined);
});

async function tabularHasta(user, elemento) {
    for (let i = 0; i < 8 && document.activeElement !== elemento; i++) {
        await user.tab();
    }
}

describe('AccountSelector', () => {
    it('permite elegir otra cuenta con Tab y Enter', async () => {
        const user = userEvent.setup();
        const onSelect = vi.fn();
        render(<AccountSelector onSelect={onSelect} />);

        const alterna = screen.getByRole('button', { name: /Cuenta alterna/ });
        await tabularHasta(user, alterna);

        expect(alterna).toHaveFocus();
        await user.keyboard('{Enter}');

        await waitFor(() => expect(onSelect).toHaveBeenCalledWith(accounts[1]));
        expect(sessionAPI.setActive).toHaveBeenCalledWith('u-2');
    });

    it('pide la contraseña en vez de entrar cuando el consumidor exige re-autenticación', async () => {
        const user = userEvent.setup();
        const onSelect = vi.fn();
        render(<AccountSelector onSelect={onSelect} exigeContrasena />);

        await user.click(screen.getByRole('button', { name: /Cuenta principal/ }));

        expect(await screen.findByPlaceholderText('Contraseña')).toBeInTheDocument();
        expect(onSelect).not.toHaveBeenCalled();
        expect(sessionAPI.setActive).not.toHaveBeenCalled();
    });

    it('pide la contraseña si el backend ya no reconoce viva la sesión de la cuenta', async () => {
        const user = userEvent.setup();
        const onSelect = vi.fn();
        sessionAPI.setActive.mockRejectedValue({ response: { status: 409 } });
        render(<AccountSelector onSelect={onSelect} />);

        await user.click(screen.getByRole('button', { name: /Cuenta alterna/ }));

        expect(await screen.findByPlaceholderText('Contraseña')).toBeInTheDocument();
        expect(sessionAPI.fetchSession).toHaveBeenCalled();
        expect(onSelect).not.toHaveBeenCalled();
    });
});
