import { useNavigate } from 'react-router-dom';
import { Button, Result } from 'antd';
import * as authAPI from '@/api/auth';

export default function NoAccessPage() {
    const navigate = useNavigate();

    const handleLogout = async () => {
        await authAPI.logout();
        navigate('/login', { replace: true });
    };

    return (
        <Result
            status="403"
            title="Sin acceso al panel"
            subTitle="Tu cuenta no tiene el rol de administrador de Minerva. Comunícate con un administrador si crees que es un error."
            extra={
                <Button type="primary" onClick={handleLogout}>
                    Cerrar sesión
                </Button>
            }
            style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
        />
    );
}
