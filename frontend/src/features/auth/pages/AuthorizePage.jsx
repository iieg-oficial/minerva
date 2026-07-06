import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { App as AntApp, Button, Flex, Result, Spin, Typography } from 'antd';
import { authorizeUrl } from '@/api/auth';

const { Text } = Typography;

// Modo popup (opt-in con response_mode=web_message): en vez de navegar la ventana
// al consumidor, devolvemos el resultado al opener vía postMessage y cerramos el
// popup. El targetOrigin se fija al origen del redirect_uri (ya validado contra el
// allowlist del backend antes de emitir el code), nunca "*".
function postToOpener(redirectUri, payload) {
    let targetOrigin;
    try {
        targetOrigin = new URL(redirectUri).origin;
    } catch {
        return false;
    }
    if (!window.opener) return false;
    window.opener.postMessage({ source: 'minerva', ...payload }, targetOrigin);
    return true;
}

// Página de autorización OAuth2: un sistema consumidor (p. ej. Godín) redirige
// aquí con client_id/redirect_uri/state. Si hay sesión, pedimos a Minerva el
// `code` y devolvemos el navegador al consumidor; si no, mandamos a login y
// regresamos aquí al autenticar (parámetro `next`).
export default function AuthorizePage() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const { message } = AntApp.useApp();
    const ran = useRef(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (ran.current) return;
        ran.current = true;

        const clientId = params.get('client_id');
        const redirectUri = params.get('redirect_uri');
        const state = params.get('state');
        const scope = params.get('scope') || 'openid profile email';
        const codeChallenge = params.get('code_challenge');
        const codeChallengeMethod = params.get('code_challenge_method');
        // Popup opt-in: el consumidor abre /authorize con response_mode=web_message.
        const popupMode = params.get('response_mode') === 'web_message' && !!window.opener;

        if (!clientId || !redirectUri || !state) {
            setError('Solicitud de autorización inválida: faltan parámetros (client_id, redirect_uri, state).');
            return;
        }

        const token = localStorage.getItem('access_token');
        const resumePath = `/authorize?${params.toString()}`;
        if (!token) {
            navigate(`/login?next=${encodeURIComponent(resumePath)}`, { replace: true });
            return;
        }

        authorizeUrl({ clientId, redirectUri, state, scope, codeChallenge, codeChallengeMethod })
            .then((redirectUrl) => {
                // En modo popup, si la URL es el resultado final del consumidor
                // (empieza con su redirect_uri), lo devolvemos por postMessage en
                // vez de navegar; si es una URL de re-login de Minerva, navegamos.
                if (popupMode && redirectUrl.startsWith(redirectUri)) {
                    const result = new URL(redirectUrl).searchParams;
                    postToOpener(redirectUri, {
                        code: result.get('code'),
                        state: result.get('state'),
                        error: result.get('error'),
                    });
                    window.close();
                    return;
                }
                window.location.href = redirectUrl;
            })
            .catch((err) => {
                if (err.response?.status === 401) {
                    navigate(`/login?next=${encodeURIComponent(resumePath)}`, { replace: true });
                    return;
                }
                const detail = err.response?.data?.detail || 'No se pudo completar la autorización.';
                // En popup, avisamos al opener para que no quede colgado esperando.
                if (popupMode) {
                    postToOpener(redirectUri, { state, error: 'server_error' });
                }
                message.error(detail);
                setError(detail);
            });
    }, [params, navigate, message]);

    if (error) {
        return (
            <Result
                status="error"
                title="Autorización fallida"
                subTitle={error}
                extra={
                    <Button type="primary" onClick={() => navigate('/login', { replace: true })}>
                        Volver al inicio de sesión
                    </Button>
                }
            />
        );
    }

    return (
        <Flex vertical align="center" justify="center" gap={16} style={{ minHeight: '100dvh' }}>
            <Spin size="large" />
            <Text>Autorizando acceso…</Text>
        </Flex>
    );
}
