import { useReducer, useState } from 'react';
import { Avatar, Button, Flex, Typography } from 'antd';
import {
    ArrowLeftOutlined,
    ClockCircleOutlined,
    DeleteOutlined,
    DownOutlined,
    PlusCircleOutlined,
    SettingOutlined,
    UpOutlined,
} from '@ant-design/icons';
import { getActive, getSessions, isExpired, removeSession, setActive } from '@/api/session';
import { BRAND } from './AuthShell';

const { Title, Text } = Typography;

function initial(session) {
    return (session?.name || session?.email || '?').trim().slice(0, 1).toUpperCase();
}

// Pill de estado de la sesión: activa (punto verde) o vencida (reloj gris).
function StatusPill({ expired }) {
    if (expired) {
        return (
            <Flex align="center" gap={6}>
                <ClockCircleOutlined style={{ color: '#8E8E8E', fontSize: 13 }} />
                <Text style={{ color: '#8E8E8E', fontSize: 13, fontFamily: '"Garet", sans-serif' }}>
                    Sesión vencida
                </Text>
            </Flex>
        );
    }
    return (
        <Flex align="center" gap={6}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#22C55E' }} />
            <Text style={{ color: '#16A34A', fontSize: 13, fontFamily: '"Garet", sans-serif' }}>
                Sesión activa
            </Text>
        </Flex>
    );
}

// Fila de cuenta reutilizable (avatar + nombre/email + estado + acción a la derecha).
function AccountRow({ session, brandColor, onClick, extra, dim }) {
    const content = (
        <>
            <Avatar style={{ backgroundColor: brandColor, flexShrink: 0 }}>
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
            <StatusPill expired={isExpired(session)} />
            {extra}
        </>
    );
    const style = {
        padding: '10px 12px',
        opacity: dim ? 0.7 : 1,
        minWidth: 0,
    };

    if (onClick) {
        return (
            <button
                type="button"
                onClick={onClick}
                style={{
                    ...style,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    width: '100%',
                    border: 0,
                    background: 'transparent',
                    color: 'inherit',
                    font: 'inherit',
                    textAlign: 'left',
                    cursor: 'pointer',
                }}
            >
                {content}
            </button>
        );
    }

    return (
        <Flex align="center" gap={12} style={{ ...style, cursor: 'default' }}>
            {content}
        </Flex>
    );
}

