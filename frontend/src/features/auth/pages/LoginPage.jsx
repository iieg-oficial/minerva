import { useState, useEffect } from 'react';
import { App as AntApp, Form, Input, Button, Typography, Flex, Spin, theme } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import * as authAPI from '@/api/auth';
import { useSession } from '@features/auth/SessionContext';
import { getAppBranding } from '@/api/public';
import AuthShell, { BRAND } from '../components/AuthShell';
import AccountSelector from '../components/AccountSelector';

const { Title, Text } = Typography;
const { useToken } = theme;

// Solo permite rutas internas como destino post-login (evita open redirect).
function safeNext(next) {
    if (next && next.startsWith('/') && !next.startsWith('//')) {
        return next;
    }
    return '/admin';
}

// Extrae el client_id del destino post-login cuando viene de un flujo /authorize
// (p. ej. next="/authorize?client_id=...&redirect_uri=..."), para pedir el branding
// de la app solicitante. Devuelve null si no aplica.
function clientIdFromNext(next) {
    if (!next || !next.startsWith('/authorize')) return null;
    const query = next.slice(next.indexOf('?') + 1);
    return new URLSearchParams(query).get('client_id');
}

export default function LoginPage() {
    const [loading, setLoading] = useState(false);
    const [branding, setBranding] = useState(null);
    // Fuerza el formulario aunque haya cuentas guardadas (agregar/reingresar).
    const [forcedForm, setForcedForm] = useState(false);
    // Fuerza volver al selector aunque la URL traiga ?add=1.
    const [forceSelector, setForceSelector] = useState(false);
    const [reauthEmail, setReauthEmail] = useState(null);
    const [form] = Form.useForm();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { token } = useToken();
    const { message } = AntApp.useApp();
    const { accounts, active, loading: sessionLoading, refresh } = useSession();

    const next = safeNext(searchParams.get('next'));
    const clientId = clientIdFromNext(searchParams.get('next'));
    // Modo "agregar cuenta": el selector manda aquí con ?add=1 para forzar el
    // formulario aunque ya haya una sesión activa. `email` prellena la cuenta.
    const addMode = !!searchParams.get('add');
    // Re-autenticación (`prompt=login`): se queda en el selector y abre la tarjeta de
    // la cuenta en cuestión para pedir sólo la contraseña.
    const reauthMode = !!searchParams.get('reauth');
    const prefillEmail = reauthEmail || searchParams.get('email');

    // Sin cuentas guardadas → login_first siempre; con cuentas → selector
    // (login_again) salvo que se pida el formulario (agregar/reingresar/?add=1).
    // Ya no auto-saltamos al panel. `forceSelector` gana sobre ?add=1 de la URL.
    const hasSessions = accounts.length > 0;
    const showForm = !hasSessions || (!forceSelector && (addMode || forcedForm));

    useEffect(() => {
        // Personaliza la pantalla con el branding de la app solicitante. Si la app
        // no existe o no tiene branding, se conserva la identidad genérica de Minerva.
        if (!clientId) return;
        getAppBranding(clientId)
            .then(setBranding)
            .catch(() => setBranding(null));
    }, [clientId]);

    // `initialValues` solo se aplica al montar el Form: si el formulario ya estaba en
    // pantalla, el correo prellenado no llegaba al campo. Se sincroniza a mano.
    useEffect(() => {
        if (showForm && prefillEmail) form.setFieldsValue({ email: prefillEmail });
    }, [showForm, prefillEmail, form]);

    const appName = branding?.display_name || branding?.name;
    const brandColor = branding?.brand_color || BRAND.purple;

    const onFinish = async (values) => {
        setLoading(true);
        try {
            await authAPI.login(values.email, values.password);
            await refresh(); // refresca el contexto para que ProtectedRoute vea la sesión
            navigate(next, { replace: true });
        } catch (error) {
            const status = error.response?.status;
            const detail = error.response?.data?.detail;
            if (status === 403 && error.response?.data?.code === 'password_change_required') {
                // Credenciales correctas, pero debe fijar una contraseña propia antes de entrar.
                message.info('Debes cambiar tu contraseña antes de continuar.');
                // El token va en el state de la navegación, no en la URL: no queda en el historial.
                navigate('/activar', {
                    state: {
                        credentialToken: error.response.data.credential_token,
                        email: values.email,
                        next: searchParams.get('next'),
                    },
                });
                return;
            }
            if (status === 401 || status === 400) {
                form.setFields([
                    { name: 'password', errors: [detail || 'Usuario o contraseña incorrectos'] },
                ]);
            } else if (status === 429) {
                message.error(
                    detail || 'Demasiados intentos. Espera unos minutos e intenta de nuevo.'
                );
            } else {
                // Cualquier otro error (500, red caída, etc.): antes fallaba en silencio.
                message.error(detail || 'No se pudo iniciar sesión. Intenta de nuevo.');
            }
        } finally {
            setLoading(false);
        }
    };

    // Mientras se resuelve el estado de sesión, evita el parpadeo formulario↔selector.
    if (sessionLoading) {
        return (
            <AuthShell appName={appName} brandColor={brandColor} logoUrl={branding?.logo_url}>
                <Flex align="center" justify="center" style={{ minHeight: 200, width: '100%' }}>
                    <Spin size="large" />
                </Flex>
            </AuthShell>
        );
    }

    if (!showForm) {
        return (
            <AuthShell appName={appName} brandColor={brandColor} logoUrl={branding?.logo_url}>
                <AccountSelector
                    brandColor={brandColor}
                    onSelect={async () => {
                        await refresh();
                        navigate(next, { replace: true });
                    }}
                    abrirSub={reauthMode ? active?.sub || accounts[0]?.sub : null}
                    exigeContrasena={reauthMode}
                    onAccountsChanged={refresh}
                    onEntrar={async (email, password) => {
                        await authAPI.login(email, password);
                        await refresh();
                        navigate(next, { replace: true });
                    }}
                    onAddAccount={() => {
                        setReauthEmail(null);
                        setForceSelector(false);
                        setForcedForm(true);
                    }}
                />
            </AuthShell>
        );
    }

    return (
        <AuthShell appName={appName} brandColor={brandColor} logoUrl={branding?.logo_url}>
            <Flex vertical gap={4} style={{ marginBottom: token.marginXL }}>
                <Title
                    style={{
                        margin: 0,
                        color: BRAND.purple,
                        fontSize: 22,
                        fontWeight: 700,
                        lineHeight: 1.2,
                        fontFamily: '"Garet", sans-serif',
                    }}
                >
                    Hola
                </Title>
                <Text
                    style={{
                        fontSize: 12,
                        color: '#1f2937',
                        fontWeight: 400,
                        fontFamily: '"Garet", sans-serif',
                    }}
                >
                    Ingresa tus datos para iniciar sesión.
                </Text>
            </Flex>

            <Form
                form={form}
                name="login"
                onFinish={onFinish}
                layout="vertical"
                initialValues={
                    prefillEmail
                        ? { email: prefillEmail }
                        : import.meta.env.DEV
                          ? { email: 'admin@iieg.gob.mx' }
                          : {}
                }
                className="login-form-minerva"
                requiredMark={(label, info) => (
                    <>
                        {label}
                        {info.required && (
                            <span style={{ color: BRAND.orange, marginLeft: 4, fontWeight: 700 }}>
                                *
                            </span>
                        )}
                    </>
                )}
            >
                <Form.Item
                    label="Correo electrónico"
                    name="email"
                    normalize={(value) => (value ? value.replace(/\s/g, '').toLowerCase() : value)}
                    rules={[
                        { required: true, message: 'Ingrese su correo' },
                        { type: 'email', message: 'Ingrese un correo válido' },
                    ]}
                >
                    <Input placeholder="correo@iieg.gob.mx" autoComplete="username" />
                </Form.Item>

                <Form.Item
                    label="Contraseña"
                    name="password"
                    rules={[{ required: true, message: 'Ingrese su contraseña' }]}
                >
                    <Input.Password
                        placeholder="Contraseña"
                        autoComplete="current-password"
                        iconRender={(visible) => (
                            <img
                                src={`${import.meta.env.BASE_URL}${visible ? 'ico-show.svg' : 'ico-hidden.svg'}`}
                                alt={visible ? 'Mostrar' : 'Ocultar'}
                                style={{ width: 22, height: 22 }}
                            />
                        )}
                    />
                </Form.Item>

                <Form.Item style={{ marginTop: token.marginXL, marginBottom: 0 }}>
                    <Button
                        type="primary"
                        htmlType="submit"
                        loading={loading}
                        block
                        style={{
                            background: brandColor,
                            borderColor: brandColor,
                            height: 40,
                            borderRadius: 20,
                            fontWeight: 700,
                            fontSize: 14,
                            fontFamily: '"Garet", sans-serif',
                        }}
                    >
                        Iniciar sesión
                    </Button>
                </Form.Item>

                {hasSessions && (
                    <Button
                        type="link"
                        block
                        onClick={() => {
                            setForcedForm(false);
                            setReauthEmail(null);
                            setForceSelector(true);
                        }}
                        style={{
                            marginTop: 8,
                            color: brandColor,
                            fontFamily: '"Garet", sans-serif',
                        }}
                    >
                        Volver a mis cuentas
                    </Button>
                )}
            </Form>
        </AuthShell>
    );
}
