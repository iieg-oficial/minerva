import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Flex, Spin, Typography } from 'antd';
import * as authAPI from '@/api/auth';
import { useSession } from '@features/auth/SessionContext';

const { Text } = Typography;

// Cierra la sesión de Minerva (single logout). Un sistema consumidor (p. ej.
// Godín) redirige aquí para que, además de cerrar su propia sesión, termine la
// de Minerva y no quede una cuenta activa que re-autorice en silencio.
export default function LogoutPage() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const { loading, active } = useSession();
    const ran = useRef(false);

    useEffect(() => {
        // Espera a que el contexto cargue (así el token CSRF ya está disponible para
        // la llamada de logout).
        if (loading || ran.current) return;
        ran.current = true;

        const redirect = params.get('redirect_uri');
        const finish = () => {
            // Solo URLs absolutas http(s) como destino externo; si no, al login local.
            if (redirect && /^https?:\/\//i.test(redirect)) {
                window.location.href = redirect;
            } else {
                navigate('/login', { replace: true });
            }
        };

        // logout() es suave (cierra la cuenta activa; las demás quedan para reingresar).
        // Sin cuenta activa no hay nada que cerrar: solo redirige.
        if (active) {
            authAPI.logout().finally(finish);
        } else {
            finish();
        }
    }, [loading, active, params, navigate]);

    return (
        <Flex vertical align="center" justify="center" gap={16} style={{ minHeight: '100dvh' }}>
            <Spin size="large" />
            <Text>Cerrando sesión…</Text>
        </Flex>
    );
}
