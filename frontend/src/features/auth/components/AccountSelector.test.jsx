import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AccountSelector from './AccountSelector';

const accounts = [
    { sub: 'u-1', name: 'Cuenta principal', email: 'principal@iieg.gob.mx', expired: false },
    { sub: 'u-2', name: 'Cuenta alterna', email: 'alterna@iieg.gob.mx', expired: false },
];

vi.mock('@/api/session', () => ({
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

describe('AccountSelector', () => {
    it('permite elegir otra cuenta con Tab y Enter', async () => {
        const user = userEvent.setup();
        const onSelect = vi.fn();
        render(<AccountSelector onSelect={onSelect} />);

        const toggle = screen.getByRole('button', { name: 'Ver otras cuentas' });
        await user.click(toggle);
        await user.tab();

        const alternate = screen.getByRole('button', { name: /Cuenta alterna/ });
        expect(alternate).toHaveFocus();
        await user.keyboard('{Enter}');
        await user.click(screen.getByRole('button', { name: 'Continuar' }));

        expect(sessionAPI.setActive).toHaveBeenCalledWith('u-2');
        expect(onSelect).toHaveBeenCalledWith(accounts[1]);
    });
});
