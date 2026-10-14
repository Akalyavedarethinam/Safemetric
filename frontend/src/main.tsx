import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import "./styles.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { Spinner, ToastProvider } from "./components/ui";
import Layout from "./components/Layout";
import Landing from "./pages/Landing";
import { Login, Register } from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import NewInspection from "./pages/NewInspection";
import InspectionDetail from "./pages/InspectionDetail";
import History from "./pages/History";
import Reports from "./pages/Reports";
import Rules from "./pages/Rules";
import Users from "./pages/Users";
import Settings from "./pages/Settings";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  return <>{children}</>;
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return user ? <Navigate to="/app/dashboard" replace /> : <>{children}</>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
            <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
            <Route path="/app" element={<RequireAuth><Layout /></RequireAuth>}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="inspections/new" element={<NewInspection />} />
              <Route path="inspections/:id" element={<InspectionDetail />} />
              <Route path="inspections" element={<History />} />
              <Route path="reports" element={<Reports />} />
              <Route path="rules" element={<Rules />} />
              <Route path="users" element={<Users />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
