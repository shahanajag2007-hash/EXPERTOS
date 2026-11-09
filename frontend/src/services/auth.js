import { useEffect, useState } from "react";
import { getJSON, postJSON } from "./api";
import { saveSession, storedSession } from "./identity";

export async function register({ name, email, password }) {
  const data = await postJSON("/auth/register", { name, email, password });
  saveSession({ token: data.token, user: data.user });
  return data.user;
}

export async function signIn({ email, password }) {
  const data = await postJSON("/auth/login", { email, password });
  saveSession({ token: data.token, user: data.user });
  return data.user;
}

export async function signOut() {
  try {
    await postJSON("/auth/logout", {});
  } catch {
    // Signing out locally is what matters; the server session expires anyway.
  }
  saveSession(null);
}

/** Check a stored session with the backend; clears it if it has expired. */
export async function refreshSession() {
  if (!storedSession()) return null;
  try {
    const { user } = await getJSON("/auth/me");
    const session = storedSession();
    if (session) saveSession({ ...session, user });
    return user;
  } catch (err) {
    if (err?.status === 401) saveSession(null);
    return storedSession()?.user || null;
  }
}

/** The signed-in user ({ id, email, name }) or null; updates on sign-in/out. */
export function useSession() {
  const [user, setUser] = useState(() => storedSession()?.user || null);

  useEffect(() => {
    const onChange = (e) => setUser(e.detail?.user || null);
    const onStorage = (e) => {
      if (e.key === "expertos.session") setUser(storedSession()?.user || null);
    };
    window.addEventListener("expertos:session", onChange);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("expertos:session", onChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return user;
}
