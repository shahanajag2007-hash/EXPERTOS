const numberFormat = new Intl.NumberFormat("en-US");

// Every value comes from GET /stats, which counts stored records only.
// Empty states say so instead of showing placeholder numbers.
export function buildStatItems(stats) {
  const ratings = stats.ratings;
  const response = stats.response_time;

  return [
    {
      key: "consultations",
      number: numberFormat.format(stats.completed_consultations),
      label: "Consultations Completed",
      detail: "Delivered recommendations, analyses and panel reviews",
    },
    {
      key: "experts",
      number: String(stats.active_experts),
      label: "Specialized AI Experts",
      detail: "Configured and available",
    },
    ratings.total > 0
      ? {
          key: "satisfaction",
          number: `${Math.round(ratings.satisfaction_rate)}%`,
          label: "Satisfaction Rate",
          detail: `${ratings.positive_threshold}+ stars, from ${numberFormat.format(ratings.total)} rating${ratings.total === 1 ? "" : "s"}`,
        }
      : {
          key: "satisfaction",
          number: "—",
          label: "Awaiting first ratings",
          detail: "Rate a consultation below",
        },
    response.status === "measured"
      ? {
          key: "response",
          number: `${response.average_seconds.toFixed(1)}s`,
          label: "Average Response",
          detail: `Single-expert replies, last ${response.window_days} days (${numberFormat.format(response.samples)} measured)`,
        }
      : {
          key: "response",
          number: "—",
          label: "Measuring response times",
          detail: `Target: under ${response.target_seconds}s`,
        },
  ];
}
