import { useEffect, useState } from "react";
import { getJSON } from "../services/api";

// Platform statistics from GET /stats, shared by every component that shows
// them. One request serves all subscribers; data refreshes every minute while
// a page using it is open.
const REFRESH_MS = 60000;
const MAX_AGE_MS = 15000;

let cache = { data: null, error: null, fetchedAt: 0 };
let inflight = null;
const listeners = new Set();

function notify() {
  listeners.forEach((listener) => listener(cache));
}

export function refreshStats({ force = false } = {}) {
  if (!force && cache.data && Date.now() - cache.fetchedAt < MAX_AGE_MS) {
    return Promise.resolve(cache);
  }
  if (inflight) return inflight;

  inflight = getJSON("/stats")
    .then((data) => {
      cache = { data, error: null, fetchedAt: Date.now() };
    })
    .catch((error) => {
      // Keep the last good data if a refresh fails.
      cache = { ...cache, error };
    })
    .finally(() => {
      inflight = null;
      notify();
    });

  return inflight;
}

export function useStats() {
  const [state, setState] = useState(cache);

  useEffect(() => {
    listeners.add(setState);
    refreshStats();
    const timer = setInterval(() => refreshStats({ force: true }), REFRESH_MS);
    return () => {
      listeners.delete(setState);
      clearInterval(timer);
    };
  }, []);

  return {
    stats: state.data,
    error: state.error,
    loading: !state.data && !state.error,
  };
}

/** Per-expert statistics keyed by backend expert key (e.g. "Database Engineer"). */
export function useExpertStats(expertKey) {
  const { stats, error, loading } = useStats();
  const expertStats = stats
    ? stats.experts?.[expertKey] ?? { consultations: 0, ratings: 0, average_stars: null, satisfaction_rate: null }
    : null;
  return { expertStats, error, loading };
}

// Test helper.
export function __resetStatsCache() {
  cache = { data: null, error: null, fetchedAt: 0 };
  inflight = null;
}
