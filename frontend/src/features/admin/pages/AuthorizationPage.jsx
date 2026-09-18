import { useState, useEffect, useCallback } from 'react';
import {
    Form,
    Input,
    Select,
    Button,
    Typography,
    Card,
    Tag,
    Space,
    App,
    Descriptions,
    Badge,
    Tabs,
    Empty,
    Spin,
    Row,
    Col,
} from 'antd';
import {
    CheckCircleOutlined,
    SafetyOutlined,
    UserAddOutlined,
    CloseOutlined,
    ReloadOutlined,
} from '@ant-design/icons';
import * as authzAPI from '@/api/authorization';
import * as appsAPI from '@/api/applications';
import * as usersAPI from '@/api/users';
import * as rolesAPI from '@/api/roles';
import * as groupsAPI from '@/api/groups';
import { formatApiError } from '@/api/errors';

const { Title, Text } = Typography;
const FONT = '"Garet", sans-serif';
const NAVY = '#2e4372';
const PURPLE = '#5C2472';

function AccessPanel({ apps, users }) {
    const { message } = App.useApp();
    const [selectedApp, setSelectedApp] = useState(null);
    const [roles, setRoles] = useState([]);
    const [roleUsers, setRoleUsers] = useState({}); // roleId -> [users]
    const [loading, setLoading] = useState(false);
    const [addValue, setAddValue] = useState({}); // roleId -> userId
    const [busy, setBusy] = useState(false);

    const loadRoles = useCallback(
        async (appId) => {
            if (!appId) return;
            setLoading(true);
            try {
                const rolesRes = await rolesAPI.listRoles({ application_id: appId, limit: 500 });
                const appRoles = rolesRes.items || [];
                setRoles(appRoles);
                const entries = await Promise.all(
                    appRoles.map(async (r) => [r.id, await rolesAPI.getRoleUsers(r.id)])
                );
                setRoleUsers(Object.fromEntries(entries));
            } catch {
                message.error('Error al cargar roles del sistema');
            } finally {
                setLoading(false);
            }
        },
        [message]
    );

    const handleSelectApp = (appId) => {
        setSelectedApp(appId);
        setAddValue({});
        loadRoles(appId);
    };

    const refreshRole = async (roleId) => {
        try {
            const list = await rolesAPI.getRoleUsers(roleId);
            setRoleUsers((prev) => ({ ...prev, [roleId]: list }));
        } catch {
            /* noop */
        }
    };

    const handleAddUser = async (roleId) => {
        const userId = addValue[roleId];
        if (!userId) {
            message.warning('Selecciona un usuario');
            return;
        }
        setBusy(true);
        try {
            await groupsAPI.assignRoleToUser(userId, roleId);
            message.success('Usuario agregado al rol');
            setAddValue((prev) => ({ ...prev, [roleId]: undefined }));
            await refreshRole(roleId);
        } catch (err) {
            message.error(formatApiError(err, 'Error al agregar usuario'));
        } finally {
            setBusy(false);
        }
    };

    const handleRemoveUser = async (roleId, userId) => {
        setBusy(true);
        try {
            await groupsAPI.removeRoleFromUser(userId, roleId);
            message.success('Usuario removido del rol');
            await refreshRole(roleId);
        } catch (err) {
            message.error(formatApiError(err, 'Error al remover usuario'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div>
            <Space wrap style={{ marginBottom: 16 }}>
                <Text strong style={{ fontFamily: FONT }}>
                    Sistema:
                </Text>
                <Select
                    style={{ minWidth: 280 }}
                    placeholder="Selecciona un sistema"
                    value={selectedApp}
                    onChange={handleSelectApp}
                    options={apps.map((a) => ({ label: a.name, value: a.id }))}
                />
                {selectedApp && (
                    <Button icon={<ReloadOutlined />} onClick={() => loadRoles(selectedApp)}>
                        Actualizar
                    </Button>
                )}
            </Space>

            {!selectedApp ? (
                <Empty
                    description="Selecciona un sistema para gestionar sus roles y accesos"
                    style={{ marginTop: 48 }}
                />
            ) : loading ? (
                <Spin style={{ display: 'block', marginTop: 48 }} />
            ) : roles.length === 0 ? (
                <Empty description="Este sistema no tiene roles" style={{ marginTop: 48 }} />
            ) : (
                <Row gutter={[16, 16]}>
                    {roles.map((role) => {
                        const assigned = roleUsers[role.id] || [];
                        const assignedIds = new Set(assigned.map((u) => u.id));
                        const available = users.filter((u) => !assignedIds.has(u.id));
                        return (
                            <Col xs={24} lg={12} key={role.id}>
                                <Card
                                    style={{ borderRadius: 12, height: '100%' }}
                                    styles={{ header: { fontFamily: FONT } }}
                                    title={
                                        <Space>
                                            <SafetyOutlined style={{ color: NAVY }} />
                                            <span>{role.name}</span>
                                            <Tag color={NAVY}>{role.slug}</Tag>
                                        </Space>
                                    }
                                >
                                    {role.description && (
                                        <Text
                                            type="secondary"
                                            style={{
                                                fontFamily: FONT,
                                                display: 'block',
                                                marginBottom: 12,
                                            }}
                                        >
                                            {role.description}
                                        </Text>
                                    )}

                                    <Text strong style={{ fontFamily: FONT, fontSize: 12 }}>
                                        Usuarios con acceso ({assigned.length})
                                    </Text>
                                    <div style={{ margin: '8px 0 16px' }}>
                                        {assigned.length === 0 ? (
                                            <Text type="secondary" style={{ fontSize: 12 }}>
                                                Sin usuarios asignados
                                            </Text>
                                        ) : (
                                            <Space size={[8, 8]} wrap>
                                                {assigned.map((u) => (
                                                    <Tag
                                                        key={u.id}
                                                        closable
                                                        closeIcon={<CloseOutlined />}
                                                        onClose={(e) => {
                                                            e.preventDefault();
                                                            handleRemoveUser(role.id, u.id);
                                                        }}
                                                        color={PURPLE}
                                                        style={{ padding: '2px 8px' }}
                                                    >
                                                        {u.full_name}
                                                    </Tag>
                                                ))}
                                            </Space>
                                        )}
                                    </div>

                                    <Space.Compact style={{ width: '100%' }}>
                                        <Select
                                            showSearch
                                            style={{ flex: 1 }}
                                            placeholder="Agregar usuario..."
                                            value={addValue[role.id]}
                                            onChange={(v) =>
                                                setAddValue((prev) => ({ ...prev, [role.id]: v }))
                                            }
                                            filterOption={(input, option) =>
                                                option?.label
                                                    ?.toLowerCase()
                                                    .includes(input.toLowerCase())
                                            }
                                            options={available.map((u) => ({
                                                label: `${u.full_name} (${u.email})`,
                                                value: u.id,
                                            }))}
                                        />
                                        <Button
                                            type="primary"
                                            icon={<UserAddOutlined />}
                                            loading={busy}
                                            onClick={() => handleAddUser(role.id)}
                                        >
                                            Agregar
                                        </Button>
                                    </Space.Compact>
                                </Card>
                            </Col>
                        );
                    })}
                </Row>
            )}
        </div>
    );
}

function VerifyPanel({ apps, users }) {
    const { message } = App.useApp();
    const [result, setResult] = useState(null);
    const [myPerms, setMyPerms] = useState(null);
    const [checkForm] = Form.useForm();
    const [meForm] = Form.useForm();

    const handleCheck = async (values) => {
        try {
            setResult(await authzAPI.checkPermission(values));
        } catch (err) {
            message.error(formatApiError(err, 'Error al verificar permiso'));
        }
    };

    const handleMePerms = async (values) => {
        try {
            setMyPerms(await authzAPI.getMePermissions(values.application_slug));
        } catch (err) {
            message.error(formatApiError(err, 'Error al consultar permisos'));
        }
    };

    return (
        <Row gutter={[24, 24]}>
            <Col xs={24} lg={12}>
                <Card title="Verificar permiso" styles={{ header: { fontFamily: FONT } }}>
                    <Form form={checkForm} layout="vertical" onFinish={handleCheck}>
                        <Form.Item name="user_id" label="Usuario" rules={[{ required: true }]}>
                            <Select
                                showSearch
                                placeholder="Seleccionar usuario"
                                filterOption={(input, option) =>
                                    option?.label?.toLowerCase().includes(input.toLowerCase())
                                }
                                options={users.map((u) => ({
                                    label: `${u.full_name} (${u.email})`,
                                    value: u.id,
                                }))}
                            />
                        </Form.Item>
                        <Form.Item
                            name="application_slug"
                            label="Sistema"
                            rules={[{ required: true }]}
                        >
                            <Select
                                placeholder="Seleccionar sistema"
                                options={apps.map((a) => ({ label: a.name, value: a.slug }))}
                            />
                        </Form.Item>
                        <Form.Item name="permission" label="Permiso" rules={[{ required: true }]}>
                            <Input placeholder="Ej. minerva.users.manage" />
                        </Form.Item>
                        <Button
                            type="primary"
                            htmlType="submit"
                            block
                            icon={<CheckCircleOutlined />}
                            style={{ borderRadius: 20 }}
                        >
                            Verificar
                        </Button>
                    </Form>

                    {result && (
                        <Card
                            size="small"
                            style={{
                                marginTop: 16,
                                background: result.allowed ? '#f6ffed' : '#fff2f0',
                            }}
                        >
                            <Space>
                                <Badge status={result.allowed ? 'success' : 'error'} />
                                <strong>{result.allowed ? 'PERMITIDO' : 'DENEGADO'}</strong>
                            </Space>
                            <p style={{ margin: '8px 0 0', fontSize: 12, color: '#8c8c8c' }}>
                                {result.reason}
                            </p>
                        </Card>
                    )}
                </Card>
            </Col>

            <Col xs={24} lg={12}>
                <Card title="Mis permisos por sistema" styles={{ header: { fontFamily: FONT } }}>
                    <Form form={meForm} layout="vertical" onFinish={handleMePerms}>
                        <Form.Item
                            name="application_slug"
                            label="Sistema"
                            rules={[{ required: true }]}
                        >
                            <Select
                                placeholder="Seleccionar sistema"
                                options={apps.map((a) => ({ label: a.name, value: a.slug }))}
                            />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" block style={{ borderRadius: 20 }}>
                            Consultar
                        </Button>
                    </Form>

                    {myPerms && (
                        <div style={{ marginTop: 16 }}>
                            <Descriptions column={1} size="small" bordered>
                                <Descriptions.Item label="Usuario">
                                    {myPerms.user_id}
                                </Descriptions.Item>
                                <Descriptions.Item label="Sistema">
                                    {myPerms.application_slug}
                                </Descriptions.Item>
                                <Descriptions.Item label="Roles">
                                    {(myPerms.roles || []).map((r) => (
                                        <Tag key={r.id || r.slug || r} color={NAVY}>
                                            {r.name || r.slug || r}
                                        </Tag>
                                    ))}
                                </Descriptions.Item>
                                <Descriptions.Item label="Permisos">
                                    {(myPerms.permissions || []).map((p) => (
                                        <Tag key={p.id || p.slug || p} color={PURPLE}>
                                            {p.slug || p}
                                        </Tag>
                                    ))}
                                </Descriptions.Item>
                            </Descriptions>
                        </div>
                    )}
                </Card>
            </Col>
        </Row>
    );
}

export default function AuthorizationPage() {
    const [apps, setApps] = useState([]);
    const [users, setUsers] = useState([]);

    useEffect(() => {
        (async () => {
            try {
                const [appsRes, usersRes] = await Promise.all([
                    appsAPI.listApplications({ limit: 100 }),
                    usersAPI.listUsers({ limit: 500 }),
                ]);
                setApps(appsRes.items || []);
                setUsers(usersRes.items || []);
            } catch {
                /* noop */
            }
        })();
    }, []);

    const items = [
        {
            key: 'access',
            label: 'Gestión de accesos',
            children: <AccessPanel apps={apps} users={users} />,
        },
        {
            key: 'verify',
            label: 'Verificación',
            children: <VerifyPanel apps={apps} users={users} />,
        },
    ];

    return (
        <div>
            <Title level={4} style={{ fontFamily: FONT }}>
                Autorización
            </Title>
            <Tabs items={items} />
        </div>
    );
}
