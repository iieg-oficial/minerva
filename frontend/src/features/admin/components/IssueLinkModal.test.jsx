import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App as AntApp } from 'antd';
import IssueLinkModal from './IssueLinkModal';

vi.mock('@/api/users', () => ({
    listCredentialDestinations: vi.fn(),
    createCredentialLink: vi.fn(),
}));

const usersAPI = await import('@/api/users');

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

const USER = { id: 'u-1', email: 'persona@iieg.gob.mx', status: 'active' };
const LINK = {
    url: 'https://minerva/activar#token=x',
    purpose: 'reset',
    expires_at: '2026-10-14T00:00:00Z',
};

afterEach(() => {
    vi.clearAllMocks();
});

function renderModal(onIssued = vi.fn()) {
    render(
        <AntApp>
            <IssueLinkModal user={USER} onClose={vi.fn()} onIssued={onIssued} />
        </AntApp>
    );
    return onIssued;
}

describe('IssueLinkModal', () => {
    it('preselecciona la primera aplicación de la persona y la manda como destino', async () => {
        usersAPI.listCredentialDestinations.mockResolvedValue([
            { id: 'app-1', name: 'Mariachi', homepage_url: 'https://mariachi.example/' },
        ]);
        usersAPI.createCredentialLink.mockResolvedValue(LINK);
        const onIssued = renderModal();

        expect(await screen.findByText('Mariachi')).toBeInTheDocument();
        await userEvent.click(screen.getByRole('button', { name: 'Generar' }));

        expect(usersAPI.createCredentialLink).toHaveBeenCalledWith('u-1', 'app-1');
        expect(onIssued).toHaveBeenCalledWith({ email: USER.email, ...LINK });
    });

    it('sin aplicaciones genera el enlace sin destino', async () => {
        usersAPI.listCredentialDestinations.mockResolvedValue([]);
        usersAPI.createCredentialLink.mockResolvedValue(LINK);
        renderModal();

        expect(await screen.findByText('Sin destino (login de Minerva)')).toBeInTheDocument();
        await userEvent.click(screen.getByRole('button', { name: 'Generar' }));

        expect(usersAPI.createCredentialLink).toHaveBeenCalledWith('u-1', null);
    });
});
