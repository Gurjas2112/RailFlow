import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import { useSim } from "../store/sim";
import { applyUserLang } from "./useSession";
import LangSwitch from "../panels/LangSwitch";

/** Username + password + Sign in. No "Create account": accounts arrive by admin invite (§14, §30). */
export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const session = useSim((s) => s.session);
  const setSession = useSim((s) => s.setSession);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (session) return <Navigate to={session.role === "admin" ? "/admin" : "/"} replace />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await api.login(username.trim(), password);
      setSession(s);
      applyUserLang(s);
      navigate(s.role === "admin" ? "/admin" : "/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t("login.locked") : t("login.invalid"));
    } finally {
      setBusy(false);
      setPassword("");
    }
  }

  return (
    <main className="grid min-h-full place-items-center p-4">
      <form onSubmit={submit} className="panel w-full max-w-sm space-y-4 p-6" aria-labelledby="login-title">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h1 id="login-title" className="text-xl font-semibold">{t("app.name")}</h1>
            <p className="text-sm text-muted">{t("app.station")}</p>
          </div>
          <LangSwitch />
        </div>
        <label className="block space-y-1">
          <span className="label">{t("login.username")}</span>
          <input className="field" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="block space-y-1">
          <span className="label">{t("login.password")}</span>
          <input className="field" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p role="alert" className="text-sm text-conflict">{error}</p>}
        <button className="btn w-full" disabled={busy || !username || !password}>{busy ? t("app.working") : t("login.submit")}</button>
        <p className="text-xs text-muted">{t("login.inviteOnly")}</p>
      </form>
    </main>
  );
}
