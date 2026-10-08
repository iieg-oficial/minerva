import { useEffect, useState } from 'react';
import { App as AntApp, Button, Flex, Form, Spin, Typography } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import * as credentialsAPI from '@/api/credentials';
import * as sessionAPI from '@/api/session';
import AuthShell, { BRAND } from '../components/AuthShell';
import NewPasswordFields from '../components/NewPasswordFields';

const { Title, Text } = Typography;
const FONT = '"Garet", sans-serif';

const COPY = {
    invite: {
        title: 'Activa tu cuenta',
        subtitle: 'Define la contraseña con la que vas a ingresar.',
    },
    reset: {
        title: 'Restablece tu contraseña',
        subtitle: 'Define una contraseña nueva para tu cuenta.',
    },
    forced_change: {
        title: 'Cambia tu contraseña',
        subtitle: 'Antes de continuar necesitas definir una contraseña propia.',
    },
};

// El token viaja en el fragmento (#token=...): el navegador no lo envía al servidor, así
// que no queda en logs de acceso ni en el Referer.
function tokenFromHash(hash) {
    return new URLSearchParams((hash || '').replace(/^#/, '')).get('token');
}

// Destino tras fijar la contraseña: el login, prellenado si venimos del login mismo
// (cambio obligatorio) y conservando el `next` de un flujo /authorize.
function loginUrl(state) {
    const params = new URLSearchParams();
    // Tras fijar la contraseña se manda siempre al formulario de login normal, no al
    // selector de cuentas: `add=1` fuerza el formulario aunque el contenedor tenga cuentas.
    params.set('add', '1');
    if (state?.email) params.set('email', state.email);
    if (state?.next) params.set('next', state.next);
    return `/login?${params.toString()}`;
}

export default function SetPasswordPage() {
    const location = useLocation();
    const navigate = useNavigate();
    const { message } = AntApp.useApp();
    // Del login llega por el state de la navegación; de un enlace, por el fragmento.
    const [token] = useState(() => location.state?.credentialToken || tokenFromHash(location.hash));
    const [info, setInfo] = useState(null);
    const [error, setError] = useState(
        token ? null : 'El enlace está incompleto. Ábrelo tal como lo recibiste.'
    );
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!token) return;
        // Ya leído, el token sale de la barra de direcciones y del historial.
        if (window.location.hash) {
            window.history.replaceState(
                window.history.state,
                '',
                window.location.pathname + window.location.search
            );
        }
        credentialsAPI
            .inspectCredential(token)
            .then(setInfo)
            .catch((err) => {
                const detail = err.response?.data?.detail;
                setError(typeof detail === 'string' ? detail : 'No se pudo validar el enlace.');
            });
    }, [token]);

    const onFinish = async ({ password }) => {
        setSaving(true);
        try {
            await credentialsAPI.setCredential(token, password);
            // Reset propio en el mismo navegador: el contenedor de panel conserva la cuenta
            // ya revocada y el selector ciclaría en el login; se destruye para llegar a un
            // login en blanco. Si no había sesión (invitación), ambos llamados fallan sin efecto.
            await sessionAPI.fetchSession().catch(() => {});
            await sessionAPI.logoutAll().catch(() => {});
            message.success('Contraseña guardada. Ya puedes iniciar sesión.');
            navigate(loginUrl(location.state), { replace: true });
        } catch (err) {
            const status = err.response?.status;
            const detail = err.response?.data?.detail;
            if (status === 400 && typeof detail === 'string') {
                setError(detail);
            } else if (status === 429) {
                message.error(
                    detail || 'Demasiados intentos. Espera unos minutos e intenta de nuevo.'
                );
            } else {
                message.error(
                    typeof detail === 'string' ? detail : 'No se pudo guardar la contraseña.'
                );
            }
        } finally {
            setSaving(false);
        }
    };

    const copy = info ? COPY[info.purpose] || COPY.reset : { title: 'Define tu contraseña' };

    return (
        <AuthShell>
            <Flex vertical gap={4} style={{ marginBottom: 24 }}>
                <Title
                    style={{
                        margin: 0,
                        color: BRAND.purple,
                        fontSize: 22,
                        fontWeight: 700,
                        fontFamily: FONT,
                    }}
                >
                    {copy.title}
                </Title>
                {info && !error && (
                    <Text style={{ fontSize: 12, fontFamily: FONT }}>
                        {copy.subtitle} Cuenta: {info.email}
                    </Text>
                )}
            </Flex>

            {error ? (
                <Flex vertical gap={16}>
                    <Text type="danger">{error}</Text>
                    <Button type="link" onClick={() => navigate('/login', { replace: true })}>
                        Ir al inicio de sesión
                    </Button>
                </Flex>
            ) : !info ? (
                <Flex align="center" justify="center" style={{ minHeight: 120 }}>
                    <Spin />
                </Flex>
            ) : (
                <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
                    <NewPasswordFields />
                    <Button
                        type="primary"
                        htmlType="submit"
                        loading={saving}
                        block
                        style={{
                            background: BRAND.purple,
                            borderColor: BRAND.purple,
                            height: 40,
                            borderRadius: 20,
                            fontWeight: 700,
                            fontFamily: FONT,
                        }}
                    >
                        Guardar contraseña
                    </Button>
                </Form>
            )}
        </AuthShell>
    );
}
