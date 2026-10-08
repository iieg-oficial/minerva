import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
    Avatar,
    Button,
    ConfigProvider,
    Flex,
    Grid,
    Input,
    Tooltip,
    Typography,
} from 'antd';
import { PlusCircleOutlined } from '@ant-design/icons';
import { fetchSession, getSessions, isExpired, removeSession, setActive } from '@/api/session';
import { BRAND } from './AuthShell';

const { Title, Text } = Typography;
const { useBreakpoint } = Grid;

function initial(session) {
    return (session?.name || session?.email || '?').trim().slice(0, 1).toUpperCase();
}

// Chevron y tache con el mismo trazo que usa el visor (MapaLab), para no
// arrastrar una familia de iconos distinta a la de Ant Design en dos glifos.
function ChevronIcon({ color, giro = 90 }) {
    return (
        <svg
            width="14"
            height="14"
            viewBox="0 0 13.171 7.05"
            fill="none"
            stroke={color}
            strokeLinecap="round"
            strokeWidth="2"
            aria-hidden="true"
            style={{ transform: `rotate(${giro}deg)`, transition: 'transform 0.2s' }}
        >
            <path d="M1.409 1.409 6.6 5.746l5.163-4.337" />
        </svg>
    );
}

function CloseIcon({ color }) {
    return (
        <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
        >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
    );
}

