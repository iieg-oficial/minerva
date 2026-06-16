import { useState } from 'react';
import { Button, Upload, App } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import * as appsAPI from '@/api/applications';

// Botón reutilizable para subir/recargar un manifiesto (manifest.minerva.yml).
// Hace upsert de aplicación, permisos y roles en el backend.
export default function ManifestUploadButton({ onImported, type = 'default', children }) {
    const { message } = App.useApp();
    const [loading, setLoading] = useState(false);

    const handleFile = async (file) => {
        setLoading(true);
        try {
            const res = await appsAPI.importManifest(file);
            message.success(
                `Manifiesto "${res.application_code}" importado: ` +
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
            <Button type={type} icon={<UploadOutlined />} loading={loading}>
                {children || 'Subir manifiesto'}
            </Button>
        </Upload>
    );
}
