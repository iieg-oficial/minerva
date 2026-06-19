import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Modal, Form, Input, Select, Typography, Space, Tag, App, Alert, Divider } from 'antd';
import { PlusOutlined, EditOutlined, LinkOutlined, ReloadOutlined, KeyOutlined } from '@ant-design/icons';
import * as appsAPI from '@/api/applications';
import ManifestUploadButton from '@features/admin/components/ManifestUploadButton';

const { Title } = Typography;

export default function ApplicationsPage() {
    const [apps, setApps] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingApp, setEditingApp] = useState(null);
    const [uriModalOpen, setUriModalOpen] = useState(false);
    const [uris, setUris] = useState([]);
    const [selectedApp, setSelectedApp] = useState(null);
    const [pagination, setPagination] = useState({ offset: 0, limit: 10 });
    const [form] = Form.useForm();
    const [editForm] = Form.useForm();
    const [uriForm] = Form.useForm();
    const { message } = App.useApp();

    const fetchApps = useCallback(async () => {
        setLoading(true);
        try {
            const data = await appsAPI.listApplications(pagination);
            setApps(data.items || []);
            setTotal(data.total || 0);
        } catch {
            message.error('Error al cargar aplicaciones');
        } finally {
            setLoading(false);
        }
    }, [pagination, message]);

    useEffect(() => { fetchApps(); }, [fetchApps]);

    // El client_secret solo viaja en la respuesta de creación/regeneración y no
    // se vuelve a poder consultar: hay que mostrarlo aquí para que el admin lo copie.
    const showCredentials = (result, { isNew }) => {
        Modal.success({
            title: isNew ? 'Aplicación creada' : 'Nuevo client secret generado',
            width: 540,
            content: (
                <div>
                    <Alert
                        type="warning"
                        showIcon
                        style={{ marginBottom: 16 }}
                        message="Guarda el client secret ahora"
                        description="Por seguridad no se vuelve a mostrar. Si lo pierdes, tendrás que regenerarlo."
                    />
                    <Typography.Paragraph style={{ marginBottom: 4 }}><strong>Client ID</strong></Typography.Paragraph>
                    <Typography.Paragraph copyable={{ text: result.client_id }} style={{ marginBottom: 16 }}>
                        <Typography.Text code>{result.client_id}</Typography.Text>
                    </Typography.Paragraph>
                    <Typography.Paragraph style={{ marginBottom: 4 }}><strong>Client Secret</strong></Typography.Paragraph>
                    <Typography.Paragraph copyable={{ text: result.client_secret_hash }} style={{ marginBottom: 0 }}>
                        <Typography.Text code>{result.client_secret_hash}</Typography.Text>
                    </Typography.Paragraph>
                </div>
            ),
        });
    };

    const handleCreate = async (values) => {
        try {
            const result = await appsAPI.createApplication(values);
            message.success('Aplicación creada');
            showCredentials(result, { isNew: true });
            setModalOpen(false);
            form.resetFields();
            fetchApps();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al crear aplicación');
        }
    };

    const handleRegenerateSecret = (record) => {
        Modal.confirm({
            title: `¿Regenerar el client secret de "${record.name}"?`,
            content: 'El secret anterior dejará de funcionar. El client_id no cambia; deberás actualizar el sistema consumidor con el nuevo secret.',
            okText: 'Regenerar',
            okButtonProps: { danger: true },
            cancelText: 'Cancelar',
            onOk: async () => {
                try {
                    const result = await appsAPI.regenerateSecret(record.id);
                    message.success('Client secret regenerado');
                    showCredentials(result, { isNew: false });
                } catch (err) {
                    message.error(err.response?.data?.detail || 'Error al regenerar el secret');
                }
            },
        });
    };

    const handleEdit = (app) => {
        setEditingApp(app);
        editForm.setFieldsValue({ name: app.name, description: app.description, homepage_url: app.homepage_url, status: app.status });
        setModalOpen(true);
    };

    const handleUpdate = async (values) => {
        try {
            await appsAPI.updateApplication(editingApp.id, values);
            message.success('Aplicación actualizada');
            setModalOpen(false);
            setEditingApp(null);
            editForm.resetFields();
            fetchApps();
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al actualizar aplicación');
        }
    };

    const handleUriOpen = async (app) => {
        setSelectedApp(app);
        try {
            const data = await appsAPI.listRedirectUris(app.id);
            setUris(data.items || []);
        } catch {
            setUris([]);
        }
        setUriModalOpen(true);
    };

    const handleAddUri = async (values) => {
        try {
            await appsAPI.addRedirectUri(selectedApp.id, values);
            message.success('URI agregada');
            uriForm.resetFields();
            const data = await appsAPI.listRedirectUris(selectedApp.id);
            setUris(data.items || []);
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al agregar URI');
        }
    };

    const columns = [
        { title: 'Nombre', dataIndex: 'name', key: 'name' },
        { title: 'Slug', dataIndex: 'slug', key: 'slug' },
        { title: 'Client ID', dataIndex: 'client_id', key: 'client_id', width: 200, ellipsis: true },
        {
            title: 'Estado', dataIndex: 'status', key: 'status', width: 100,
            render: (v) => <Tag color={v === 'active' ? 'green' : 'default'}>{v}</Tag>,
        },
        {
            title: '', key: 'actions', width: 130,
            render: (_, record) => (
                <Space>
                    <Button type="text" size="small" icon={<LinkOutlined />} title="Redirect URIs" onClick={() => handleUriOpen(record)} />
                    <Button type="text" size="small" icon={<KeyOutlined />} title="Regenerar client secret" onClick={() => handleRegenerateSecret(record)} />
                    <Button type="text" size="small" icon={<EditOutlined />} title="Editar" onClick={() => handleEdit(record)} />
                </Space>
            ),
        },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Title level={4} style={{ margin: 0 }}>Aplicaciones</Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={fetchApps}>Actualizar</Button>
                    <ManifestUploadButton onImported={fetchApps} />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingApp(null); form.resetFields(); setModalOpen(true); }}>
                        Nueva aplicación
                    </Button>
                </Space>
            </div>

            <Table columns={columns} dataSource={apps} rowKey="id" loading={loading}
                pagination={{
                    total, current: Math.floor(pagination.offset / pagination.limit) + 1,
                    pageSize: pagination.limit,
                    onChange: (p, ps) => setPagination({ offset: (p - 1) * ps, limit: ps }),
                }}
            />

            <Modal
                title={editingApp ? 'Editar aplicación' : 'Nueva aplicación'}
                open={modalOpen}
                onCancel={() => { setModalOpen(false); setEditingApp(null); form.resetFields(); editForm.resetFields(); }}
                footer={null}
            >
                {!editingApp && (
                    <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                        message="¿Tienes el manifiesto del sistema?"
                        description={
                            <Space direction="vertical" size={8}>
                                <span>Puedes dar de alta la aplicación junto con sus permisos y roles subiendo su manifest.minerva.yml.</span>
                                <ManifestUploadButton onImported={() => { setModalOpen(false); fetchApps(); }}>
                                    Crear desde manifiesto
                                </ManifestUploadButton>
                            </Space>
                        }
                    />
                )}
                {!editingApp && <Divider style={{ margin: '0 0 16px' }}>o captura manualmente</Divider>}
                <Form form={editingApp ? editForm : form} layout="vertical" onFinish={editingApp ? handleUpdate : handleCreate}>
                    {!editingApp && (
                        <>
                            <Form.Item name="name" label="Nombre" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item name="slug" label="Slug" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item name="description" label="Descripción">
                                <Input.TextArea rows={2} />
                            </Form.Item>
                            <Form.Item name="homepage_url" label="URL Homepage">
                                <Input placeholder="https://..." />
                            </Form.Item>
                        </>
                    )}
                    {editingApp && (
                        <>
                            <Form.Item name="name" label="Nombre" rules={[{ required: true }]}>
                                <Input />
                            </Form.Item>
                            <Form.Item name="description" label="Descripción">
                                <Input.TextArea rows={2} />
                            </Form.Item>
                            <Form.Item name="homepage_url" label="URL Homepage">
                                <Input placeholder="https://..." />
                            </Form.Item>
                            <Form.Item name="status" label="Estado">
                                <Select options={[{ label: 'Activo', value: 'active' }, { label: 'Inactivo', value: 'inactive' }]} />
                            </Form.Item>
                        </>
                    )}
                    <Button type="primary" htmlType="submit" block style={{ borderRadius: 20 }}>
                        {editingApp ? 'Guardar cambios' : 'Crear aplicación'}
                    </Button>
                </Form>
            </Modal>

            <Modal
                title={`Redirect URIs — ${selectedApp?.name || ''}`}
                open={uriModalOpen}
                onCancel={() => setUriModalOpen(false)}
                footer={null}
            >
                <Table columns={[
                    { title: 'URI', dataIndex: 'uri', key: 'uri' },
                    { title: 'Entorno', dataIndex: 'environment', key: 'environment', width: 100 },
                ]} dataSource={uris} rowKey="id" size="small" pagination={false} style={{ marginBottom: 16 }} />
                <Form form={uriForm} layout="inline" onFinish={handleAddUri}>
                    <Form.Item name="uri" rules={[{ required: true, type: 'url' }]}>
                        <Input placeholder="https://app.com/callback" style={{ width: 280 }} />
                    </Form.Item>
                    <Form.Item name="environment" initialValue="production">
                        <Select options={[{ label: 'Production', value: 'production' }, { label: 'Development', value: 'development' }]} style={{ width: 130 }} />
                    </Form.Item>
                    <Form.Item>
                        <Button type="primary" htmlType="submit">Agregar</Button>
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
