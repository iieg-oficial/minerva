import { useEffect, useState } from 'react';
import { App, Modal, Select, Typography } from 'antd';
import * as usersAPI from '@/api/users';
import { formatApiError } from '@/api/errors';

const { Paragraph, Text } = Typography;

const NO_DESTINATION = '';

// Confirma la emisión del enlace de contraseña y elige a qué aplicación se manda a la
// persona al guardarla. Sin destino termina en el login de Minerva, cuyo panel es solo
// para administradores: por eso se preselecciona la primera aplicación que usa.
export default function IssueLinkModal({ user, onClose, onIssued }) {
    const { message } = App.useApp();
    const [destinations, setDestinations] = useState(null);
    const [applicationId, setApplicationId] = useState(NO_DESTINATION);
    const [issuing, setIssuing] = useState(false);

    useEffect(() => {
        if (!user) return;
        setDestinations(null);
        usersAPI
            .listCredentialDestinations(user.id)
            .then((items) => {
                setDestinations(items);
                setApplicationId(items[0]?.id ?? NO_DESTINATION);
            })
            .catch(() => {
                setDestinations([]);
                setApplicationId(NO_DESTINATION);
            });
    }, [user]);

    const handleOk = async () => {
        setIssuing(true);
        try {
            const link = await usersAPI.createCredentialLink(user.id, applicationId || null);
            onIssued({ email: user.email, ...link });
        } catch (err) {
            message.error(formatApiError(err, 'No se pudo generar el enlace'));
        } finally {
            setIssuing(false);
        }
    };

    const options = [
        ...(destinations || []).map((d) => ({ label: d.name, value: d.id })),
        { label: 'Sin destino (login de Minerva)', value: NO_DESTINATION },
    ];

    return (
        <Modal
            title={
                user?.status === 'pending'
                    ? 'Generar un nuevo enlace de invitación'
                    : 'Generar un enlace para restablecer la contraseña'
            }
            open={!!user}
            onCancel={onClose}
            onOk={handleOk}
            okText="Generar"
            cancelText="Cancelar"
            confirmLoading={issuing}
            okButtonProps={{ disabled: destinations === null }}
            destroyOnHidden
        >
            <Paragraph>
                Al guardar su contraseña, <Text strong>{user?.email}</Text> irá a:
            </Paragraph>
            <Select
                style={{ width: '100%' }}
                loading={destinations === null}
                value={applicationId}
                onChange={setApplicationId}
                options={options}
                aria-label="Aplicación de destino"
            />
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                Solo aparecen las aplicaciones donde tiene roles y con página de inicio. Cualquier
                enlace anterior de este usuario dejará de funcionar.
            </Paragraph>
        </Modal>
    );
}