// Selector de cuentas ya iniciadas en este navegador, con
// el mismo shell visual que el login. Estados:
//  - list   → cuenta activa + dropdown de otras cuentas (login_again / login_select_account)
//  - manage → gestor con borrar por cuenta (login_account_manager)
export default function AccountSelector({
    appName,
    brandColor = BRAND.purple,
    onSelect,
    onReauth,
    onAddAccount,
    onAccountsChanged,
}) {
    const [view, setView] = useState('list');
    const [open, setOpen] = useState(false);
    const [selectedSub, setSelectedSub] = useState(
        () => getActive()?.sub || getSessions()[0]?.sub || null
    );
    const [, refresh] = useReducer((x) => x + 1, 0);

    const sessions = getSessions();
    const selected = sessions.find((s) => s.sub === selectedSub) || sessions[0] || null;
    const others = sessions.filter((s) => s.sub !== selected?.sub);

    const pick = (s) => {
        setSelectedSub(s.sub);
        setOpen(false);
    };

    const handleContinue = async () => {
        if (!selected) return;
        if (isExpired(selected)) return onReauth(selected);
        await setActive(selected.sub); // fija la cuenta activa en el backend antes de continuar
        onSelect(selected);
    };

    const handleRemove = async (sub) => {
        await removeSession(sub); // quita la cuenta del dispositivo y revoca su token
        if (sub === selectedSub) setSelectedSub(getActive()?.sub || getSessions()[0]?.sub || null);
        refresh();
        onAccountsChanged?.();
    };

    const addBtn = (
        <Button
            type="text"
            icon={<PlusCircleOutlined style={{ color: brandColor, fontSize: 20 }} />}
            onClick={onAddAccount}
            style={{
                color: BRAND.numeralia,
                fontWeight: 700,
                fontFamily: '"Garet", sans-serif',
                paddingLeft: 4,
            }}
        >
            Agregar cuenta
        </Button>
    );

    if (view === 'manage') {
        return (
            <Flex vertical gap={4} style={{ width: '100%' }}>
                <Flex align="center" gap={10} style={{ marginBottom: 4 }}>
                    <Button
                        type="text"
                        icon={<ArrowLeftOutlined style={{ color: brandColor, fontSize: 18 }} />}
                        onClick={() => setView('list')}
                        aria-label="Volver"
                    />
                    <Title
                        level={4}
                        style={{ margin: 0, color: brandColor, fontFamily: '"Garet", sans-serif' }}
                    >
                        Gestionar cuentas
                    </Title>
                </Flex>
                <Text
                    type="secondary"
                    style={{ fontSize: 12, fontFamily: '"Garet", sans-serif', marginBottom: 8 }}
                >
                    Elige qué cuentas quieres conservar en este dispositivo.
                </Text>

                <div
                    style={{
                        maxHeight: 300,
                        overflowY: 'auto',
                        border: '1px solid #EDE7F2',
                        borderRadius: 12,
                    }}
                >
                    {sessions.length === 0 ? (
                        <Text
                            type="secondary"
                            style={{ display: 'block', padding: 16, textAlign: 'center' }}
                        >
                            No hay cuentas guardadas
                        </Text>
                    ) : (
                        sessions.map((s, i) => (
                            <div
                                key={s.sub}
                                style={{ borderTop: i ? '1px solid #F0ECF4' : 'none' }}
                            >
                                <AccountRow
                                    session={s}
                                    brandColor={brandColor}
                                    extra={
                                        <Button
                                            type="text"
                                            danger
                                            icon={<DeleteOutlined />}
                                            onClick={() => handleRemove(s.sub)}
                                            aria-label={`Quitar ${s.email}`}
                                        />
                                    }
                                />
                            </div>
                        ))
                    )}
                </div>

                {addBtn}
                <Text type="secondary" style={{ fontSize: 12, fontFamily: '"Garet", sans-serif' }}>
                    Quitar una cuenta solo la elimina de este dispositivo.
                </Text>
                <Button
                    block
                    onClick={() => setView('list')}
                    style={{
                        marginTop: 8,
                        height: 40,
                        borderRadius: 20,
                        color: brandColor,
                        borderColor: brandColor,
                        fontWeight: 700,
                        fontFamily: '"Garet", sans-serif',
                    }}
                >
                    Volver al inicio de sesión
                </Button>
            </Flex>
        );
    }

    return (
        <Flex vertical gap={16} style={{ width: '100%' }}>
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
            {appName && (
                <Text
                    type="secondary"
                    style={{ marginTop: -12, fontFamily: '"Garet", sans-serif' }}
                >
                    para continuar en {appName}
                </Text>
            )}

            <div>
                {/* Card de la cuenta seleccionada + chevron para abrir el dropdown. */}
                <Flex
                    align="center"
                    gap={4}
                    style={{
                        border: `1.5px solid ${open ? brandColor : '#E3D9EC'}`,
                        borderRadius: 12,
                        background: '#F7F2FA',
                        paddingRight: 8,
                    }}
                >
                    {selected ? (
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <AccountRow session={selected} brandColor={brandColor} />
                        </div>
                    ) : (
                        <Text type="secondary" style={{ padding: '14px 12px' }}>
                            No hay cuentas guardadas
                        </Text>
                    )}
                    {others.length > 0 && (
                        <Button
                            type="text"
                            icon={open ? <UpOutlined /> : <DownOutlined />}
                            onClick={() => setOpen((v) => !v)}
                            aria-label="Ver otras cuentas"
                            style={{ color: brandColor }}
                        />
                    )}
                </Flex>

                {/* Dropdown (login_select_account): otras cuentas (scroll) + gestionar. */}
                {open && (
                    <div
                        style={{
                            marginTop: 6,
                            border: '1px solid #EDE7F2',
                            borderRadius: 12,
                            boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                            overflow: 'hidden',
                        }}
                    >
                        <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                            {others.map((s) => (
                                <AccountRow
                                    key={s.sub}
                                    session={s}
                                    brandColor={brandColor}
                                    onClick={() => pick(s)}
                                />
                            ))}
                        </div>
                        <Button
                            type="text"
                            block
                            icon={<SettingOutlined />}
                            onClick={() => {
                                setOpen(false);
                                setView('manage');
                            }}
                            style={{
                                textAlign: 'left',
                                justifyContent: 'flex-start',
                                height: 44,
                                borderTop: '1px solid #F0ECF4',
                                color: BRAND.numeralia,
                                fontWeight: 700,
                                fontFamily: '"Garet", sans-serif',
                            }}
                        >
                            Gestionar cuentas
                        </Button>
                    </div>
                )}
            </div>

            {addBtn}

            <Button
                type="primary"
                block
                disabled={!selected}
                onClick={handleContinue}
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
                Continuar
            </Button>
        </Flex>
    );
}
