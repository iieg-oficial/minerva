import { Typography, Flex, Row, Col, theme } from 'antd';

const { Title, Text, Link: TypoLink } = Typography;
const { useToken } = theme;

export const BRAND = {
    numeralia: '#2e4372',
    purple: '#5C2472',
    orange: '#FF8300',
};

// Shell visual compartido por el login y el selector de cuentas: fondo morado,
// card de dos columnas (contenido a la izquierda vía `children`, branding de
// Minerva/app a la derecha) y footer con Jalisco + aviso de privacidad. Así el
// selector se ve idéntico al formulario de login.
export default function AuthShell({ appName, brandColor = BRAND.purple, logoUrl, children }) {
    const { token } = useToken();

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
                            <div style={{ width: '100%', maxWidth: 320 }}>{children}</div>
                        </Flex>
                    </Col>

                    <Col xs={0} md={12}>
                        <Flex
                            vertical
                            align="center"
                            justify="center"
                            gap={28}
                            style={{ minHeight: 300, width: '100%', padding: '24px 16px' }}
                        >
                            <Flex align="center" justify="center" gap={18} wrap>
                                <img
                                    src={
                                        logoUrl || `${import.meta.env.BASE_URL}iieg-favicon-192.png`
                                    }
                                    alt=""
                                    aria-hidden="true"
                                    // El logo puede venir de un host externo (branding por app):
                                    // no filtres el referer del panel a ese tercero.
                                    referrerPolicy="no-referrer"
                                    style={{
                                        height: 86,
                                        width: 'auto',
                                        maxWidth: 200,
                                        objectFit: 'contain',
                                    }}
                                    onError={(e) => {
                                        e.currentTarget.src = `${import.meta.env.BASE_URL}iieg-favicon-192.png`;
                                    }}
                                />
                                <div
                                    style={{ width: 2, height: 54, background: BRAND.orange }}
                                    aria-hidden
                                />
                                <Title
                                    level={1}
                                    style={{
                                        margin: 0,
                                        color: appName ? brandColor : '#5B6770',
                                        fontWeight: 800,
                                        letterSpacing: 0,
                                        fontSize: appName && appName.length > 8 ? 40 : 58,
                                        lineHeight: 1,
                                        fontFamily: '"Garet", sans-serif',
                                    }}
                                >
                                    {appName || 'Minerva'}
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
                                {appName
                                    ? `Inicia sesión con tu cuenta del IIEG para continuar a ${appName}`
                                    : 'Sistema institucional de autenticación y gestión de accesos'}
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
                    href="https://iieg.jalisco.gob.mx/acervo/iieg/avisos-de-privacidad.pdf"
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
