import { useState, useEffect } from 'react';
import { Form, Input, Button, Typography, Flex, Row, Col, theme } from 'antd';
import { useNavigate } from 'react-router';
import * as authAPI from '@/api/auth';

const { Title, Text, Link: TypoLink } = Typography;
const { useToken } = theme;

const BRAND = {
    numeralia: '#2e4372',
    purple: '#5C2472',
    orange: '#FF8300',
};

const PASSWORD_ICONS = {
    show: 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%238E8E8E" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'),
    hide: 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%238E8E8E" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'),
};

export default function LoginPage() {
    const [loading, setLoading] = useState(false);
    const [form] = Form.useForm();
    const navigate = useNavigate();
    const { token } = useToken();

    useEffect(() => {
        const stored = localStorage.getItem('access_token');
        if (stored) {
            navigate('/admin', { replace: true });
        }
    }, [navigate]);

    const onFinish = async (values) => {
        setLoading(true);
        try {
            await authAPI.login(values.email, values.password);
            navigate('/admin', { replace: true });
        } catch (error) {
            const status = error.response?.status;
            const detail = error.response?.data?.detail;
            if (status === 401 || status === 400) {
                form.setFields([
                    { name: 'password', errors: [detail || 'Usuario o contraseña incorrectos'] },
                ]);
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <Flex
            vertical
            align="center"
            justify="center"
            style={{
                minHeight: '100dvh',
                width: '100%',
                boxSizing: 'border-box',
                paddingInline: 'max(20px, env(safe-area-inset-left), env(safe-area-inset-right))',
                paddingBlock: 'max(24px, env(safe-area-inset-top))',
                paddingBottom: 'max(24px, env(safe-area-inset-bottom))',
                background: `url(${import.meta.env.BASE_URL}login-background.svg) center / cover no-repeat`,
                overscrollBehavior: 'none',
                overflowX: 'hidden',
            }}
        >
            <div
                style={{
                    width: '100%',
                    maxWidth: 1088,
                    marginInline: 'auto',
                    background: token.colorBgContainer,
                    borderRadius: 16,
                    boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
                    padding: 'clamp(32px, 5vw, 72px) clamp(20px, 4vw, 56px)',
                    boxSizing: 'border-box',
                    overflow: 'hidden',
                }}
            >
                <Row
                    gutter={[
                        { xs: 0, sm: 0, md: 32, lg: 48 },
                        { xs: 24, sm: 24, md: 0 },
                    ]}
                    align="middle"
                    style={{ margin: 0 }}
                >
                    <Col xs={24} md={12}>
                        <Flex vertical align="center" justify="center">
                            <div style={{ width: '100%', maxWidth: 260 }}>
                                <Flex vertical gap={4} style={{ marginBottom: token.marginXL }}>
                                    <Title style={{ margin: 0, color: BRAND.purple, fontSize: 22, fontWeight: 700, lineHeight: 1.2, fontFamily: '"Garet", sans-serif' }}>
                                        Hola
                                    </Title>
                                    <Text style={{ fontSize: 12, color: '#1f2937', fontWeight: 400, fontFamily: '"Garet", sans-serif' }}>
                                        Ingresa tus datos para iniciar sesión.
                                    </Text>
                                </Flex>

                                <Form
                                    form={form}
                                    name="login"
                                    onFinish={onFinish}
                                    autoComplete="off"
                                    layout="vertical"
                                    initialValues={import.meta.env.DEV ? { email: 'admin@iieg.gob.mx' } : {}}
                                    className="login-form-minerva"
                                    requiredMark={(label, info) => (
                                        <>
                                            {label}
                                            {info.required && (
                                                <span style={{ color: BRAND.orange, marginLeft: 4, fontWeight: 700 }}>*</span>
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
                                        <Input placeholder="correo@iieg.gob.mx" />
                                    </Form.Item>

                                    <Form.Item
                                        label="Contraseña"
                                        name="password"
                                        rules={[{ required: true, message: 'Ingrese su contraseña' }]}
                                    >
                                        <Input.Password
                                            placeholder="Contraseña"
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
                                                background: BRAND.purple,
                                                borderColor: BRAND.purple,
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
                                </Form>
                            </div>
                        </Flex>
                    </Col>

                    <Col xs={0} md={12}>
                        <Flex
                            vertical
                            align="center"
                            justify="center"
                            gap={28}
                            style={{
                                minHeight: 300,
                                width: '100%',
                                padding: '24px 16px',
                            }}
                        >
                            <Flex align="center" justify="center" gap={18} wrap>
                                <img
                                    src={`${import.meta.env.BASE_URL}iieg-favicon-192.png`}
                                    alt=""
                                    aria-hidden="true"
                                    style={{ height: 86, width: 'auto' }}
                                />
                                <div style={{ width: 2, height: 54, background: BRAND.orange }} aria-hidden />
                                <Title
                                    level={1}
                                    style={{
                                        margin: 0,
                                        color: '#5B6770',
                                        fontWeight: 800,
                                        letterSpacing: 0,
                                        fontSize: 58,
                                        lineHeight: 1,
                                        fontFamily: '"Garet", sans-serif',
                                    }}
                                >
                                    Minerva
                                </Title>
                            </Flex>
                            <Text
                                style={{
                                    maxWidth: 360,
                                    textAlign: 'center',
                                    color: '#5B6770',
                                    fontSize: 16,
                                    fontWeight: 600,
                                    lineHeight: 1.35,
                                    fontFamily: '"Garet", sans-serif',
                                }}
                            >
                                Sistema institucional de autenticación y gestión de accesos
                            </Text>
                        </Flex>
                    </Col>
                </Row>
            </div>

            <Flex vertical align="center" gap={20} style={{ marginTop: 40 }}>
                <img
                    src={`${import.meta.env.BASE_URL}jalisco-logo.svg`}
                    alt="Gobierno de Jalisco"
                    style={{ height: 52, width: 'auto' }}
                />
                <TypoLink
                    href="https://iieg.gob.mx/ns/wp-content/uploads/2025/06/Aviso_de_Privacidad_Integral_IIEG_06_2025.pdf"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                        fontSize: 10,
                        color: '#fff',
                        textDecoration: 'underline',
                        fontWeight: 700,
                        fontFamily: '"Garet", sans-serif',
                    }}
                >
                    Aviso de privacidad
                </TypoLink>
            </Flex>
        </Flex>
    );
}
