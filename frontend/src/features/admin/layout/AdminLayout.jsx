import { useState, useCallback } from 'react';
import {
    App as AntApp,
    Layout,
    Menu,
    Button,
    Typography,
    Flex,
    Dropdown,
    Avatar,
    theme,
} from 'antd';
import {
    HomeOutlined,
    TeamOutlined,
    AppstoreOutlined,
    SafetyOutlined,
    KeyOutlined,
    UsergroupAddOutlined,
    CheckCircleOutlined,
    FileTextOutlined,
    LockOutlined,
    LogoutOutlined,
    PlusOutlined,
    DownOutlined,
    MenuFoldOutlined,
    MenuUnfoldOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import * as authAPI from '@/api/auth';
import { isExpired, setActive } from '@/api/session';
import { useSession } from '@features/auth/SessionContext';

function initial(session) {
    return (session?.name || session?.email || '?').trim().slice(0, 1).toUpperCase();
}

const { Header, Sider, Content } = Layout;
const { Text } = Typography;
const { useToken } = theme;

const MENU_ITEMS = [
    { key: '/admin', icon: <HomeOutlined />, label: 'Dashboard' },
    { key: '/admin/users', icon: <TeamOutlined />, label: 'Usuarios' },
    { key: '/admin/applications', icon: <AppstoreOutlined />, label: 'Aplicaciones' },
    { key: '/admin/roles', icon: <SafetyOutlined />, label: 'Roles' },
    { key: '/admin/permissions', icon: <KeyOutlined />, label: 'Permisos' },
    { key: '/admin/groups', icon: <UsergroupAddOutlined />, label: 'Grupos' },
    { key: '/admin/authorization', icon: <CheckCircleOutlined />, label: 'Autorización' },
    { key: '/admin/audit', icon: <FileTextOutlined />, label: 'Auditoría' },
];

export default function AdminLayout() {
    const [collapsed, setCollapsed] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    const { token } = useToken();

    // Prefijo más largo: /admin solo gana en la raíz exacta; cada subruta resalta su sección.
    const selectedKey =
        MENU_ITEMS.map((item) => item.key)
            .filter((key) => location.pathname === key || location.pathname.startsWith(key + '/'))
            .sort((a, b) => b.length - a.length)[0] || '/admin';

    const { accounts: sessions, active, refresh } = useSession();
    const { message } = AntApp.useApp();
    const userName = active?.name || '';

    // Menú de cuenta: cambiar entre sesiones del navegador, agregar otra, o cerrar.
    const accountItems = sessions
        .filter((s) => s.sub !== active?.sub)
        .map((s) => ({
            key: `${isExpired(s) ? 'reauth' : 'switch'}:${s.sub}`,
            icon: (
                <Avatar size="small" style={{ backgroundColor: '#5C2472' }}>
                    {initial(s)}
                </Avatar>
            ),
            label: isExpired(s)
                ? `${s.email} (${s.signed_out ? 'sesión cerrada' : 'expirada'})`
                : s.name || s.email,
        }));

    const menuItems = [
        ...(accountItems.length ? [...accountItems, { type: 'divider' }] : []),
        { key: 'add', icon: <PlusOutlined />, label: 'Agregar otra cuenta' },
        { key: 'password', icon: <LockOutlined />, label: 'Cambiar contraseña' },
        { key: 'logout', icon: <LogoutOutlined />, label: 'Cerrar sesión', danger: true },
        ...(sessions.length > 1
            ? [{ key: 'logoutAll', label: 'Cerrar todas las sesiones', danger: true }]
            : []),
    ];

    const onAccountMenu = useCallback(
        async ({ key }) => {
            if (key === 'add') return navigate('/login?add=1');
            if (key === 'password') return navigate('/cuenta/contrasena');
            if (key === 'logout') {
                // Cierra y revoca la cuenta activa; queda en el selector pidiendo contraseña.
                // Las demás cuentas del navegador siguen vivas.
                try {
                    await authAPI.logout();
                } catch {
                    message.error('No se pudo cerrar la sesión. Intenta de nuevo.');
                    return;
                }
                await refresh();
                return navigate('/login', { replace: true });
            }
            if (key === 'logoutAll') {
                // Con cookie HttpOnly, JS no puede invalidar la sesión: si el backend falla,
                // la sesión sigue viva. No navegamos (no aparentar que se cerró) y avisamos.
                try {
                    await authAPI.logoutAll();
                } catch {
                    message.error('No se pudieron cerrar todas las sesiones. Intenta de nuevo.');
                    return;
                }
                await refresh();
                return navigate('/login', { replace: true });
            }
            const [action, sub] = key.split(':');
            const reauth = () => {
                const s = sessions.find((x) => x.sub === sub);
                navigate(`/login?add=1&email=${encodeURIComponent(s?.email || '')}`);
            };
            if (action === 'switch') {
                try {
                    await setActive(sub);
                } catch (e) {
                    // 409: la sesión de esa cuenta ya no vale; se entra con contraseña.
                    if (e.response?.status === 409) return reauth();
                    message.error('No se pudo cambiar de cuenta. Intenta de nuevo.');
                    return;
                }
                window.location.assign('/admin'); // recarga para re-leer la cuenta activa
            } else if (action === 'reauth') {
                reauth();
            }
        },
        [navigate, sessions, refresh, message]
    );

    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider
                trigger={null}
                collapsible
                collapsed={collapsed}
                width={240}
                style={{
                    background: '#2e4372',
                    borderRight: 'none',
                }}
            >
                <Flex
                    vertical
                    align="center"
                    justify="center"
                    style={{ height: 64, padding: '0 16px' }}
                >
                    <Flex align="center" gap={8}>
                        <img
                            src={`${import.meta.env.BASE_URL}iieg-favicon-192.png`}
                            alt=""
                            style={{ height: 28, width: 'auto' }}
                        />
                        {!collapsed && (
                            <Text
                                strong
                                style={{
                                    color: '#fff',
                                    fontSize: 16,
                                    fontFamily: '"Garet", sans-serif',
                                }}
                            >
                                Minerva
                            </Text>
                        )}
                    </Flex>
                </Flex>
                <Menu
                    theme="dark"
                    mode="inline"
                    selectedKeys={[selectedKey]}
                    items={MENU_ITEMS}
                    onClick={({ key }) => navigate(key)}
                    style={{
                        background: 'transparent',
                        borderRight: 'none',
                        fontFamily: '"Garet", sans-serif',
                    }}
                />
            </Sider>
            <Layout>
                <Header
                    style={{
                        background: token.colorBgContainer,
                        padding: '0 24px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
                    }}
                >
                    <Button
                        type="text"
                        icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                        onClick={() => setCollapsed(!collapsed)}
                    />
                    <Dropdown
                        menu={{ items: menuItems, onClick: onAccountMenu }}
                        trigger={['click']}
                    >
                        <Button type="text" style={{ height: 'auto', padding: '4px 8px' }}>
                            <Flex align="center" gap={8}>
                                <Avatar size="small" style={{ backgroundColor: '#5C2472' }}>
                                    {initial(active)}
                                </Avatar>
                                <Text style={{ fontFamily: '"Garet", sans-serif' }}>
                                    {userName}
                                </Text>
                                <DownOutlined style={{ fontSize: 10 }} />
                            </Flex>
                        </Button>
                    </Dropdown>
                </Header>
                <Content
                    style={{
                        margin: 24,
                        padding: 24,
                        background: token.colorBgContainer,
                        borderRadius: token.borderRadiusLG,
                        minHeight: 280,
                    }}
                >
                    <Outlet />
                </Content>
            </Layout>
        </Layout>
    );
}
