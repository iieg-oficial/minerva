import { useState } from 'react';
import { Button, Upload, App } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import * as appsAPI from '@/api/applications';

// Botón reutilizable para subir/recargar un manifiesto (manifest.minerva.yml).
// Hace upsert de aplicación, permisos y roles en el backend.
// Si recibe `appId`, recarga el manifiesto de esa aplicación concreta (el backend
// valida que el `application.code` coincida con su slug); si no, hace import global.
export default function ManifestUploadButton({
    onImported,
    appId,
    type = 'default',
    size,
    icon,
    title,
    children,
}) {
    const { message } = App.useApp();
    const [loading, setLoading] = useState(false);

    const handleFile = async (file) => {
        setLoading(true);
        try {
            const res = appId
                ? await appsAPI.updateManifest(appId, file)
                : await appsAPI.importManifest(file);
            message.success(
                `Manifiesto "${res.application_code}" ${appId ? 'actualizado' : 'importado'}: ` +
                    `${res.permissions_upserted} permisos nuevos, ${res.roles_upserted} roles nuevos.`
            );
            onImported?.(res);
        } catch (err) {
            message.error(err.response?.data?.detail || 'Error al importar el manifiesto');
        } finally {
            setLoading(false);
        }
        return Upload.LIST_IGNORE; // evitamos la subida automática y la lista de AntD
    };

    return (
        <Upload accept=".yml,.yaml" showUploadList={false} maxCount={1} beforeUpload={handleFile}>
            <Button
                type={type}
                size={size}
                title={title}
                icon={icon || <UploadOutlined />}
                loading={loading}
            >
                {children === undefined ? 'Subir manifiesto' : children}
            </Button>
        </Upload>
    );
}
