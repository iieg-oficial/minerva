import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { fetchSession } from '@/api/session';

// Contexto de sesión del panel: hace UN fetch de `/auth/session` al montar y expone
// el estado multi-cuenta (fuente de verdad en el backend). `ProtectedRoute` y las
// páginas lo consumen en vez de leer tokens del navegador.
// ponytail: un provider con un fetch al montar; sin state manager global.
const SessionContext = createContext(null);

export function SessionProvider({ children }) {
    const [state, setState] = useState({ loading: true, active: null, accounts: [] });

    const refresh = useCallback(async () => {
        const s = await fetchSession();
        setState({ loading: false, active: s.active, accounts: s.accounts });
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return (
        <SessionContext.Provider value={{ ...state, isAdmin: !!state.active?.is_admin, refresh }}>
            {children}
        </SessionContext.Provider>
    );
}

export function useSession() {
    return useContext(SessionContext);
}
