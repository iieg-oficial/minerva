import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Flex, Spin, Typography } from 'antd';
import * as authAPI from '@/api/auth';

const { Text } = Typography;

// Cierra la sesión de Minerva (single logout). Un sistema consumidor (p. ej.
// Godín) redirige aquí para que, además de cerrar su propia sesión, termine la
// de Minerva y no quede una sesión que re-autorice en silencio.
export default function LogoutPage() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const ran = useRef(false);

    useEffect(() => {
        if (ran.current) return;
        ran.current = true;

        const redirect = params.get('redirect_uri');
        authAPI.logout().finally(() => {
            // Solo URLs absolutas http(s) como destino externo; si no, al login local.
            if (redirect && /^https?:\/\//i.test(redirect)) {
                window.location.href = redirect;
            } else {
                navigate('/login', { replace: true });
            }
        });
    }, [params, navigate]);

    return (
        <Flex vertical align="center" justify="center" gap={16} style={{ minHeight: '100dvh' }}>
            <Spin size="large" />
            <Text>Cerrando sesión…</Text>
        </Flex>
    );
}
