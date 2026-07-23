import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Flex, Result, Spin, Typography } from 'antd';
import * as authAPI from '@/api/auth';
import { useSession } from '@features/auth/SessionContext';

const { Text } = Typography;

// Solo destinos internos: se normaliza con la API URL (no con chequeos de caracteres,
// que un tab o un backslash evaden) y se exige que el origen coincida. Aceptar destinos
// externos requiere registrar `post_logout_redirect_uris`, que Minerva aún no implementa.
export function safePath(value) {
    if (!value) return '/login';
    try {
        const url = new URL(value, window.location.origin);
        if (url.origin !== window.location.origin) return '/login';
        return url.pathname + url.search + url.hash;
    } catch {
        return '/login';
    }
}

// Cierra la sesión de Minerva (single logout). Un sistema consumidor (p. ej.
// Godín) redirige aquí para que, además de cerrar su propia sesión, termine la
// de Minerva y no quede una cuenta activa que re-autorice en silencio.
export default function LogoutPage() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const { loading, active } = useSession();
    const [failed, setFailed] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const firedAttempt = useRef(-1);

    const redirect = params.get('redirect_uri');

    const finish = useCallback(() => {
        navigate(safePath(redirect), { replace: true });
    }, [navigate, redirect]);

    useEffect(() => {
        // Espera a que el contexto cargue (así el token CSRF ya está disponible para
        // la llamada de logout).
        if (loading) return;

        // logout() es suave (cierra la cuenta activa; las demás quedan para reingresar).
        // Sin cuenta activa no hay nada que cerrar: solo redirige.
        if (!active) {
            finish();
            return;
        }

        // Un intento = un POST: el ref sobrevive al doble montaje de <StrictMode> y a que
        // `active` cambie de identidad. Un segundo POST podría contradecir al primero.
        if (firedAttempt.current === attempt) return;
        firedAttempt.current = attempt;

        setFailed(false);
        // Con cookie HttpOnly, JS no puede invalidar la sesión: si el backend no confirma,
        // la sesión sigue viva. Solo se navega en la resolución exitosa.
        authAPI
            .logout()
            .then(finish)
            .catch(() => setFailed(true));
    }, [loading, active, finish, attempt]);

    if (failed) {
        return (
            <Flex align="center" justify="center" style={{ minHeight: '100dvh' }}>
                <Result
                    status="error"
                    title="No se pudo cerrar la sesión"
                    subTitle="Tu sesión sigue activa. Revisa tu conexión e intenta de nuevo."
                    extra={
                        <Button type="primary" onClick={() => setAttempt((n) => n + 1)}>
                            Reintentar
                        </Button>
                    }
                />
            </Flex>
        );
    }

    return (
        <Flex vertical align="center" justify="center" gap={16} style={{ minHeight: '100dvh' }}>
            <Spin size="large" />
            <Text>Cerrando sesión…</Text>
        </Flex>
    );
}
