import { Suspense, lazy, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSession } from "./auth/useSession";
import Login from "./auth/Login";
import AcceptInvite from "./auth/AcceptInvite";
import Workspace from "./layout/Workspace";
import { useSim } from "./store/sim";
import { api } from "./api/client";

const AdminPage = lazy(() => import("./admin/AdminPage"));

function Loading() {
  const { t } = useTranslation();
  return <div className="grid h-full place-items-center text-muted">{t("app.loading")}</div>;
}

function Guard({ children, role }: { children: React.ReactNode; role?: "admin" }) {
  const session = useSim((s) => s.session);
  const checked = useSim((s) => s.sessionChecked);
  const loc = useLocation();
  if (!checked) return <Loading />;
  if (!session) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (role === "admin" && session.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  useSession();
  const setHealth = useSim((s) => s.setHealth);
  useEffect(() => {
    let alive = true;
    const poll = () => api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(null));
    poll();
    const id = window.setInterval(poll, 10000);
    return () => { alive = false; window.clearInterval(id); };
  }, [setHealth]);

  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/invite/:token" element={<AcceptInvite />} />
        <Route path="/admin/*" element={<Guard role="admin"><AdminPage /></Guard>} />
        <Route path="/" element={<Guard><Workspace /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
