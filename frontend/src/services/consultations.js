// Consultations this browser has completed, with their access tokens.
//
// There are no accounts: the backend issues a random token when a
// consultation completes, and only this browser receives it. The token is
// needed to rate the consultation, open its live room or delete its content.
// Stored in localStorage (this browser only); losing it only means the
// consultation can't be rated or reopened from here.

const KEY = "expertos.consultations";
const MAX_ENTRIES = 20;

function read() {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(list) ? list.filter((c) => c && c.id && c.token) : [];
  } catch {
    return [];
  }
}

function write(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX_ENTRIES)));
  } catch {
    // Storage unavailable (private mode, quota); the feature degrades gracefully.
  }
  window.dispatchEvent(new Event("expertos:consultations"));
}

/** Remember a consultation returned by the backend ({ id, token }). */
export function rememberConsultation(consultation, { kind, label } = {}) {
  if (!consultation?.id || !consultation?.token) return;
  const list = read().filter((c) => c.id !== consultation.id);
  list.unshift({
    id: consultation.id,
    token: consultation.token,
    kind,
    label,
    createdAt: new Date().toISOString(),
    rated: false,
  });
  write(list);
}

export function listConsultations() {
  return read();
}

/** The most recent consultation this browser hasn't rated yet. */
export function latestUnrated() {
  return read().find((c) => !c.rated) || null;
}

export function markRated(id) {
  write(read().map((c) => (c.id === id ? { ...c, rated: true } : c)));
}

export function forgetConsultation(id) {
  write(read().filter((c) => c.id !== id));
}

export function tokenFor(id) {
  return read().find((c) => c.id === id)?.token || null;
}