// Fila de cuenta: toda la fila continúa con esa cuenta. El chevron (izquierda) y
// el tache (derecha) sólo aparecen al pasar el cursor, para no llenar la tarjeta
// de controles cuando el usuario únicamente está eligiendo con quién entrar.
function AccountRow({
    session,
    brandColor,
    onSelect,
    onRemove,
    abierta,
    onCerrar,
    onEntrar,
    onFallo,
}) {
    const [hover, setHover] = useState(false);
    const [pressed, setPressed] = useState(false);
    const expired = isExpired(session);
    const esMovil = !useBreakpoint().md;
    const [password, setPassword] = useState('');
    const [verPassword, setVerPassword] = useState(false);
    const [enfocado, setEnfocado] = useState(false);
    const [sacudir, setSacudir] = useState(false);
    const tarjetaRef = useRef(null);
    const campoRef = useRef(null);
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState('');
    const activa = hover || pressed || abierta;
    // En táctil no hay hover: si los controles solo aparecieran al pasar el cursor,
    // en el teléfono no habría forma de quitar una cuenta.
    const controlesVisibles = activa || esMovil;

    // Al abrir se enfoca el campo sin `autoFocus`: éste hace que el navegador
    // desplace la lista —que tiene scroll propio— para asegurar la visibilidad, y ese
    // salto se percibía como un parpadeo. `preventScroll` lo evita. `enfocado` se marca
    // aquí mismo para que el botón de entrar se pinte en el primer fotograma en vez de
    // aparecer un tick después, que era el otro salto.
    useEffect(() => {
        if (!abierta) {
            setEnfocado(false);
            setPassword('');
            setError(false);
            return;
        }
        setEnfocado(true);
        campoRef.current?.focus({ preventScroll: true });
    }, [abierta]);

    // Un clic en cualquier otro punto de la pantalla cierra el campo. Los eventos de
    // dentro de la tarjeta no llegan aquí: el bloque de la contraseña ya los detiene.
    useEffect(() => {
        if (!abierta) return undefined;
        const alClicarFuera = (e) => {
            if (tarjetaRef.current && !tarjetaRef.current.contains(e.target)) onCerrar();
        };
        document.addEventListener('mousedown', alClicarFuera);
        return () => document.removeEventListener('mousedown', alClicarFuera);
    }, [abierta, onCerrar]);

    const entrar = async () => {
        if (!password || enviando) return;
        setEnviando(true);
        setError('');
        onFallo('');
        try {
            await onEntrar(session.email, password);
        } catch (e) {
            const status = e.response?.status;
            const detalle = e.response?.data?.detail;
            setError('error');
            onFallo(
                status === 429
                    ? detalle || 'Demasiados intentos. Espera unos minutos e intenta de nuevo.'
                    : detalle || 'Contraseña incorrecta'
            );
            setSacudir(true);
            setTimeout(() => setSacudir(false), 450);
            setPassword('');
            setEnviando(false);
            campoRef.current?.focus({ preventScroll: true });
        }
    };

    return (
        <Flex
            vertical
            ref={tarjetaRef}
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => {
                setHover(false);
                setPressed(false);
            }}
            onMouseDown={() => setPressed(true)}
            onMouseUp={() => setPressed(false)}
            style={{
                padding: 12,
                cursor: abierta ? 'default' : 'pointer',
                // El relleno se reserva para la tarjeta abierta. Incluir aquí `pressed`
                // provocaba un parpadeo al abrir: entre `mouseup` (que lo apaga) y el
                // `click` (que abre) mediaba un fotograma con la tarjeta en blanco.
                background: abierta ? '#F7F2FA' : '#FFFFFF',
                // Abierta, el contorno sobra: ya la distingue el fondo y el campo de
                // contraseña. Se mantiene transparente para no alterar el ancho.
                border: `1.5px solid ${abierta ? 'transparent' : activa ? brandColor : '#E3D9EC'}`,
                borderRadius: 12,
                minWidth: 0,
                transition: 'background 0.15s, border-color 0.15s',
            }}
        >
            <Flex align="center" gap={12} style={{ minWidth: 0 }}>
            {/* El tache queda fuera de este bloque: un control interactivo dentro de otro
                es HTML inválido y su etiqueta se colaba en el nombre que anuncia el lector
                de pantalla para la cuenta. */}
            <Flex
                align="center"
                gap={12}
                onClick={() => (abierta ? onCerrar() : onSelect(session))}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        if (abierta) onCerrar();
                        else onSelect(session);
                    }
                }}
                style={{ minWidth: 0, flex: 1 }}
            >
            <Flex
                align="center"
                justify="center"
                style={{ width: 18, flexShrink: 0, opacity: controlesVisibles ? 1 : 0 }}
            >
                <ChevronIcon color={brandColor} giro={abierta ? 0 : 90} />
            </Flex>

            <Avatar style={{ backgroundColor: BRAND.orange, flexShrink: 0 }}>
                {initial(session)}
            </Avatar>

            <Flex vertical style={{ minWidth: 0, flex: 1 }}>
                <Text
                    strong
                    ellipsis
                    style={{
                        color: BRAND.numeralia,
                        fontSize: 14,
                        fontFamily: '"Garet", sans-serif',
                    }}
                >
                    {session.name || session.email}
                </Text>
                <Text
                    type="secondary"
                    ellipsis
                    style={{ fontSize: 12, fontFamily: '"Garet", sans-serif' }}
                >
                    {session.email}
                </Text>
            </Flex>

            {expired && (
                <Text
                    style={{
                        color: '#8E8E8E',
                        fontSize: 12,
                        whiteSpace: 'nowrap',
                        fontFamily: '"Garet", sans-serif',
                    }}
                >
                    Pedirá tu contraseña
                </Text>
            )}
            </Flex>

            <Button
                type="text"
                size="small"
                shape="circle"
                icon={<CloseIcon color="#8E8E8E" />}
                onClick={(e) => {
                    e.stopPropagation();
                    onRemove(session.sub);
                }}
                aria-label={`Quitar ${session.email}`}
                style={{
                    flexShrink: 0,
                    // Con la contraseña desplegada, el clic en la tarjeta cierra: dejar
                    // el tache visible ahí invita a confundir cerrar con eliminar.
                    opacity: controlesVisibles && !abierta ? 1 : 0,
                    pointerEvents: abierta ? 'none' : 'auto',
                }}
            />
            </Flex>

            {abierta && (
                <Flex
                    vertical
                    gap={6}
                    className="login-form-minerva"
                    style={{ marginTop: 10, width: '100%' }}
                    // El campo vive dentro de una tarjeta que abre y cierra al clic: sin
                    // esto, teclear la contraseña cerraría la tarjeta al burbujear, y el
                    // `mousedown` marcaría la fila como presionada (el parpadeo).
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                    onMouseUp={(e) => e.stopPropagation()}
                >
                    <Input
                        ref={campoRef}
                        className={sacudir ? 'minerva-sacudida' : undefined}
                        type={verPassword ? 'text' : 'password'}
                        placeholder="Contraseña"
                        value={password}
                        // `readOnly` y no `disabled`: un campo deshabilitado pierde el
                        // foco al vuelo y no lo recupera al rehabilitarse, así que tras
                        // un intento fallido había que volver a hacer clic para escribir.
                        readOnly={enviando}
                        status={error ? 'error' : undefined}
                        onChange={(e) => {
                            setPassword(e.target.value);
                            if (error) setError('');
                        }}
                        onPressEnter={entrar}
                        onFocus={() => setEnfocado(true)}
                        onBlur={() => setEnfocado(false)}
                        suffix={
                            <Flex align="center" gap={6}>
                                {password && (
                                    <img
                                        src={`${import.meta.env.BASE_URL}${verPassword ? 'ico-show.svg' : 'ico-hidden.svg'}`}
                                        alt={
                                            verPassword
                                                ? 'Ocultar contraseña'
                                                : 'Mostrar contraseña'
                                        }
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => setVerPassword((v) => !v)}
                                        style={{ width: 22, height: 22, cursor: 'pointer' }}
                                    />
                                )}
                                {/* Aparece con el campo en uso —enfocado, con texto o
                                    enviando—; el `preventDefault` evita que el clic le
                                    robe el foco al input y lo haga desaparecer antes de
                                    registrar la pulsación. */}
                                {(enfocado || password || enviando) && (
                                    <ConfigProvider wave={{ disabled: true }}>
                                        <Tooltip title="Entrar" placement="top">
                                            <Button
                                                type="primary"
                                                shape="circle"
                                                size="small"
                                                loading={enviando}
                                                onMouseDown={(e) => e.preventDefault()}
                                                onClick={entrar}
                                                aria-label="Entrar"
                                                icon={<ChevronIcon color="#fff" giro={-90} />}
                                                style={{
                                                    background: brandColor,
                                                    borderColor: brandColor,
                                                    boxShadow: 'none',
                                                }}
                                            />
                                        </Tooltip>
                                    </ConfigProvider>
                                )}
                            </Flex>
                        }
                    />
                </Flex>
            )}
        </Flex>
    );
}

