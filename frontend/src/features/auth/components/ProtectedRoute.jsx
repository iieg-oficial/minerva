import { Navigate } from 'react-router-dom';
import { isAdmin } from '@/api/auth';

export default function ProtectedRoute({ children }) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        return <Navigate to="/login" replace />;
    }
    if (!isAdmin()) {
        return <Navigate to="/no-access" replace />;
    }
    return children;
}
