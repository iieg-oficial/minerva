import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Modal, Form, Input, Select, Typography, Space, App } from 'antd';
import { PlusOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons';
import * as usersAPI from '@/api/users';

const { Title } = Typography;

const STATUS_OPTIONS = [
    { label: 'Activo', value: 'active' },
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
    const [form] = Form.useForm();
    const [editForm] = Form.useForm();
    const { message } = App.useApp();

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

    const handleCreate = async (values) => {
        try {
            await usersAPI.createUser(values);
            message.success('Usuario creado');
            setModalOpen(false);
            form.resetFields();
            fetchUsers();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al crear usuario');
        }
    };

    const handleEdit = (user) => {
        setEditingUser(user);
        editForm.setFieldsValue({
            full_name: user.full_name,
            email: user.email,
            password: '',
            status: user.status,
            domain: user.domain || '',
        });
        setModalOpen(true);
    };

    const handleUpdate = async (values) => {
        try {
            if (editingUser) {
                await usersAPI.updateUser(editingUser.id, values);
                message.success('Usuario actualizado');
            }
            setModalOpen(false);
            setEditingUser(null);
            form.resetFields();
            editForm.resetFields();
            fetchUsers();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al actualizar usuario');
        }
    };

    const handleStatusChange = async (userId, status) => {
        try {
            await usersAPI.updateUserStatus(userId, status);
            message.success('Estado actualizado');
            fetchUsers();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al cambiar estado');
        }
    };

    const columns = [
        { title: 'Nombre', dataIndex: 'full_name', key: 'full_name' },
        { title: 'Email', dataIndex: 'email', key: 'email' },
        { title: 'Proveedor', dataIndex: 'auth_provider', key: 'auth_provider', width: 100 },
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
            width: 60,
            render: (_, record) => (
                <Button type="text" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
            ),
        },
    ];

    const isEditMode = !!editingUser;

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Title level={4} style={{ margin: 0 }}>Usuarios</Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={fetchUsers}>Actualizar</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingUser(null); form.resetFields(); setModalOpen(true); }}>
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
                    onChange: (page, pageSize) => setPagination({ offset: (page - 1) * pageSize, limit: pageSize }),
                }}
            />

            <Modal
                title={isEditMode ? 'Editar usuario' : 'Nuevo usuario'}
                open={modalOpen}
                onCancel={() => { setModalOpen(false); setEditingUser(null); form.resetFields(); editForm.resetFields(); }}
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
                            <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item name="password" label="Contraseña">
                                <Input.Password placeholder="Opcional si es Google" />
                            </Form.Item>
                            <Form.Item name="auth_provider" label="Proveedor" initialValue="local">
                                <Select options={[{ label: 'Local', value: 'local' }, { label: 'Google', value: 'google' }]} />
                            </Form.Item>
                        </>
                    )}
                    {isEditMode && (
                        <>
                            <Form.Item name="full_name" label="Nombre" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item
                                name="password"
                                label="Nueva contraseña"
                                extra="Déjalo vacío para conservar la contraseña actual"
                            >
                                <Input.Password placeholder="••••••••" autoComplete="new-password" />
                            </Form.Item>
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
        </div>
    );
}
