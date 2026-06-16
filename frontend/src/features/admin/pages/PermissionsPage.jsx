import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Typography, Space, Tag, Card, Alert, Collapse, Empty, Spin, App } from 'antd';
import { ReloadOutlined, KeyOutlined, InfoCircleOutlined } from '@ant-design/icons';
import * as permsAPI from '@/api/permissions';
import * as appsAPI from '@/api/applications';
import ManifestUploadButton from '@features/admin/components/ManifestUploadButton';

const { Title, Text } = Typography;
const FONT = '"Garet", sans-serif';
const PURPLE = '#5C2472';

export default function PermissionsPage() {
    const [perms, setPerms] = useState([]);
    const [apps, setApps] = useState([]);
    const [loading, setLoading] = useState(false);
    const { message } = App.useApp();

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [permsRes, appsRes] = await Promise.all([
                permsAPI.listPermissions({ limit: 500 }),
                appsAPI.listApplications({ limit: 100 }),
            ]);
            setPerms(permsRes.items || []);
            setApps(appsRes.items || []);
        } catch {
            message.error('Error al cargar permisos');
        } finally {
            setLoading(false);
        }
    }, [message]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const columns = [
        { title: 'Nombre', dataIndex: 'name', key: 'name', width: 220 },
        {
            title: 'Slug', dataIndex: 'slug', key: 'slug',
            render: (slug) => <Tag color={PURPLE}>{slug}</Tag>,
        },
        {
            title: 'Descripción', dataIndex: 'description', key: 'description',
            render: (d) => d || <Text type="secondary">—</Text>,
        },
    ];

    // Agrupa los permisos por aplicación (sistema)
    const groups = apps
        .map((app) => ({
            app,
            perms: perms.filter((p) => p.application_id === app.id),
        }))
        .filter((g) => g.perms.length > 0);

    // Permisos sin aplicación conocida
    const knownAppIds = new Set(apps.map((a) => a.id));
    const orphan = perms.filter((p) => !knownAppIds.has(p.application_id));

    const collapseItems = [
        ...groups.map((g) => ({
            key: g.app.id,
            label: (
                <Space>
                    <KeyOutlined style={{ color: PURPLE }} />
                    <Text strong style={{ fontFamily: FONT }}>{g.app.name}</Text>
                    <Tag>{g.perms.length}</Tag>
                </Space>
            ),
            children: (
                <Table
                    columns={columns}
                    dataSource={g.perms}
                    rowKey="id"
                    size="small"
                    pagination={false}
                />
            ),
        })),
        ...(orphan.length > 0 ? [{
            key: '__orphan__',
            label: (
                <Space>
                    <KeyOutlined />
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
                <Title level={4} style={{ margin: 0, fontFamily: FONT }}>Permisos</Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={fetchData}>Actualizar</Button>
                    <ManifestUploadButton type="primary" onImported={fetchData}>
                        Cargar manifiesto
                    </ManifestUploadButton>
                </Space>
            </div>

            <Alert
                type="info"
                showIcon
                icon={<InfoCircleOutlined />}
                style={{ marginBottom: 16, fontFamily: FONT }}
                message="Los permisos no se crean ni editan en Minerva"
                description="Cada sistema declara sus permisos mediante su manifiesto. Aquí solo se consultan, agrupados por sistema, para evitar inconsistencias."
            />

            {loading ? (
                <Spin style={{ display: 'block', marginTop: 48 }} />
            ) : collapseItems.length === 0 ? (
                <Card style={{ borderRadius: 12 }}>
                    <Empty description="No hay permisos cargados" />
                </Card>
            ) : (
                <Collapse
                    items={collapseItems}
                    defaultActiveKey={collapseItems.map((i) => i.key)}
                    style={{ fontFamily: FONT, background: 'transparent' }}
                />
            )}
        </div>
    );
}
