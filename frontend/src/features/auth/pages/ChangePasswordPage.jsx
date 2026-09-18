import { useState } from 'react';
import { App as AntApp, Button, Flex, Form, Input, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import * as authAPI from '@/api/auth';
import { useSession } from '@features/auth/SessionContext';
import AuthShell, { BRAND } from '../components/AuthShell';
import NewPasswordFields from '../components/NewPasswordFields';

const { Title, Text } = Typography;
const FONT = '"Garet", sans-serif';

// Cambio de contraseña propio. Solo exige sesión (no rol de administrador): cualquier
// persona con cuenta en Minerva debe poder cambiar la suya.
export default function ChangePasswordPage() {
    const [saving, setSaving] = useState(false);
    const [form] = Form.useForm();
    const navigate = useNavigate();
    const { message } = AntApp.useApp();
    const { active, isAdmin, refresh } = useSession();

    const onFinish = async ({ current_password, password }) => {
        setSaving(true);
        try {
            await authAPI.changePassword(current_password, password);
            message.success('Contraseña actualizada. Inicia sesión con la nueva.');
            // El backend cerró todas las sesiones de esta cuenta: se vuelve a entrar.
            navigate(`/login?add=1&email=${encodeURIComponent(active?.email || '')}`, {
                replace: true,
            });
            await refresh();
        } catch (err) {
            const status = err.response?.status;
            const detail = err.response?.data?.detail;
            if (status === 400) {
                form.setFields([
                    {
                        name: 'current_password',
                        errors: [
                            typeof detail === 'string'
                                ? detail
                                : 'La contraseña actual no es correcta',
                        ],
                    },
                ]);
            } else if (status === 429) {
                message.error(
                    detail || 'Demasiados intentos. Espera unos minutos e intenta de nuevo.'
                );
            } else {
                message.error(
                    typeof detail === 'string' ? detail : 'No se pudo cambiar la contraseña.'
                );
            }
        } finally {
            setSaving(false);
        }
    };

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
                    Cambiar contraseña
                </Title>
                <Text style={{ fontSize: 12, fontFamily: FONT }}>
                    Cuenta: {active?.email}. Al guardar se cerrarán todas tus sesiones abiertas.
                </Text>
            </Flex>

            <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
                <Form.Item
                    label="Contraseña actual"
                    name="current_password"
                    rules={[{ required: true, message: 'Ingresa tu contraseña actual' }]}
                >
                    <Input.Password autoComplete="current-password" />
                </Form.Item>
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
                <Button
                    type="link"
                    block
                    onClick={() => navigate(isAdmin ? '/admin' : '/no-access')}
                    style={{ marginTop: 8, color: BRAND.purple, fontFamily: FONT }}
                >
                    Volver
                </Button>
            </Form>
        </AuthShell>
    );
}
