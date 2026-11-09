// Wording for real per-expert statistics (from GET /stats). Empty states say
// what is missing instead of showing placeholder numbers.

// Used when statistics have loaded but contain nothing for an expert yet.
export const NO_EXPERT_STATS = { consultations: 0, ratings: 0, average_stars: null, satisfaction_rate: null };

const numberFormat = new Intl.NumberFormat("en-US");

export function formatRating(stats) {
  if (!stats) return { value: "—", detail: "Loading ratings" };
  if (!stats.ratings) return { value: "No ratings yet", detail: "" };
  return {
    value: `★ ${stats.average_stars.toFixed(1)}`,
    detail: `${numberFormat.format(stats.ratings)} rating${stats.ratings === 1 ? "" : "s"}`,
  };
}

export function formatConsultations(stats) {
  if (!stats) return "—";
  if (!stats.consultations) return "No consultations yet";
  return `${numberFormat.format(stats.consultations)} consultation${stats.consultations === 1 ? "" : "s"}`;
}

export function formatSatisfaction(stats) {
  if (!stats || stats.satisfaction_rate == null) return "—";
  return `${Math.round(stats.satisfaction_rate)}%`;
}
