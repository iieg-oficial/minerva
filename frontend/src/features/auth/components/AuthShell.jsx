import { useEffect, useRef, useState } from 'react';
import { Typography, Flex, Row, Col, theme, Grid } from 'antd';

const { useBreakpoint } = Grid;

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
    // En móvil la columna de branding no se pinta (`xs={0}`), así que el logo de la
    // aplicación anfitriona sube arriba de la card para que siga presente.
    const esMovil = !useBreakpoint().md;
    const [logoFallo, setLogoFallo] = useState(false);
    // Sin logo propio de la app no hay nada que separar: se muestra solo el nombre,
    // sin el filete naranja ni el logo genérico.
    const mostrarLogoApp = Boolean(logoUrl) && !logoFallo;

    // El lockup de la derecha envuelve en anchos intermedios y el filete naranja se
    // quedaba colgando al final del renglón del logo. Se oculta sin sacarlo del flujo:
    // si se quitara del layout volvería a caber en una línea y entraría en un
    // parpadeo mostrar/ocultar.
    const nombreRef = useRef(null);
    const logoRef = useRef(null);
    const [lockupEnDosLineas, setLockupEnDosLineas] = useState(false);

    useEffect(() => {
        const medir = () => {
            const logo = logoRef.current;
            const nombre = nombreRef.current;
            if (!logo || !nombre) return;
            // Con `align="center"` dos elementos de la MISMA línea ya tienen distinto
            // `offsetTop`, así que compararlos entre sí da falso positivo. Hay salto de
            // línea solo si el nombre empieza por debajo de donde termina el logo.
            setLockupEnDosLineas(nombre.offsetTop >= logo.offsetTop + logo.offsetHeight);
        };
        medir();
        const observador = new ResizeObserver(medir);
        if (logoRef.current?.parentElement) observador.observe(logoRef.current.parentElement);
        return () => observador.disconnect();
    }, [appName, logoUrl, mostrarLogoApp]);

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
            {esMovil && (
                <Flex align="center" justify="center" gap={14} style={{ marginBottom: 28 }}>
                    {mostrarLogoApp && (
                        <img
                            src={logoUrl}
                            alt=""
                            aria-hidden="true"
                            referrerPolicy="no-referrer"
                            onError={() => setLogoFallo(true)}
                            style={{
                                height: 56,
                                width: 'auto',
                                maxWidth: 140,
                                objectFit: 'contain',
                            }}
                        />
                    )}
                    <Title
                        level={1}
                        style={{
                            margin: 0,
                            // Va sobre el fondo morado, fuera de la card: el color de
                            // marca no contrasta ahí, el blanco sí.
                            color: '#fff',
                            fontWeight: 800,
                            letterSpacing: 1,
                            fontSize: 26,
                            fontFamily: '"Garet", sans-serif',
                        }}
                    >
                        {appName || 'Minerva'}
                    </Title>
                </Flex>
            )}

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

                    <Col
                        xs={0}
                        md={12}
                        // El filete que sale del lockup al partirse en dos líneas se
                        // recupera aquí, en el canal que la rejilla deja entre columnas,
                        // así que queda a la misma distancia de ambos contenidos sin
                        // tocar sus paddings. Se pinta como fondo porque un `borderLeft`
                        // ocuparía todo el alto y se quiere un tercio.
                        style={{
                            backgroundImage: lockupEnDosLineas
                                ? `linear-gradient(${BRAND.orange}, ${BRAND.orange})`
                                : 'none',
                            backgroundSize: '2px 33%',
                            backgroundPosition: 'left center',
                            backgroundRepeat: 'no-repeat',
                        }}
                    >
                        <Flex
                            vertical
                            align="center"
                            justify="center"
                            gap={28}
                            style={{ minHeight: 300, width: '100%', padding: '24px 0' }}
                        >
                            <Flex align="center" justify="center" gap={18} wrap>
                                <img
                                    src={
                                        logoUrl || `${import.meta.env.BASE_URL}iieg-favicon-192.png`
                                    }
                                    alt=""
                                    aria-hidden="true"
                                    ref={logoRef}
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
                                    style={{
                                        width: 2,
                                        height: 54,
                                        background: BRAND.orange,
                                        visibility: lockupEnDosLineas ? 'hidden' : 'visible',
                                    }}
                                    aria-hidden
                                />
                                <Title
                                    level={1}
                                    ref={nombreRef}
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

            {/* Firma institucional: el IIEG es obligatorio en cualquier desarrollo del
                instituto. Variante para fondo oscuro, que es sobre lo que se pinta.
                Rejilla de tres columnas: la central la dimensiona el propio aviso, así
                que el hueco entre los logos mide exactamente lo que mide ese texto —el
                IIEG termina donde empieza y Jalisco arranca donde acaba— sin números
                mágicos que se rompan si cambia la leyenda. */}
            <div
                style={{
                    marginTop: 40,
                    display: 'grid',
                    gridTemplateColumns: esMovil
                        ? 'minmax(0, auto) 48px minmax(0, auto)'
                        : 'minmax(0, auto) auto minmax(0, auto)',
                    justifyContent: 'center',
                    alignItems: 'center',
                    rowGap: esMovil ? 28 : 40,
                    maxWidth: '100%',
                }}
            >
                <img
                    src={`${import.meta.env.BASE_URL}iieg-logo-dark.svg`}
                    alt="Instituto de Información Estadística y Geográfica"
                    style={{
                        gridColumn: 1,
                        gridRow: 1,
                        height: esMovil ? 42 : 'clamp(30px, 8vw, 52px)',
                        width: 'auto',
                        maxWidth: '100%',
                        objectFit: 'contain',
                    }}
                />
                <img
                    src={`${import.meta.env.BASE_URL}jalisco-logo.svg`}
                    alt="Gobierno de Jalisco"
                    style={{
                        gridColumn: 3,
                        gridRow: 1,
                        height: esMovil ? 42 : 'clamp(30px, 8vw, 52px)',
                        width: 'auto',
                        maxWidth: '100%',
                        objectFit: 'contain',
                    }}
                />
                <TypoLink
                    href="https://iieg.jalisco.gob.mx/acervo/iieg/avisos-de-privacidad.pdf"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                        // En escritorio va en la columna central para que sea el texto
                        // quien fije el hueco entre los logos; en móvil ese hueco es
                        // fijo, así que el aviso se centra bajo las tres columnas.
                        gridColumn: esMovil ? '1 / -1' : 2,
                        gridRow: 2,
                        justifySelf: 'center',
                        fontSize: 10,
                        color: '#fff',
                        textDecoration: 'underline',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                        fontFamily: '"Garet", sans-serif',
                        paddingInline: 16,
                    }}
                >
                    Aviso de privacidad
                </TypoLink>
            </div>
        </Flex>
    );
}
