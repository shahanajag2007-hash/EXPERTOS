// Who this browser is, for the backend (see backend/services/auth.py).
//
// - Client ID: a random ID generated once per browser. Conversations and
//   uploads made without an account belong to it.
// - Session: set after signing in; conversations then belong to the account
//   and are available from any browser where you sign in.
//
// Both live in localStorage. If storage is unavailable the client ID lasts
// for this page view only.

const CLIENT_KEY = "expertos.clientId";
const SESSION_KEY = "expertos.session";

let memoryClientId = null;

function randomId() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function clientId() {
  try {
    let id = localStorage.getItem(CLIENT_KEY);
    if (!id || !/^[A-Za-z0-9_-]{22,128}$/.test(id)) {
      id = randomId();
      localStorage.setItem(CLIENT_KEY, id);
    }
    return id;
  } catch {
    memoryClientId = memoryClientId || randomId();
    return memoryClientId;
  }
}

/** { token, user: { id, email, name } } or null. */
export function storedSession() {
  try {
    const session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    return session?.token && session?.user ? session : null;
  } catch {
    return null;
  }
}

export function saveSession(session) {
  try {
    if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    // Not persisted; the user stays signed in for this page view only.
  }
  window.dispatchEvent(new CustomEvent("expertos:session", { detail: session }));
}

export function sessionToken() {
  return storedSession()?.token || null;
}
