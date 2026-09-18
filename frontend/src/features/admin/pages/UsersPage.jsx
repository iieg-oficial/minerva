import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Modal, Form, Input, Select, Typography, Space, App, Divider, Popconfirm } from 'antd';
import {
    PlusOutlined,
    EditOutlined,
    ReloadOutlined,
    DeleteOutlined,
    LinkOutlined,
} from '@ant-design/icons';
import * as usersAPI from '@/api/users';
import * as applicationsAPI from '@/api/applications';
import * as rolesAPI from '@/api/roles';
import { assignRoleToUser } from '@/api/groups';
import { formatApiError } from '@/api/errors';

const { Title, Paragraph, Text } = Typography;

const STATUS_OPTIONS = [
    { label: 'Activo', value: 'active' },
    // Solo lo asigna el alta por invitación; se muestra pero no se puede elegir a mano.
    { label: 'Pendiente', value: 'pending', disabled: true },
    { label: 'Inactivo', value: 'inactive' },
    { label: 'Suspendido', value: 'suspended' },
];

export default function UsersPage() {
    const [users, setUsers] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [pagination, setPagination] = useState({ offset: 0, limit: 10 });
    const [applications, setApplications] = useState([]);
    const [roles, setRoles] = useState([]);
    // Enlace recién emitido ({ email, url, purpose, expires_at }): se muestra una sola vez.
    const [credentialLink, setCredentialLink] = useState(null);
    const [form] = Form.useForm();
    const [editForm] = Form.useForm();
    const { message } = App.useApp();
    const roleAssignments = Form.useWatch('roleAssignments', form) || [];

    const fetchUsers = useCallback(async () => {
        setLoading(true);
        try {
            const data = await usersAPI.listUsers(pagination);
            setUsers(data.items || []);
            setTotal(data.total || 0);
        } catch {
            message.error('Error al cargar usuarios');
        } finally {
            setLoading(false);
        }
    }, [pagination, message]);

    useEffect(() => {
        fetchUsers();
    }, [fetchUsers]);

    useEffect(() => {
        // Se precargan para el selector de "Aplicaciones y roles" al crear un usuario.
        Promise.all([
            applicationsAPI.listApplications({ limit: 100 }),
            rolesAPI.listRoles({ limit: 500 }),
        ])
            .then(([appsData, rolesData]) => {
                setApplications(appsData.items || []);
                setRoles(rolesData.items || []);
            })
            .catch(() => message.error('Error al cargar aplicaciones y roles'));
    }, [message]);

    const handleCreate = async (values) => {
        const { roleAssignments, ...userData } = values;
        try {
            // Sin contraseña (o borrada) el alta es por invitación: no se manda el campo vacío.
            const user = await usersAPI.createUser(userData);
            const roleIds = (roleAssignments || []).map((a) => a?.role_id).filter(Boolean);
            for (const roleId of roleIds) {
                try {
                    await assignRoleToUser(user.id, roleId);
                } catch {
                    message.warning('El usuario se creó, pero un rol no pudo asignarse');
                }
            }
            message.success('Usuario creado');
            setModalOpen(false);
            form.resetFields();
            fetchUsers();
            if (user.credential_link) {
                setCredentialLink({ email: user.email, ...user.credential_link });
            }
        } catch (err) {
            message.error(formatApiError(err, 'Error al crear usuario'));
        }
    };

    const handleEdit = (user) => {
        setEditingUser(user);
        editForm.setFieldsValue({
            full_name: user.full_name,
            email: user.email,
            status: user.status,
            domain: user.domain || '',
        });
        setModalOpen(true);
    };

    const handleUpdate = async (values) => {
        // El admin no fija contraseñas: solo datos del usuario. La credencial va por enlace.
        const payload = values;
        try {
            if (editingUser) {
                await usersAPI.updateUser(editingUser.id, payload);
                message.success('Usuario actualizado');
            }
            setModalOpen(false);
            setEditingUser(null);
            form.resetFields();
            editForm.resetFields();
            fetchUsers();
        } catch (err) {
            message.error(formatApiError(err, 'Error al actualizar usuario'));
        }
    };

    const handleIssueLink = async (user) => {
        try {
            const link = await usersAPI.createCredentialLink(user.id);
            setCredentialLink({ email: user.email, ...link });
        } catch (err) {
            message.error(formatApiError(err, 'No se pudo generar el enlace'));
        }
    };

    const handleStatusChange = async (userId, status) => {
        try {
            await usersAPI.updateUserStatus(userId, status);
            message.success('Estado actualizado');
            fetchUsers();
        } catch (err) {
            message.error(formatApiError(err, 'Error al cambiar estado'));
        }
    };

    const columns = [
        { title: 'Nombre', dataIndex: 'full_name', key: 'full_name' },
        { title: 'Email', dataIndex: 'email', key: 'email' },
        {
            title: 'Estado',
            dataIndex: 'status',
            key: 'status',
            width: 120,
            render: (status, record) => (
                <Select
                    value={status}
                    size="small"
                    style={{ width: 110 }}
                    options={STATUS_OPTIONS}
                    onChange={(val) => handleStatusChange(record.id, val)}
                />
            ),
        },
        {
            title: 'Creado',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 120,
            render: (v) => v?.slice(0, 10),
        },
        {
            title: '',
            key: 'actions',
            width: 90,
            render: (_, record) => (
                <Space size={0}>
                    <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        aria-label="Editar usuario"
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title={
                            record.status === 'pending'
                                ? '¿Generar un nuevo enlace de invitación?'
                                : '¿Generar un enlace para restablecer la contraseña?'
                        }
                        description="Cualquier enlace anterior de este usuario dejará de funcionar."
                        okText="Generar"
                        cancelText="Cancelar"
                        onConfirm={() => handleIssueLink(record)}
                    >
                        <Button
                            type="text"
                            size="small"
                            icon={<LinkOutlined />}
                            aria-label="Generar enlace de contraseña"
                        />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    const isEditMode = !!editingUser;

    return (
        <div>
            <div
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 16,
                }}
            >
                <Title level={4} style={{ margin: 0 }}>
                    Usuarios
                </Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={fetchUsers}>
                        Actualizar
                    </Button>
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                            setEditingUser(null);
                            form.resetFields();
                            setModalOpen(true);
                        }}
                    >
                        Nuevo usuario
                    </Button>
                </Space>
            </div>

            <Table
                columns={columns}
                dataSource={users}
                rowKey="id"
                loading={loading}
                pagination={{
                    total,
                    current: Math.floor(pagination.offset / pagination.limit) + 1,
                    pageSize: pagination.limit,
                    onChange: (page, pageSize) =>
                        setPagination({ offset: (page - 1) * pageSize, limit: pageSize }),
                }}
            />

            <Modal
                title={isEditMode ? 'Editar usuario' : 'Nuevo usuario'}
                open={modalOpen}
                onCancel={() => {
                    setModalOpen(false);
                    setEditingUser(null);
                    form.resetFields();
                    editForm.resetFields();
                }}
                footer={null}
            >
                <Form
                    form={isEditMode ? editForm : form}
                    layout="vertical"
                    onFinish={isEditMode ? handleUpdate : handleCreate}
                >
                    {!isEditMode && (
                        <>
                            <Form.Item name="full_name" label="Nombre" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item
                                name="email"
                                label="Email"
                                rules={[{ required: true, type: 'email' }]}
                            >
                                <Input />
                            </Form.Item>
                            {/* Sin campo de contraseña: al crear se emite un enlace de
                                invitación para que la persona defina la suya. */}
                            <Divider style={{ margin: '8px 0 16px' }}>
                                Aplicaciones y roles (opcional)
                            </Divider>
                            <Form.List name="roleAssignments">
                                {(fields, { add, remove }) => (
                                    <>
                                        {fields.map(({ key, name, ...restField }) => {
                                            const applicationId =
                                                roleAssignments[name]?.application_id;
                                            const roleOptions = roles
                                                .filter((r) => r.application_id === applicationId)
                                                .map((r) => ({ label: r.name, value: r.id }));
                                            return (
                                                <Space
                                                    key={key}
                                                    align="baseline"
                                                    style={{ display: 'flex', marginBottom: 8 }}
                                                >
                                                    <Form.Item
                                                        {...restField}
                                                        name={[name, 'application_id']}
                                                        rules={[
                                                            {
                                                                required: true,
                                                                message:
                                                                    'Selecciona una aplicación',
                                                            },
                                                        ]}
                                                    >
                                                        <Select
                                                            placeholder="Aplicación"
                                                            style={{ width: 160 }}
                                                            options={applications.map((a) => ({
                                                                label: a.name,
                                                                value: a.id,
                                                            }))}
                                                            onChange={() =>
                                                                form.setFieldValue(
                                                                    [
                                                                        'roleAssignments',
                                                                        name,
                                                                        'role_id',
                                                                    ],
                                                                    undefined
                                                                )
                                                            }
                                                        />
                                                    </Form.Item>
                                                    <Form.Item
                                                        {...restField}
                                                        name={[name, 'role_id']}
                                                        rules={[
                                                            {
                                                                required: true,
                                                                message: 'Selecciona un rol',
                                                            },
                                                        ]}
                                                    >
                                                        <Select
                                                            placeholder="Rol"
                                                            style={{ width: 160 }}
                                                            disabled={!applicationId}
                                                            options={roleOptions}
                                                        />
                                                    </Form.Item>
                                                    <Button
                                                        type="text"
                                                        icon={<DeleteOutlined />}
                                                        onClick={() => remove(name)}
                                                    />
                                                </Space>
                                            );
                                        })}
                                        <Form.Item>
                                            <Button
                                                type="dashed"
                                                onClick={() => add()}
                                                block
                                                icon={<PlusOutlined />}
                                            >
                                                Agregar aplicación
                                            </Button>
                                        </Form.Item>
                                    </>
                                )}
                            </Form.List>
                        </>
                    )}
                    {isEditMode && (
                        <>
                            <Form.Item name="full_name" label="Nombre" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item
                                name="email"
                                label="Email"
                                rules={[{ required: true, type: 'email' }]}
                            >
                                <Input />
                            </Form.Item>
                            {/* La contraseña no se edita aquí: se restablece con el botón de
                                enlace de la lista, que la persona usa para definir la suya. */}
                            <Form.Item name="status" label="Estado">
                                <Select options={STATUS_OPTIONS} />
                            </Form.Item>
                            <Form.Item name="domain" label="Dominio">
                                <Input placeholder="Ej. iieg.gob.mx" />
                            </Form.Item>
                        </>
                    )}
                    <Button type="primary" htmlType="submit" block style={{ borderRadius: 20 }}>
                        {isEditMode ? 'Guardar cambios' : 'Crear usuario'}
                    </Button>
                </Form>
            </Modal>

            <Modal
                title={
                    credentialLink?.purpose === 'invite'
                        ? 'Enlace de invitación'
                        : 'Enlace para restablecer la contraseña'
                }
                open={!!credentialLink}
                onCancel={() => setCredentialLink(null)}
                footer={
                    <Button type="primary" onClick={() => setCredentialLink(null)}>
                        Listo
                    </Button>
                }
            >
                {credentialLink && (
                    <>
                        <Paragraph>
                            Entrega este enlace a <Text strong>{credentialLink.email}</Text> para
                            que defina su contraseña. Es de un solo uso y vence el{' '}
                            {new Date(credentialLink.expires_at).toLocaleString('es-MX')}.
                        </Paragraph>
                        <Paragraph
                            code
                            copyable={{ text: credentialLink.url }}
                            style={{ wordBreak: 'break-all' }}
                        >
                            {credentialLink.url}
                        </Paragraph>
                        <Text type="secondary">
                            No se podrá volver a consultar: si se pierde, genera uno nuevo desde la
                            lista de usuarios.
                        </Text>
                    </>
                )}
            </Modal>
        </div>
    );
}
