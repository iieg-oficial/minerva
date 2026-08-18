import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { App as AntApp, Button, Flex, Result, Spin, Typography } from 'antd';
import { authorizeUrl } from '@/api/auth';
import { isExpired, setActive } from '@/api/session';
import { useSession } from '@features/auth/SessionContext';
import { getAppBranding } from '@/api/public';
import AccountSelector from '../components/AccountSelector';
import AuthShell from '../components/AuthShell';

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
// aquí con client_id/redirect_uri/state. Comportamiento según `prompt` (OIDC):
//  - select_account → muestra el selector de cuentas (multi-sesión de esta SPA).
//  - login          → fuerza login fresco (formulario) aunque haya sesión.
//  - (sin prompt)   → SSO silencioso con la cuenta activa; si no hay, a login.
export default function AuthorizePage() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const { message } = AntApp.useApp();
    const { loading: sessionLoading, active, accounts } = useSession();
    const ran = useRef(false);
    const [error, setError] = useState(null);
    const [selecting, setSelecting] = useState(false);
    const [branding, setBranding] = useState(null);

    const clientId = params.get('client_id');
    const redirectUri = params.get('redirect_uri');
    const state = params.get('state');
    const scope = params.get('scope') || 'openid profile email';
    const codeChallenge = params.get('code_challenge');
    const codeChallengeMethod = params.get('code_challenge_method');
    const nonce = params.get('nonce');
    const prompt = params.get('prompt');
    const maxAgeRaw = params.get('max_age');
    const maxAge = maxAgeRaw !== null && /^\d+$/.test(maxAgeRaw) ? Number(maxAgeRaw) : undefined;
    const popupMode = params.get('response_mode') === 'web_message' && !!window.opener;
    const resumePath = `/authorize?${params.toString()}`;
    const loginNext = (extra = '') => `/login?next=${encodeURIComponent(resumePath)}${extra}`;

    // Pide a Minerva el `code` con la cuenta activa (el interceptor usa su Bearer)
    // y regresa al consumidor. `prompt=select_account`/`login` ya se resolvieron en
    // la SPA, así que NO se reenvían (reenviarlos re-dispararía el prompt); `none`
    // sí se pasa para que el backend devuelva login_required si corresponde.
    const proceed = useCallback(() => {
        authorizeUrl({
            clientId,
            redirectUri,
            state,
            scope,
            codeChallenge,
            codeChallengeMethod,
            nonce,
            prompt: prompt === 'none' ? 'none' : undefined,
            maxAge,
        })
            .then((redirectUrl) => {
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
                    navigate(loginNext(), { replace: true });
                    return;
                }
                const detail =
                    err.response?.data?.detail || 'No se pudo completar la autorización.';
                if (popupMode) postToOpener(redirectUri, { state, error: 'server_error' });
                message.error(detail);
                setError(detail);
            });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [
        clientId,
        redirectUri,
        state,
        scope,
        codeChallenge,
        codeChallengeMethod,
        nonce,
        prompt,
        maxAge,
        popupMode,
    ]);

    useEffect(() => {
        // Espera a que el contexto resuelva el estado de sesión (cookie) antes de
        // decidir el flujo: si no, leería cuentas vacías y saltaría a login por error.
        if (sessionLoading) return;
        if (ran.current) return;
        ran.current = true;

        if (!clientId || !redirectUri || !state) {
            setError(
                'Solicitud de autorización inválida: faltan parámetros (client_id, redirect_uri, state).'
            );
            return;
        }

        if (prompt === 'login') {
            // Re-autenticación forzada. Si la cuenta ya está en el navegador no hace
            // falta el formulario completo: `reauth=1` deja el selector y pide sólo la
            // contraseña sobre su tarjeta. Sin cuentas guardadas, el propio selector
            // cae al formulario. Quitamos `prompt` del resume para que, tras el login
            // fresco, esta rama no se vuelva a disparar (evita el loop
            // formulario→authorize→formulario).
            const resumeParams = new URLSearchParams(params);
            resumeParams.delete('prompt');
            navigate(
                `/login?next=${encodeURIComponent(`/authorize?${resumeParams.toString()}`)}&reauth=1`,
                {
                    replace: true,
                }
            );
            return;
        }

        if (prompt === 'select_account') {
            // Si la única cuenta guardada es la activa y sigue vigente (login recién hecho),
            // no tiene sentido pedir un "Continuar" extra: procede directo.
            const onlyFreshAccount =
                accounts.length === 1 && active?.sub === accounts[0].sub && !isExpired(active);
            if (onlyFreshAccount) {
                proceed();
                return;
            }
            if (clientId)
                getAppBranding(clientId)
                    .then(setBranding)
                    .catch(() => {});
            setSelecting(true);
            return;
        }

        // SSO silencioso: si hay cuenta activa, seguimos; si no, a login.
        if (!active) {
            navigate(loginNext(), { replace: true });
            return;
        }
        proceed();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [clientId, redirectUri, state, prompt, sessionLoading]);

    const onSelect = async (session) => {
        await setActive(session.sub); // fija la cuenta activa en el backend antes de continuar
        setSelecting(false);
        proceed();
    };
    const onReauth = (session) =>
        navigate(loginNext(`&add=1&email=${encodeURIComponent(session.email)}`), { replace: true });
    const onAddAccount = () => navigate(loginNext('&add=1'), { replace: true });

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

    if (selecting) {
        return (
            <AuthShell
                appName={branding?.display_name || branding?.name}
                brandColor={branding?.brand_color}
                logoUrl={branding?.logo_url}
            >
                <AccountSelector
                    appName={branding?.display_name || branding?.name}
                    brandColor={branding?.brand_color}
                    onSelect={onSelect}
                    onReauth={onReauth}
                    onAddAccount={onAddAccount}
                />
            </AuthShell>
        );
    }

    return (
        <Flex vertical align="center" justify="center" gap={16} style={{ minHeight: '100dvh' }}>
            <Spin size="large" />
            <Text>Autorizando acceso…</Text>
        </Flex>
    );
}