// Cuentas ya iniciadas en este navegador. Una sola lista: elegir la cuenta ES
// continuar, así que no hay selección previa ni botón aparte.
export default function AccountSelector({
    brandColor = BRAND.purple,
    onSelect,
    onEntrar,
    onAddAccount,
    onAccountsChanged,
    abrirSub = null,
    exigeContrasena = false,
}) {
    const [, refresh] = useReducer((x) => x + 1, 0);
    const [abierta, setAbierta] = useState(abrirSub);
    // El aviso de credenciales vive fuera de la tarjeta, bajo la cuenta que falló, para
    // no alterar su alto ni empujar el campo mientras se escribe.
    const [fallo, setFallo] = useState({ sub: null, mensaje: '' });
    const cerrar = useCallback(() => {
        setAbierta(null);
        setFallo({ sub: null, mensaje: '' });
    }, []);
    const sessions = getSessions();

    // Una sesión vencida no manda al formulario: despliega la contraseña dentro de su
    // propia tarjeta. El correo ya está ahí, así que no hay que volver a escribirlo ni
    // cambiar de vista.
    //
    // `exigeContrasena` viene de `prompt=login`: ahí la cuenta puede estar vigente y aun
    // así hay que re-autenticar. Sin esta comprobación bastaba cerrar la tarjeta y volver
    // a tocarla para entrar sin escribir nada.
    //
    // Una cuenta cerrada con «Cerrar sesión» llega marcada como vencida. Si aun así el
    // backend rechaza activarla (409: su sesión se revocó por otra vía), se refresca el
    // estado y se pide la contraseña igual: sólo una sesión viva entra sin escribirla.
    const handleSelect = async (session) => {
        if (exigeContrasena || isExpired(session)) {
            setAbierta(session.sub);
            return;
        }
        try {
            await setActive(session.sub); // fija la cuenta activa en el backend antes de continuar
        } catch (e) {
            if (e.response?.status !== 409) throw e;
            await fetchSession();
            refresh();
            onAccountsChanged?.();
            setAbierta(session.sub);
            return;
        }
        onSelect(session);
    };

    const handleRemove = async (sub) => {
        await removeSession(sub); // quita la cuenta del dispositivo y revoca su token
        if (sub === abierta) setAbierta(null);
        refresh();
        onAccountsChanged?.();
    };

    return (
        <Flex vertical gap={24} style={{ width: '100%' }}>
            <Title
                level={4}
                style={{
                    margin: 0,
                    color: brandColor,
                    fontWeight: 700,
                    fontFamily: '"Garet", sans-serif',
                }}
            >
                Iniciar sesión con:
            </Title>

            <Flex
                vertical
                gap={10}
                style={{ maxHeight: 288, overflowY: 'auto', paddingRight: 2 }}
            >
                {sessions.length === 0 ? (
                    <Text type="secondary" style={{ display: 'block', padding: 16 }}>
                        No hay cuentas guardadas
                    </Text>
                ) : (
                    sessions.map((s) => (
                        <Flex vertical key={s.sub}>
                            <AccountRow
                                session={s}
                                brandColor={brandColor}
                                onSelect={handleSelect}
                                onRemove={handleRemove}
                                abierta={abierta === s.sub}
                                onCerrar={cerrar}
                                onEntrar={onEntrar}
                                onFallo={(mensaje) => setFallo({ sub: s.sub, mensaje })}
                            />
                            {fallo.sub === s.sub && fallo.mensaje && (
                                <Flex
                                    align="center"
                                    gap={8}
                                    role="alert"
                                    style={{ padding: '6px 12px 2px' }}
                                >
                                    <CloseIcon color="#FF4D4F" />
                                    <Text
                                        style={{
                                            color: '#FF4D4F',
                                            fontSize: 12,
                                            fontFamily: '"Garet", sans-serif',
                                        }}
                                    >
                                        {fallo.mensaje}
                                    </Text>
                                </Flex>
                            )}
                        </Flex>
                    ))
                )}
            </Flex>

            <Button
                type="text"
                icon={<PlusCircleOutlined style={{ color: brandColor, fontSize: 20 }} />}
                onClick={onAddAccount}
                style={{
                    color: BRAND.numeralia,
                    fontWeight: 700,
                    fontFamily: '"Garet", sans-serif',
                    alignSelf: 'center',
                }}
            >
                Agregar cuenta
            </Button>
        </Flex>
    );
}
