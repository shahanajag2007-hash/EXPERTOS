import { useCallback, useEffect, useState } from "react";
import { deleteJSON, getJSON } from "./api";

// Saved conversations (backend/services/conversations.py). Without an account
// they belong to this browser; signed in, to the account.

export function listConversations({ kind, expert } = {}, options = {}) {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (expert) params.set("expert", expert);
  return getJSON(`/conversations?${params}`, options).then((data) => data.conversations);
}

export function getConversation(id, options = {}) {
  return getJSON(`/conversations/${encodeURIComponent(id)}`, options);
}

export function deleteConversation(id) {
  return deleteJSON(`/conversations/${encodeURIComponent(id)}`);
}

// The conversation open in a room, so a reload continues it.
export function activeConversation(slot) {
  try {
    return sessionStorage.getItem(`expertos.active.${slot}`);
  } catch {
    return null;
  }
}

export function setActiveConversation(slot, id) {
  try {
    if (id) sessionStorage.setItem(`expertos.active.${slot}`, id);
    else sessionStorage.removeItem(`expertos.active.${slot}`);
  } catch {
    // Not remembered across reloads; the history list still has it.
  }
}

/** Conversation list that refreshes on demand and when the user signs in or out. */
export function useConversationList(filter) {
  const [conversations, setConversations] = useState([]);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const { kind, expert } = filter;

  useEffect(() => {
    const controller = new AbortController();
    listConversations({ kind, expert }, { signal: controller.signal })
      .then((list) => {
        setConversations(list);
        setError("");
      })
      .catch((err) => {
        if (err?.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [kind, expert, version]);

  useEffect(() => {
    const bump = () => setVersion((v) => v + 1);
    window.addEventListener("expertos:session", bump);
    return () => window.removeEventListener("expertos:session", bump);
  }, []);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  return { conversations, error, refresh };
}

export function formatWhen(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
