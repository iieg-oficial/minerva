import { useState, useCallback } from 'react';
import { Layout, Menu, Button, Typography, Flex, Dropdown, Avatar, theme } from 'antd';
import {
    HomeOutlined,
    TeamOutlined,
    AppstoreOutlined,
    SafetyOutlined,
    KeyOutlined,
    UsergroupAddOutlined,
    CheckCircleOutlined,
    FileTextOutlined,
    LogoutOutlined,
    PlusOutlined,
    DownOutlined,
    MenuFoldOutlined,
    MenuUnfoldOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router';
import * as authAPI from '@/api/auth';
import { getActive, getSessions, isExpired, setActive } from '@/api/session';

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

    const selectedKey = MENU_ITEMS.find((item) => location.pathname.startsWith(item.key))?.key || '/admin';

    const sessions = getSessions();
    const active = getActive();
    const userName = active?.name || '';

    // Menú de cuenta: cambiar entre sesiones del navegador, agregar otra, o cerrar.
    const accountItems = sessions
        .filter((s) => s.sub !== active?.sub)
        .map((s) => ({
            key: `${isExpired(s) ? 'reauth' : 'switch'}:${s.sub}`,
            icon: <Avatar size="small" style={{ backgroundColor: '#5C2472' }}>{initial(s)}</Avatar>,
            label: isExpired(s) ? `${s.email} (expirada)` : s.name || s.email,
        }));

    const menuItems = [
        ...(accountItems.length ? [...accountItems, { type: 'divider' }] : []),
        { key: 'add', icon: <PlusOutlined />, label: 'Agregar otra cuenta' },
        { key: 'logout', icon: <LogoutOutlined />, label: 'Cerrar sesión', danger: true },
        ...(sessions.length > 1 ? [{ key: 'logoutAll', label: 'Cerrar todas las sesiones', danger: true }] : []),
    ];

    const onAccountMenu = useCallback(
        async ({ key }) => {
            if (key === 'add') return navigate('/login?add=1');
            if (key === 'logout') {
                await authAPI.logout();
                // Si quedó otra cuenta activa, recargamos como ella; si no, a login.
                if (getActive()) return window.location.assign('/admin');
                return navigate('/login', { replace: true });
            }
            if (key === 'logoutAll') {
                await authAPI.logoutAll();
                return navigate('/login', { replace: true });
            }
            const [action, sub] = key.split(':');
            if (action === 'switch') {
                setActive(sub);
                window.location.assign('/admin'); // recarga para re-leer la cuenta activa
            } else if (action === 'reauth') {
                const s = sessions.find((x) => x.sub === sub);
                navigate(`/login?add=1&email=${encodeURIComponent(s?.email || '')}`);
            }
        },
        [navigate, sessions],
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
                    <Dropdown menu={{ items: menuItems, onClick: onAccountMenu }} trigger={['click']}>
                        <Button type="text" style={{ height: 'auto', padding: '4px 8px' }}>
                            <Flex align="center" gap={8}>
                                <Avatar size="small" style={{ backgroundColor: '#5C2472' }}>{initial(active)}</Avatar>
                                <Text style={{ fontFamily: '"Garet", sans-serif' }}>{userName}</Text>
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
