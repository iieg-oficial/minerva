import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Result } from 'antd';
import * as authAPI from '@/api/auth';

export default function NoAccessPage() {
    const navigate = useNavigate();
    // Aplicaciones que la persona sí usa: casi todos llegan aquí después de fijar su
    // contraseña, y lo que buscan es volver a su sistema, no el panel de Minerva.
    const [applications, setApplications] = useState([]);

    useEffect(() => {
        authAPI
            .getMyProfile()
            .then((profile) => setApplications(profile.applications || []))
            .catch(() => setApplications([]));
    }, []);

    const handleLogout = async () => {
        await authAPI.logout();
        navigate('/login', { replace: true });
    };

    const hasApplications = applications.length > 0;

    return (
        <Result
            status={hasApplications ? 'success' : '403'}
            title={hasApplications ? 'Tu cuenta está lista' : 'Sin acceso al panel'}
            subTitle={
                hasApplications
                    ? 'El panel de Minerva es solo para administradores. Entra desde la aplicación que usas.'
                    : 'Tu cuenta no tiene el rol de administrador de Minerva. Comunícate con un administrador si crees que es un error.'
            }
            extra={[
                ...applications.map((app) => (
                    <Button key={app.id} type="primary" href={app.homepage_url}>
                        Ir a {app.name}
                    </Button>
                )),
                <Button key="password" onClick={() => navigate('/cuenta/contrasena')}>
                    Cambiar mi contraseña
                </Button>,
                <Button
                    key="logout"
                    type={hasApplications ? 'default' : 'primary'}
                    onClick={handleLogout}
                >
                    Cerrar sesión
                </Button>,
            ]}
            style={{
                minHeight: '100dvh',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
            }}
        />
    );
}
