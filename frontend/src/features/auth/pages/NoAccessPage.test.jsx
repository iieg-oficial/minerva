import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NoAccessPage from './NoAccessPage';

vi.mock('@/api/auth', () => ({ getMyProfile: vi.fn(), logout: vi.fn() }));

const authAPI = await import('@/api/auth');

window.matchMedia = vi.fn(() => ({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
}));

afterEach(() => {
    vi.clearAllMocks();
});

function renderPage() {
    return render(
        <MemoryRouter>
            <NoAccessPage />
        </MemoryRouter>
    );
}

describe('NoAccessPage', () => {
    it('ofrece ir a las aplicaciones que la persona usa', async () => {
        authAPI.getMyProfile.mockResolvedValue({
            applications: [
                { id: 'app-1', name: 'Mariachi', homepage_url: 'https://mariachi.example/' },
            ],
        });
        renderPage();

        const link = await screen.findByRole('link', { name: 'Ir a Mariachi' });
        expect(link).toHaveAttribute('href', 'https://mariachi.example/');
        expect(screen.getByText('Tu cuenta está lista')).toBeInTheDocument();
    });

    it('sin aplicaciones conserva el aviso de acceso', async () => {
        authAPI.getMyProfile.mockResolvedValue({ applications: [] });
        renderPage();

        expect(await screen.findByText('Sin acceso al panel')).toBeInTheDocument();
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });
});
