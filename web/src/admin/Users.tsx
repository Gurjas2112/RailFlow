import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type InviteOut, type Role, type UserOut } from "../api/client";

/** Invite (single-use link, 24 h), change role, disable. The last admin is protected server-side (§30). */
export default function Users() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserOut[]>([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [invite, setInvite] = useState<InviteOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api.users().then(setUsers).catch((e) => setErr(String(e.message ?? e)));
  useEffect(() => { void load(); }, []);

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    try { await fn(); await load(); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
      <section className="panel overflow-x-auto p-3">
        <h2 className="label mb-2">{t("admin.users")}</h2>
        <table className="w-full min-w-[480px] text-sm">
          <thead><tr className="text-left text-muted"><th>{t("login.username")}</th><th>{t("admin.role")}</th><th>{t("admin.status")}</th><th /></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-line">
                <td className="py-2">{u.username}</td>
                <td>
                  <select className="field min-h-9 py-1" value={u.role} aria-label={t("admin.role")}
                    onChange={(e) => void act(() => api.patchUser(String(u.id), { role: e.target.value as Role }))}>
                    {(["viewer", "controller", "admin"] as Role[]).map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}
                  </select>
                </td>
                <td>{u.disabled ? <span className="text-conflict">{t("admin.disabled")}</span> : <span className="text-valid">{t("admin.active")}</span>}</td>
                <td className="text-right">
                  <button type="button" className="btn btn-ghost btn-sm"
                    onClick={() => void act(() => api.patchUser(String(u.id), { disabled: !u.disabled }))}>
                    {u.disabled ? t("admin.enable") : t("admin.disable")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {err && <p role="alert" className="mt-2 text-sm text-conflict">{err}</p>}
      </section>
      <section className="panel space-y-2 p-3">
        <h2 className="label">{t("admin.invite")}</h2>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); void act(async () => { setInvite(await api.invite(name.trim(), role)); setName(""); }); }}>
          <input className="field" placeholder={t("login.username")} value={name} onChange={(e) => setName(e.target.value)}
            pattern="[a-z0-9_.\-]{3,32}" required />
          <select className="field" value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label={t("admin.role")}>
            {(["viewer", "controller", "admin"] as Role[]).map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}
          </select>
          <button className="btn w-full" disabled={!name}>{t("admin.createInvite")}</button>
        </form>
        {invite && (
          <div className="rounded-md bg-raised p-2 text-sm">
            <p>{t("admin.inviteReady", { user: invite.username })}</p>
            <p className="num mt-1 break-all text-xs">{window.location.origin}{invite.link}</p>
            <p className="mt-1 text-xs text-muted">{t("admin.inviteOnce")}</p>
          </div>
        )}
      </section>
    </div>
  );
}
