import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Select, Typography, Space, Tag, App } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import * as auditAPI from '@/api/audit';
import * as appsAPI from '@/api/applications';

const { Title } = Typography;

export default function AuditPage() {
    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [apps, setApps] = useState([]);
    const [filters, setFilters] = useState({ offset: 0, limit: 15 });
    const { message } = App.useApp();

    const fetchLogs = useCallback(async () => {
        setLoading(true);
        try {
            const data = await auditAPI.listLogs(filters);
            setLogs(data.items || []);
            setTotal(data.total || 0);
        } catch {
            message.error('Error al cargar auditoría');
        } finally {
            setLoading(false);
        }
    }, [filters, message]);

    const fetchApps = useCallback(async () => {
        try {
            const data = await appsAPI.listApplications({ limit: 100 });
            setApps(data.items || []);
        } catch {}
    }, []);

    useEffect(() => {
        fetchLogs();
        fetchApps();
    }, [fetchLogs, fetchApps]);

    const getAppName = (id) => {
        const app = apps.find((a) => a.id === id);
        return app ? <Tag color="#2e4372">{app.name}</Tag> : id?.slice(0, 8) || '-';
    };

    const columns = [
        {
            title: 'Fecha',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 170,
            render: (v) => (v ? new Date(v).toLocaleString() : '-'),
        },
        {
            title: 'Acción',
            dataIndex: 'action',
            key: 'action',
            width: 160,
            render: (v) => (
                <Tag color={v?.includes('failed') || v?.includes('denied') ? 'red' : 'blue'}>
                    {v}
                </Tag>
            ),
        },
        {
            title: 'Usuario',
            dataIndex: 'actor_user_id',
            key: 'actor',
            width: 100,
            render: (v) => v?.slice(0, 8) || '-',
        },
        { title: 'Tipo', dataIndex: 'target_type', key: 'target_type', width: 100 },
        {
            title: 'Target',
            dataIndex: 'target_id',
            key: 'target_id',
            width: 100,
            render: (v) => v?.slice(0, 8) || '-',
        },
        {
            title: 'App',
            dataIndex: 'application_id',
            key: 'app',
            width: 120,
            render: (v) => (v ? getAppName(v) : '-'),
        },
        { title: 'IP', dataIndex: 'ip_address', key: 'ip', width: 120 },
    ];

    const ACTION_OPTIONS = [
        { label: 'login success', value: 'manual_login_success' },
        { label: 'login failed', value: 'manual_login_failed' },
        { label: 'register success', value: 'manual_register_success' },
        { label: 'logout', value: 'logout' },
        { label: 'permission check', value: 'permission_check_allowed' },
        { label: 'permission denied', value: 'permission_check_denied' },
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
                    Auditoría
                </Title>
                <Button icon={<ReloadOutlined />} onClick={fetchLogs}>
                    Actualizar
                </Button>
            </div>

            <Space wrap style={{ marginBottom: 16 }}>
                <Select
                    allowClear
                    placeholder="Filtrar por acción"
                    style={{ width: 220 }}
                    options={ACTION_OPTIONS}
                    value={filters.action}
                    onChange={(val) => setFilters((f) => ({ ...f, action: val, offset: 0 }))}
                />
                <Select
                    allowClear
                    placeholder="Filtrar por aplicación"
                    style={{ width: 200 }}
                    options={apps.map((a) => ({ label: a.name, value: a.id }))}
                    value={filters.application_id}
                    onChange={(val) =>
                        setFilters((f) => ({ ...f, application_id: val, offset: 0 }))
                    }
                />
                <Button onClick={() => setFilters({ offset: 0, limit: 15 })}>
                    Limpiar filtros
                </Button>
            </Space>

            <Table
                columns={columns}
                dataSource={logs}
                rowKey="id"
                loading={loading}
                size="small"
                pagination={{
                    total,
                    current: Math.floor(filters.offset / filters.limit) + 1,
                    pageSize: filters.limit,
                    onChange: (p, ps) =>
                        setFilters((f) => ({ ...f, offset: (p - 1) * ps, limit: ps })),
                }}
            />
        </div>
    );
}
