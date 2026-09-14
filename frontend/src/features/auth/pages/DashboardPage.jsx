import { useState, useEffect } from 'react';
import { Typography, Card, Descriptions, Tag, Row, Col, Statistic, Empty, Spin, Space } from 'antd';
import {
    TeamOutlined,
    AppstoreOutlined,
    SafetyOutlined,
    KeyOutlined,
    UsergroupAddOutlined,
} from '@ant-design/icons';
import * as authAPI from '@/api/auth';
import * as appsAPI from '@/api/applications';
import * as usersAPI from '@/api/users';
import * as rolesAPI from '@/api/roles';
import * as permsAPI from '@/api/permissions';
import * as groupsAPI from '@/api/groups';

const { Title, Text } = Typography;
const FONT = '"Garet", sans-serif';
const NAVY = '#2e4372';
const PURPLE = '#5C2472';

const STATUS_LABELS = {
    active: { text: 'Activo', color: 'green' },
    pending: { text: 'Pendiente', color: 'gold' },
    inactive: { text: 'Inactivo', color: 'default' },
    suspended: { text: 'Suspendido', color: 'red' },
};

export default function DashboardPage() {
    const [profile, setProfile] = useState(null);
    const [apps, setApps] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const [profileRes, appsRes, usersRes, rolesRes, permsRes, groupsRes] =
                    await Promise.all([
                        authAPI.getMyProfile(),
                        appsAPI.listApplications({ limit: 100 }),
                        usersAPI.listUsers({ limit: 1 }),
                        rolesAPI.listRoles({ limit: 1 }),
                        permsAPI.listPermissions({ limit: 1 }),
                        groupsAPI.listGroups({ limit: 1 }),
                    ]);
                setProfile(profileRes);
                setApps(appsRes.items || []);
                setStats({
                    users: usersRes.total || 0,
                    applications: appsRes.total || 0,
                    roles: rolesRes.total || 0,
                    permissions: permsRes.total || 0,
                    groups: groupsRes.total || 0,
                });
            } catch {
                // los errores de carga dejan secciones vacías
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    if (loading) {
        return <Spin style={{ display: 'block', marginTop: 80 }} />;
    }

    if (!profile) {
        return <Text style={{ fontFamily: FONT }}>No se pudo cargar la información.</Text>;
    }

    const user = profile.user || {};
    const appName = (appId) => apps.find((a) => a.id === appId)?.name || 'Sistema';

    // Agrupa roles y permisos del usuario por sistema (application_id)
    const bySystem = {};
    for (const r of profile.roles || []) {
        const key = r.application_id;
        bySystem[key] = bySystem[key] || { roles: [], permissions: [] };
        bySystem[key].roles.push(r);
    }
    for (const p of profile.permissions || []) {
        const key = p.application_id;
        bySystem[key] = bySystem[key] || { roles: [], permissions: [] };
        bySystem[key].permissions.push(p);
    }
    const systems = Object.keys(bySystem);
    const statusInfo = STATUS_LABELS[user.status] || { text: user.status, color: 'default' };

    const statCards = [
        { title: 'Usuarios', value: stats?.users, icon: <TeamOutlined />, color: NAVY },
        {
            title: 'Aplicaciones',
            value: stats?.applications,
            icon: <AppstoreOutlined />,
            color: PURPLE,
        },
        { title: 'Roles', value: stats?.roles, icon: <SafetyOutlined />, color: NAVY },
        { title: 'Permisos', value: stats?.permissions, icon: <KeyOutlined />, color: PURPLE },
        { title: 'Grupos', value: stats?.groups, icon: <UsergroupAddOutlined />, color: NAVY },
    ];

    return (
        <div>
            <Title level={4} style={{ color: NAVY, fontFamily: FONT, marginBottom: 4 }}>
                Bienvenido, {user.full_name}
            </Title>
            <Text type="secondary" style={{ fontFamily: FONT }}>
                Resumen general del sistema de identidad y accesos.
            </Text>

            <Row gutter={[16, 16]} style={{ marginTop: 20 }}>
                {statCards.map((s) => (
                    <Col xs={12} sm={12} md={8} lg={4} xl={4} key={s.title} flex="1">
                        <Card style={{ borderRadius: 12 }} styles={{ body: { padding: 16 } }}>
                            <Statistic
                                title={<span style={{ fontFamily: FONT }}>{s.title}</span>}
                                value={s.value ?? 0}
                                prefix={
                                    <span style={{ color: s.color, marginRight: 4 }}>{s.icon}</span>
                                }
                                valueStyle={{ color: s.color, fontFamily: FONT, fontWeight: 700 }}
                            />
                        </Card>
                    </Col>
                ))}
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
                <Col xs={24} lg={8}>
                    <Card
                        title="Mi cuenta"
                        style={{ borderRadius: 12, height: '100%' }}
                        styles={{ header: { fontFamily: FONT } }}
                    >
                        <Descriptions
                            column={1}
                            size="small"
                            labelStyle={{ fontWeight: 600, fontFamily: FONT, width: 110 }}
                            contentStyle={{ fontFamily: FONT }}
                        >
                            <Descriptions.Item label="Nombre">{user.full_name}</Descriptions.Item>
                            <Descriptions.Item label="Email">{user.email}</Descriptions.Item>
                            <Descriptions.Item label="Estado">
                                <Tag color={statusInfo.color}>{statusInfo.text}</Tag>
                            </Descriptions.Item>
                        </Descriptions>
                    </Card>
                </Col>

                <Col xs={24} lg={16}>
                    <Card
                        title="Mis accesos por sistema"
                        style={{ borderRadius: 12, height: '100%' }}
                        styles={{ header: { fontFamily: FONT } }}
                    >
                        {systems.length === 0 ? (
                            <Empty description="Sin roles ni permisos asignados" />
                        ) : (
                            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                                {systems.map((appId) => (
                                    <div key={appId}>
                                        <Text strong style={{ fontFamily: FONT, color: NAVY }}>
                                            {appName(appId)}
                                        </Text>
                                        <div style={{ marginTop: 6 }}>
                                            <Text
                                                type="secondary"
                                                style={{ fontFamily: FONT, fontSize: 12 }}
                                            >
                                                Roles:{' '}
                                            </Text>
                                            {bySystem[appId].roles.length === 0 ? (
                                                <Text type="secondary" style={{ fontSize: 12 }}>
                                                    —
                                                </Text>
                                            ) : (
                                                bySystem[appId].roles.map((r) => (
                                                    <Tag key={r.id} color={NAVY}>
                                                        {r.name}
                                                    </Tag>
                                                ))
                                            )}
                                        </div>
                                        <div style={{ marginTop: 6 }}>
                                            <Text
                                                type="secondary"
                                                style={{ fontFamily: FONT, fontSize: 12 }}
                                            >
                                                Permisos:{' '}
                                            </Text>
                                            {bySystem[appId].permissions.length === 0 ? (
                                                <Text type="secondary" style={{ fontSize: 12 }}>
                                                    —
                                                </Text>
                                            ) : (
                                                bySystem[appId].permissions.map((p) => (
                                                    <Tag key={p.id} color={PURPLE}>
                                                        {p.slug}
                                                    </Tag>
                                                ))
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </Space>
                        )}
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
