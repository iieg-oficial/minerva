import { Navigate } from 'react-router-dom';
import { Flex, Spin } from 'antd';
import { useSession } from '@features/auth/SessionContext';

// `requireAdmin={false}` para páginas de cuenta propia (p. ej. cambiar la contraseña),
// que cualquier usuario con sesión puede usar.
export default function ProtectedRoute({ children, requireAdmin = true }) {
    const { loading, active, isAdmin } = useSession();
    if (loading) {
        return (
            <Flex align="center" justify="center" style={{ minHeight: '100dvh' }}>
                <Spin size="large" />
            </Flex>
        );
    }
    if (!active) {
        return <Navigate to="/login" replace />;
    }
    if (requireAdmin && !isAdmin) {
        return <Navigate to="/no-access" replace />;
    }
    return children;
}
