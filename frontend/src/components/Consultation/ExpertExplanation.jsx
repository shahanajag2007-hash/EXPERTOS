import { useState } from "react";

function ExpertExplanation({ explanation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-white rounded-3xl shadow-lg border border-gray-200 p-8">

      <div className="flex justify-between items-center">

        <div>

          <h2 className="text-2xl font-bold">
            💬 Expert Consultation
          </h2>

          <p className="text-gray-500 mt-2">
            Read the complete reasoning behind the recommendation.
          </p>

        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-full transition"
        >
          {expanded ? "Hide" : "Read Full"}
        </button>

      </div>

      {expanded && (

        <div className="mt-6 border-t pt-6">

          <p className="text-gray-700 leading-8 whitespace-pre-wrap">
            {explanation}
          </p>

        </div>

      )}

    </div>
  );
}

export default ExpertExplanation;