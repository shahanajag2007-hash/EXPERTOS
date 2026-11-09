function AnalysisCard({ title, content }) {

  if (!content) return null;

  return (

    <div className="bg-white rounded-3xl shadow-lg border border-gray-200 overflow-hidden">

      <div className="bg-slate-100 px-6 py-4 border-b">

        <h2 className="text-xl font-bold">

          {title}

        </h2>

      </div>

      <div className="p-6 sm:p-8">

        <p className="leading-8 whitespace-pre-wrap text-gray-700">

          {content}

        </p>

      </div>

    </div>

  );

}

export default AnalysisCard;