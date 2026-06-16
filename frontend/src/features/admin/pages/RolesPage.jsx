import { useState, useEffect, useCallback } from 'react';
import {
    Table, Button, Modal, Form, Input, Select, Typography, Space, Tag, App,
    Collapse, Checkbox, Empty, Spin,
} from 'antd';
import {
    PlusOutlined, EditOutlined, DeleteOutlined, SafetyOutlined, ReloadOutlined, KeyOutlined,
} from '@ant-design/icons';
import * as rolesAPI from '@/api/roles';
import * as appsAPI from '@/api/applications';
import * as permsAPI from '@/api/permissions';

const { Title, Text } = Typography;
const FONT = '"Garet", sans-serif';
const NAVY = '#2e4372';
const PURPLE = '#5C2472';

export default function RolesPage() {
    const [roles, setRoles] = useState([]);
    const [apps, setApps] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [permModalOpen, setPermModalOpen] = useState(false);
    const [editingRole, setEditingRole] = useState(null);
    const [selectedRole, setSelectedRole] = useState(null);
    const [appPerms, setAppPerms] = useState([]);
    const [assignedPerms, setAssignedPerms] = useState([]);
    const [permLoading, setPermLoading] = useState(false);
    const [savingPerm, setSavingPerm] = useState(null);
    const [form] = Form.useForm();
    const [editForm] = Form.useForm();
    const { message } = App.useApp();

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [rolesRes, appsRes] = await Promise.all([
                rolesAPI.listRoles({ limit: 500 }),
                appsAPI.listApplications({ limit: 100 }),
            ]);
            setRoles(rolesRes.items || []);
            setApps(appsRes.items || []);
        } catch {
            message.error('Error al cargar roles');
        } finally {
            setLoading(false);
        }
    }, [message]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleCreate = async (values) => {
        try {
            await rolesAPI.createRole(values.application_id, { name: values.name, slug: values.slug, description: values.description });
            message.success('Rol creado');
            setModalOpen(false);
            form.resetFields();
            fetchData();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al crear rol');
        }
    };

    const handleEdit = (role) => {
        setEditingRole(role);
        editForm.setFieldsValue({ name: role.name, description: role.description });
        setModalOpen(true);
    };

    const handleUpdate = async (values) => {
        try {
            await rolesAPI.updateRole(editingRole.id, values);
            message.success('Rol actualizado');
            setModalOpen(false);
            setEditingRole(null);
            editForm.resetFields();
            fetchData();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al actualizar rol');
        }
    };

    const handleDelete = (role) => {
        Modal.confirm({
            title: '¿Eliminar rol?',
            content: `Se eliminará "${role.name}". Esta acción no se puede deshacer.`,
            okText: 'Eliminar',
            okType: 'danger',
            onOk: async () => {
                try {
                    await rolesAPI.deleteRole(role.id);
                    message.success('Rol eliminado');
                    fetchData();
                } catch (err) {
                    message.error(err.response?.data?.detail || 'Error al eliminar rol');
                }
            },
        });
    };

    const handlePermOpen = async (role) => {
        setSelectedRole(role);
        setPermModalOpen(true);
        setPermLoading(true);
        setAppPerms([]);
        setAssignedPerms([]);
        try {
            const [rolePerms, allPermsRes] = await Promise.all([
                rolesAPI.getRolePermissions(role.id),       // devuelve una lista plana
                permsAPI.listPermissions({ application_id: role.application_id, limit: 500 }),
            ]);
            setAssignedPerms((rolePerms || []).map((p) => p.id));
            setAppPerms(allPermsRes.items || []);
        } catch {
            message.error('Error al cargar permisos');
        } finally {
            setPermLoading(false);
        }
    };

    // Activa/desactiva un permiso del rol y persiste el cambio de inmediato.
    const togglePerm = async (permId, checked) => {
        setSavingPerm(permId);
        try {
            if (checked) {
                await rolesAPI.assignPermissionToRole(selectedRole.id, permId);
                setAssignedPerms((prev) => [...prev, permId]);
            } else {
                await rolesAPI.removePermissionFromRole(selectedRole.id, permId);
                setAssignedPerms((prev) => prev.filter((id) => id !== permId));
            }
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al actualizar permisos');
        } finally {
            setSavingPerm(null);
        }
    };

    const columns = [
        { title: 'Nombre', dataIndex: 'name', key: 'name', width: 200 },
        {
            title: 'Slug', dataIndex: 'slug', key: 'slug',
            render: (slug) => <Tag color={NAVY}>{slug}</Tag>,
        },
        {
            title: 'Descripción', dataIndex: 'description', key: 'description',
            render: (d) => d || <Text type="secondary">—</Text>,
        },
        {
            title: '', key: 'actions', width: 130,
            render: (_, record) => (
                <Space>
                    <Button type="text" size="small" icon={<SafetyOutlined />}
                        title="Administrar permisos" onClick={() => handlePermOpen(record)} />
                    <Button type="text" size="small" icon={<EditOutlined />}
                        title="Editar" onClick={() => handleEdit(record)} />
                    <Button type="text" size="small" icon={<DeleteOutlined />} danger
                        title="Eliminar" onClick={() => handleDelete(record)} />
                </Space>
            ),
        },
    ];

    // Agrupa los roles por aplicación (sistema)
    const groups = apps
        .map((app) => ({ app, roles: roles.filter((r) => r.application_id === app.id) }))
        .filter((g) => g.roles.length > 0);

    const knownAppIds = new Set(apps.map((a) => a.id));
    const orphan = roles.filter((r) => !knownAppIds.has(r.application_id));

    const collapseItems = [
        ...groups.map((g) => ({
            key: g.app.id,
            label: (
                <Space>
                    <SafetyOutlined style={{ color: NAVY }} />
                    <Text strong style={{ fontFamily: FONT }}>{g.app.name}</Text>
                    <Tag>{g.roles.length}</Tag>
                </Space>
            ),
            children: <Table columns={columns} dataSource={g.roles} rowKey="id" size="small" pagination={false} />,
        })),
        ...(orphan.length > 0 ? [{
            key: '__orphan__',
            label: (
                <Space>
                    <SafetyOutlined />
                    <Text strong style={{ fontFamily: FONT }}>Sin sistema asociado</Text>
                    <Tag>{orphan.length}</Tag>
                </Space>
            ),
            children: <Table columns={columns} dataSource={orphan} rowKey="id" size="small" pagination={false} />,
        }] : []),
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Title level={4} style={{ margin: 0, fontFamily: FONT }}>Roles</Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={fetchData}>Actualizar</Button>
                    <Button type="primary" icon={<PlusOutlined />}
                        onClick={() => { setEditingRole(null); form.resetFields(); setModalOpen(true); }}>
                        Nuevo rol
                    </Button>
                </Space>
            </div>

            {loading ? (
                <Spin style={{ display: 'block', marginTop: 48 }} />
            ) : collapseItems.length === 0 ? (
                <Empty description="No hay roles" style={{ marginTop: 48 }} />
            ) : (
                <Collapse
                    items={collapseItems}
                    defaultActiveKey={collapseItems.map((i) => i.key)}
                    style={{ fontFamily: FONT, background: 'transparent' }}
                />
            )}

            <Modal
                title={editingRole ? 'Editar rol' : 'Nuevo rol'}
                open={modalOpen}
                onCancel={() => { setModalOpen(false); setEditingRole(null); form.resetFields(); editForm.resetFields(); }}
                footer={null}
            >
                <Form form={editingRole ? editForm : form} layout="vertical" onFinish={editingRole ? handleUpdate : handleCreate}>
                    <Form.Item name="name" label="Nombre" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    {!editingRole && (
                        <>
                            <Form.Item name="slug" label="Slug" rules={[{ required: true }]}>
                                <Input placeholder="Ej. minerva.editor" />
                            </Form.Item>
                            <Form.Item name="application_id" label="Sistema" rules={[{ required: true }]}>
                                <Select options={apps.map((a) => ({ label: a.name, value: a.id }))} />
                            </Form.Item>
                        </>
                    )}
                    <Form.Item name="description" label="Descripción">
                        <Input.TextArea rows={2} />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" block style={{ borderRadius: 20 }}>
                        {editingRole ? 'Guardar cambios' : 'Crear rol'}
                    </Button>
                </Form>
            </Modal>

            <Modal
                title={
                    <Space>
                        <KeyOutlined style={{ color: PURPLE }} />
                        <span>Permisos del rol: {selectedRole?.name || ''}</span>
                    </Space>
                }
                open={permModalOpen}
                onCancel={() => setPermModalOpen(false)}
                footer={<Button onClick={() => setPermModalOpen(false)}>Cerrar</Button>}
                width={520}
            >
                {permLoading ? (
                    <Spin style={{ display: 'block', margin: '32px auto' }} />
                ) : appPerms.length === 0 ? (
                    <Empty description="Este sistema no tiene permisos declarados" />
                ) : (
                    <>
                        <Text type="secondary" style={{ fontFamily: FONT }}>
                            Marca los permisos que tendrá este rol. Los cambios se guardan automáticamente.
                        </Text>
                        <div style={{ marginTop: 12, maxHeight: 400, overflowY: 'auto', paddingRight: 8 }}>
                            <Space direction="vertical" size={10} style={{ width: '100%' }}>
                                {appPerms.map((p) => (
                                    <Checkbox
                                        key={p.id}
                                        checked={assignedPerms.includes(p.id)}
                                        disabled={savingPerm === p.id}
                                        onChange={(e) => togglePerm(p.id, e.target.checked)}
                                    >
                                        <Space size={6}>
                                            <Text style={{ fontFamily: FONT }}>{p.name}</Text>
                                            <Tag color={PURPLE} style={{ marginInlineEnd: 0 }}>{p.slug}</Tag>
                                        </Space>
                                    </Checkbox>
                                ))}
                            </Space>
                        </div>
                    </>
                )}
            </Modal>
        </div>
    );
}
