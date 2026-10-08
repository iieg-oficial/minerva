import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Modal, Form, Input, Select, Typography, Space, Tag, App } from 'antd';
import { PlusOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons';
import * as groupsAPI from '@/api/groups';
import * as usersAPI from '@/api/users';
import * as rolesAPI from '@/api/roles';
import { formatApiError } from '@/api/errors';

const { Title } = Typography;

export default function GroupsPage() {
    const [groups, setGroups] = useState([]);
    const [users, setUsers] = useState([]);
    const [allRoles, setAllRoles] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [memberModalOpen, setMemberModalOpen] = useState(false);
    const [editingGroup, setEditingGroup] = useState(null);
    const [selectedGroup, setSelectedGroup] = useState(null);
    const [form] = Form.useForm();
    const [editForm] = Form.useForm();
    const [memberForm] = Form.useForm();
    const { message } = App.useApp();
    const [page, setPage] = useState({ offset: 0, limit: 10 });

    const fetchGroups = useCallback(async () => {
        setLoading(true);
        try {
            const data = await groupsAPI.listGroups(page);
            setGroups(data.items || []);
            setTotal(data.total || 0);
        } catch {
            message.error('Error al cargar grupos');
        } finally {
            setLoading(false);
        }
    }, [page, message]);

    const fetchRefs = useCallback(async () => {
        try {
            const [usersRes, rolesRes] = await Promise.all([
                usersAPI.listUsers({ limit: 200 }),
                rolesAPI.listRoles({ limit: 200 }),
            ]);
            setUsers(usersRes.items || []);
            setAllRoles(rolesRes.items || []);
        } catch {}
    }, []);

    useEffect(() => {
        fetchGroups();
        fetchRefs();
    }, [fetchGroups, fetchRefs]);

    const handleCreate = async (values) => {
        try {
            await groupsAPI.createGroup(values);
            message.success('Grupo creado');
            setModalOpen(false);
            form.resetFields();
            fetchGroups();
        } catch (err) {
            message.error(formatApiError(err, 'Error al crear grupo'));
        }
    };

    const handleEdit = (group) => {
        setEditingGroup(group);
        editForm.setFieldsValue({ name: group.name, description: group.description });
        setModalOpen(true);
    };

    const handleUpdate = async (values) => {
        try {
            await groupsAPI.updateGroup(editingGroup.id, values);
            message.success('Grupo actualizado');
            setModalOpen(false);
            setEditingGroup(null);
            editForm.resetFields();
            fetchGroups();
        } catch (err) {
            message.error(formatApiError(err, 'Error al actualizar grupo'));
        }
    };

    const handleMemberOpen = (group) => {
        setSelectedGroup(group);
        setMemberModalOpen(true);
    };

    const handleAddUser = async (values) => {
        try {
            await groupsAPI.addUserToGroup(selectedGroup.id, values.user_id);
            message.success('Usuario agregado al grupo');
            memberForm.resetFields();
        } catch (err) {
            message.error(formatApiError(err, 'Error al agregar usuario'));
        }
    };

    const handleAddRole = async (values) => {
        try {
            await groupsAPI.addRoleToGroup(selectedGroup.id, values.role_id);
            message.success('Rol asignado al grupo');
        } catch (err) {
            message.error(formatApiError(err, 'Error al asignar rol'));
        }
    };

    const columns = [
        { title: 'Nombre', dataIndex: 'name', key: 'name' },
        { title: 'Slug', dataIndex: 'slug', key: 'slug' },
        {
            title: 'Origen',
            dataIndex: 'source',
            key: 'source',
            width: 80,
            render: (v) => (v ? <Tag>{v}</Tag> : <Tag color="#2e4372">local</Tag>),
        },
        {
            title: '',
            key: 'actions',
            width: 120,
            render: (_, record) => (
                <Space>
                    <Button type="link" size="small" onClick={() => handleMemberOpen(record)}>
                        Miembros
                    </Button>
                    <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => handleEdit(record)}
                    />
                </Space>
            ),
        },
    ];

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
                    Grupos
                </Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={fetchGroups}>
                        Actualizar
                    </Button>
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                            setEditingGroup(null);
                            form.resetFields();
                            setModalOpen(true);
                        }}
                    >
                        Nuevo grupo
                    </Button>
                </Space>
            </div>

            <Table
                columns={columns}
                dataSource={groups}
                rowKey="id"
                loading={loading}
                pagination={{
                    total,
                    current: Math.floor(page.offset / page.limit) + 1,
                    pageSize: page.limit,
                    onChange: (p, ps) => setPage({ offset: (p - 1) * ps, limit: ps }),
                }}
            />

            <Modal
                title={editingGroup ? 'Editar grupo' : 'Nuevo grupo'}
                open={modalOpen}
                onCancel={() => {
                    setModalOpen(false);
                    setEditingGroup(null);
                    form.resetFields();
                    editForm.resetFields();
                }}
                footer={null}
            >
                <Form
                    form={editingGroup ? editForm : form}
                    layout="vertical"
                    onFinish={editingGroup ? handleUpdate : handleCreate}
                >
                    <Form.Item name="name" label="Nombre" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    {!editingGroup && (
                        <>
                            <Form.Item name="slug" label="Slug" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item name="source" label="Origen">
                                <Input placeholder="Ej. ldap" />
                            </Form.Item>
                            <Form.Item name="external_group_id" label="ID externo">
                                <Input placeholder="ID del grupo en LDAP..." />
                            </Form.Item>
                        </>
                    )}
                    <Form.Item name="description" label="Descripción">
                        <Input.TextArea rows={2} />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" block style={{ borderRadius: 20 }}>
                        {editingGroup ? 'Guardar cambios' : 'Crear grupo'}
                    </Button>
                </Form>
            </Modal>

            <Modal
                title={`Miembros — ${selectedGroup?.name || ''}`}
                open={memberModalOpen}
                onCancel={() => setMemberModalOpen(false)}
                footer={null}
                width={500}
            >
                <div style={{ marginBottom: 16 }}>
                    <Title level={5}>Agregar usuario</Title>
                    <Form form={memberForm} layout="inline" onFinish={handleAddUser}>
                        <Form.Item
                            name="user_id"
                            rules={[{ required: true, message: 'Seleccione un usuario' }]}
                        >
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
                                style={{ width: 280 }}
                            />
                        </Form.Item>
                        <Form.Item>
                            <Button type="primary" htmlType="submit">
                                Agregar
                            </Button>
                        </Form.Item>
                    </Form>
                </div>

                <div>
                    <Title level={5}>Asignar rol al grupo</Title>
                    <Form layout="inline" onFinish={handleAddRole}>
                        <Form.Item
                            name="role_id"
                            rules={[{ required: true, message: 'Seleccione un rol' }]}
                        >
                            <Select
                                showSearch
                                placeholder="Seleccionar rol"
                                filterOption={(input, option) =>
                                    option?.label?.toLowerCase().includes(input.toLowerCase())
                                }
                                options={allRoles.map((r) => ({ label: r.name, value: r.id }))}
                                style={{ width: 280 }}
                            />
                        </Form.Item>
                        <Form.Item>
                            <Button type="primary" htmlType="submit">
                                Asignar
                            </Button>
                        </Form.Item>
                    </Form>
                </div>
            </Modal>
        </div>
    );
}
