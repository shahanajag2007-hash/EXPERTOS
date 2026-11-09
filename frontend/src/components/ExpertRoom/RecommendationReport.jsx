// `actions` (optional) renders below the report, e.g. a download button.
function RecommendationReport({ expert, report, actions = null }) {
  if (!expert) {

      return null;

  }

if (!report) {

    return (

        <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm p-12 text-center">

            <div className="text-6xl">

                🧠

            </div>

            <h2 className="text-3xl font-bold mt-6">

                Generating Recommendation...

            </h2>

            <p className="text-gray-500 mt-4">

                {expert.name.split(" ")[0]} is preparing your personalized recommendation.

            </p>

        </div>

    );

}

  const metrics = Array.isArray(report.metrics) ? report.metrics : [];

  return (

    <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm overflow-hidden">

      <div className="px-6 sm:px-8 py-6 border-b bg-slate-50 flex flex-wrap justify-between items-center gap-4">

        <div className="min-w-0">

          <p className="uppercase tracking-widest text-indigo-600 font-semibold">

            Recommendation Report

          </p>

          <h2 className="text-2xl sm:text-3xl font-bold mt-2 break-words">

            {report.title || `${expert.shortRole} Recommendation`}

          </h2>

        </div>

        <p className="text-xs text-gray-500 max-w-[16rem] sm:text-right">

          AI-generated recommendation. Review it before acting on it.

        </p>

      </div>

      <div className="p-6 sm:p-8">

        <div className="bg-gradient-to-r from-indigo-600 to-blue-700 rounded-3xl text-white p-6 sm:p-8">

          <h2 className="text-2xl sm:text-4xl font-bold break-words">

            {report.recommendation}

          </h2>

          {report.description && (

            <p className="mt-6 leading-8 text-lg whitespace-pre-wrap">

              {report.description}

            </p>

          )}

        </div>

        {metrics.length > 0 && (

          <>

          <h3 className="mt-8 font-semibold text-gray-800">

            What to measure

          </h3>

          <p className="text-sm text-gray-500 mt-1">

            Suggested metrics and targets for judging whether this works. They are goals, not measured results.

          </p>

          <div className="grid md:grid-cols-3 gap-6 mt-4">

            {metrics.map((metric, index) => (

                <div
                    key={`${metric.name}-${index}`}
                    className="bg-slate-50 rounded-2xl p-6"
                >

                    <p className="text-gray-500">

                        {metric.name}

                    </p>

                    <p className="text-xl font-bold mt-3 break-words">

                        {metric.value}

                    </p>

                </div>

            ))}

          </div>

          </>

        )}

        {actions && (

          <div className="mt-8 flex flex-wrap justify-end gap-3">

            {actions}

          </div>

        )}

      </div>

    </div>

  );

}

export default RecommendationReport;
