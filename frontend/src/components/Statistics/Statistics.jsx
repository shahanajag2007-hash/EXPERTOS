import { useStats } from "../../hooks/useStats";
import { buildStatItems } from "./statItems";

function Statistics() {
  const { stats, error, loading } = useStats();

  return (
    <section className="max-w-6xl mx-auto px-6 py-10" aria-labelledby="stats-heading" aria-busy={loading}>
      <h2 id="stats-heading" className="sr-only">ExpertOS statistics</h2>

      {loading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center" aria-label="Loading statistics">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse">
              <div className="h-9 w-24 mx-auto bg-slate-200 rounded" />
              <div className="h-4 w-32 mx-auto bg-slate-100 rounded mt-3" />
            </div>
          ))}
        </div>
      )}

      {!loading && !stats && error && (
        <p className="text-center text-gray-500" role="status">
          Live statistics are unavailable right now.
        </p>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          {buildStatItems(stats).map((item) => (
            <div key={item.key} data-testid={`stat-${item.key}`}>
              <p className="text-3xl font-bold text-indigo-600">
                {item.number}
              </p>

              <p className="mt-2 text-gray-600 font-medium">
                {item.label}
              </p>

              <p className="mt-1 text-xs text-gray-400">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default Statistics;
