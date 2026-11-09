function ExecutiveSummary({ summary }) {
  return (
    <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-3xl text-white p-6 sm:p-8 shadow-lg mt-8">

      <div className="flex flex-wrap justify-between items-center gap-4">

        <div>

          <h2 className="text-2xl sm:text-3xl font-bold">
            📋 Executive Summary
          </h2>

          <p className="mt-2 text-indigo-100">
            30 second overview from your AI expert.
          </p>

        </div>

        <div className="bg-white/20 px-4 py-2 rounded-full">
          30 sec read
        </div>

      </div>

      <p className="mt-8 text-lg leading-8">
        {summary}
      </p>

    </div>
  );
}

export default ExecutiveSummary;