import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import i18n from "../i18n";
import { changeLang, LANGS, type Lang } from "../i18n";
import { api, setUnauthorizedHandler, type SessionOut } from "../api/client";
import { useSim } from "../store/sim";

/** Bootstraps the session from the cookie and signs the user out on any 401. */
export function useSession() {
  const setSession = useSim((s) => s.setSession);
  const navigate = useNavigate();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (useSim.getState().session) {
        setSession(null);
        navigate("/login", { replace: true });
      }
    });
    api.me().then((s) => { setSession(s); applyUserLang(s); }).catch(() => setSession(null));
  }, [setSession, navigate]);
}

/** The language is remembered on the user record (§37); the server value wins after sign-in. */
export function applyUserLang(s: SessionOut) {
  const lng = s.lang as Lang;
  if ((LANGS as readonly string[]).includes(lng) && lng !== i18n.resolvedLanguage) void changeLang(lng);
}

export async function signOut() {
  await api.logout().catch(() => undefined);
  useSim.getState().setSession(null);
}
