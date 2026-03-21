import { Navigate, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

interface ProtectedAdminRouteProps {
  children: React.ReactNode;
}

export default function ProtectedAdminRoute({ children }: ProtectedAdminRouteProps) {
  const [isValidating, setIsValidating] = useState(true);
  const [isAuthorized, setIsAuthorized] = useState(false);
  const location = useLocation();

  useEffect(() => {
    validateAdminSession();
  }, []);

  async function validateAdminSession() {
    const adminToken = localStorage.getItem('admin_token');
    
    if (!adminToken) {
      setIsValidating(false);
      setIsAuthorized(false);
      return;
    }

    try {
      // Verify the token with the backend
      const response = await fetch(`${API_BASE_URL}/admin/verify-session`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${adminToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        setIsAuthorized(true);
      } else {
        // Token invalid - clear it
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_username');
        setIsAuthorized(false);
      }
    } catch (error) {
      console.error('Admin session validation error:', error);
      setIsAuthorized(false);
    } finally {
      setIsValidating(false);
    }
  }

  if (isValidating) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-900 via-purple-900 to-indigo-900 flex items-center justify-center">
        <div className="text-white text-xl">
          <div className="animate-spin w-8 h-8 border-4 border-white border-t-transparent rounded-full mx-auto mb-4"></div>
          Verifying admin credentials...
        </div>
      </div>
    );
  }

  if (!isAuthorized) {
    // Redirect to admin login, preserving the attempted location
    return <Navigate to="/admin/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
