import { useState } from 'react';
import { Avatar, Button, Card, Divider, Flex, List, Tag, Typography } from 'antd';
import { getSessions, isExpired, removeSession } from '@/api/session';

const { Title, Text } = Typography;

function initial(name, email) {
    return (name || email || '?').trim().slice(0, 1).toUpperCase();
}

// Selector de cuentas ya iniciadas en este navegador (estilo Google/GitHub).
// Lista las activas y las expiradas (atenuadas, con acción de reingresar) y
// permite agregar otra cuenta. Es la UI del flujo `prompt=select_account`.
export default function AccountSelector({ appName, brandColor = '#5C2472', onSelect, onReauth, onAddAccount }) {
    const [sessions, setSessions] = useState(getSessions);

    const handleRemove = (e, sub) => {
        e.stopPropagation();
        removeSession(sub);
        setSessions(getSessions());
    };

    return (
        <Card style={{ maxWidth: 440, width: '100%' }}>
            <Title level={4} style={{ marginTop: 0, marginBottom: 4 }}>
                Elige una cuenta
            </Title>
            <Text type="secondary">{appName ? `para continuar en ${appName}` : 'para continuar'}</Text>

            <List
                style={{ marginTop: 16 }}
                dataSource={sessions}
                locale={{ emptyText: 'No hay cuentas iniciadas' }}
                renderItem={(s) => {
                    const expired = isExpired(s);
                    return (
                        <List.Item
                            actions={[
                                <Button type="text" danger size="small" key="rm" onClick={(e) => handleRemove(e, s.sub)}>
                                    Quitar
                                </Button>,
                            ]}
                            style={{ cursor: 'pointer', opacity: expired ? 0.55 : 1 }}
                            onClick={() => (expired ? onReauth(s) : onSelect(s))}
                        >
                            <List.Item.Meta
                                avatar={<Avatar style={{ backgroundColor: brandColor }}>{initial(s.name, s.email)}</Avatar>}
                                title={s.name || s.email}
                                description={
                                    <Flex gap={8} align="center" wrap>
                                        <Text type="secondary">{s.email}</Text>
                                        {expired && <Tag color="warning">Expirada — reingresar</Tag>}
                                    </Flex>
                                }
                            />
                        </List.Item>
                    );
                }}
            />

            <Divider style={{ margin: '12px 0' }} />
            <Button block onClick={onAddAccount}>
                Agregar otra cuenta
            </Button>
        </Card>
    );
}
