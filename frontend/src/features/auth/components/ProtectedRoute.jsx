import { Navigate } from 'react-router-dom';
import { Flex, Spin } from 'antd';
import { useSession } from '@features/auth/SessionContext';

export default function ProtectedRoute({ children }) {
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
    if (!isAdmin) {
        return <Navigate to="/no-access" replace />;
    }
    return children;
}
