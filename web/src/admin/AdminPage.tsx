import { NavLink, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Header from "../panels/Header";
import Dashboard from "./Dashboard";
import Users from "./Users";
import AuditVerify from "./AuditVerify";

/** /admin — visible only to admins: dashboard, user management, audit verification (§14, §34). */
export default function AdminPage() {
  const { t } = useTranslation();
  const tab = ({ isActive }: { isActive: boolean }) => `btn btn-sm ${isActive ? "" : "btn-ghost"}`;
  return (
    <div className="min-h-full">
      <Header />
      <nav className="flex flex-wrap gap-2 px-3 pt-3" aria-label={t("admin.nav")}>
        <NavLink end to="/admin" className={tab}>{t("admin.dashboard")}</NavLink>
        <NavLink end to="/" className={tab}>{t("admin.station")}</NavLink>
        <NavLink to="/admin/users" className={tab}>{t("admin.users")}</NavLink>
        <NavLink to="/admin/audit" className={tab}>{t("admin.audit")}</NavLink>
      </nav>
      <div className="p-3">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="users" element={<Users />} />
          <Route path="audit" element={<AuditVerify />} />
        </Routes>
      </div>
    </div>
  );
}
