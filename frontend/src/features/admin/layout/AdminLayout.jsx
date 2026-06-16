import { useState, useCallback } from 'react';
import { Layout, Menu, Button, Typography, Flex, theme } from 'antd';
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
    MenuFoldOutlined,
    MenuUnfoldOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router';
import * as authAPI from '@/api/auth';

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

    const handleLogout = useCallback(async () => {
        await authAPI.logout();
        navigate('/login', { replace: true });
    }, [navigate]);

    let userName = '';
    try {
        const stored = localStorage.getItem('user');
        if (stored) {
            userName = JSON.parse(stored).full_name || '';
        }
    } catch {}

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
                    <Flex align="center" gap={12}>
                        <Text style={{ fontFamily: '"Garet", sans-serif' }}>{userName}</Text>
                        <Button
                            type="text"
                            icon={<LogoutOutlined />}
                            onClick={handleLogout}
                            danger
                        >
                            Salir
                        </Button>
                    </Flex>
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
