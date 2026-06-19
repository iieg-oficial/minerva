import { Routes, Route, Navigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import LoginPage from '@features/auth/pages/LoginPage';
import AuthorizePage from '@features/auth/pages/AuthorizePage';
import LogoutPage from '@features/auth/pages/LogoutPage';
import NoAccessPage from '@features/auth/pages/NoAccessPage';
import DashboardPage from '@features/auth/pages/DashboardPage';
import AdminLayout from '@features/admin/layout/AdminLayout';
import ProtectedRoute from '@features/auth/components/ProtectedRoute';
import UsersPage from '@features/admin/pages/UsersPage';
import ApplicationsPage from '@features/admin/pages/ApplicationsPage';
import RolesPage from '@features/admin/pages/RolesPage';
import PermissionsPage from '@features/admin/pages/PermissionsPage';
import GroupsPage from '@features/admin/pages/GroupsPage';
import AuthorizationPage from '@features/admin/pages/AuthorizationPage';
import AuditPage from '@features/admin/pages/AuditPage';

export default function App() {
    return (
        <AntApp>
            <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/authorize" element={<AuthorizePage />} />
                <Route path="/no-access" element={<NoAccessPage />} />
                <Route path="/logout" element={<LogoutPage />} />
                <Route path="/admin" element={<ProtectedRoute><AdminLayout /></ProtectedRoute>}>
                    <Route index element={<DashboardPage />} />
                    <Route path="users" element={<UsersPage />} />
                    <Route path="applications" element={<ApplicationsPage />} />
                    <Route path="roles" element={<RolesPage />} />
                    <Route path="permissions" element={<PermissionsPage />} />
                    <Route path="groups" element={<GroupsPage />} />
                    <Route path="authorization" element={<AuthorizationPage />} />
                    <Route path="audit" element={<AuditPage />} />
                </Route>
                <Route path="/" element={<Navigate to="/admin" replace />} />
                <Route path="*" element={<Navigate to="/admin" replace />} />
            </Routes>
        </AntApp>
    );
}
