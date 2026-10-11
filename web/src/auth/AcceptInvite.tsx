import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";

/** Single-use, 24 h invite: the user sets their own password; the admin never knows it (§30). */
export default function AcceptInvite() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (pw !== pw2) return setError(t("invite.mismatch"));
    if (pw.length < 12) return setError(t("invite.tooShort"));
    try {
      const s = await api.acceptInvite(token, pw);
      setDone(s.user);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 410 ? t("invite.expired") : err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="grid min-h-full place-items-center p-4">
      <form onSubmit={submit} className="panel w-full max-w-sm space-y-4 p-6">
        <h1 className="text-xl font-semibold">{t("invite.title")}</h1>
        {done ? (
          <>
            <p>{t("invite.done", { user: done })}</p>
            <Link className="btn w-full" to="/login">{t("login.submit")}</Link>
          </>
        ) : (
          <>
            <p className="text-sm text-muted">{t("invite.help")}</p>
            <label className="block space-y-1">
              <span className="label">{t("invite.password")}</span>
              <input className="field" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
            </label>
            <label className="block space-y-1">
              <span className="label">{t("invite.repeat")}</span>
              <input className="field" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
            </label>
            {error && <p role="alert" className="text-sm text-conflict">{error}</p>}
            <button className="btn w-full" disabled={!pw || !pw2}>{t("invite.submit")}</button>
          </>
        )}
      </form>
    </main>
  );
}
