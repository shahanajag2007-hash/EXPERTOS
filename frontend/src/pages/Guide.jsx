import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";
import { experts } from "../data/experts";
import { matchExpert } from "../services/expertRecommendation";

// Backend expert keys (e.g. "Database Engineer") → frontend expert profiles.
function findExpertByRole(role) {
  return Object.values(experts).find((e) => e.shortRole === role);
}

function Guide() {
  const navigate = useNavigate();

  const [project, setProject] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function recommend() {
    if (!project.trim()) {
      setError("Please describe your project first.");
      return;
    }

    setError("");
    setLoading(true);

    try {
      const data = await matchExpert(project);
      const expert = findExpertByRole(data.expert_key);

      if (!expert) {
        throw new Error("The recommended expert isn't available right now. Please browse the experts instead.");
      }

      setResult({ expert, matched: data.matched || [] });
    } catch (err) {
      setResult(null);
      setError(err.message);
    }

    setLoading(false);
  }

  function startConsultation() {
    navigate(`/expert/${result.expert.id}`, { state: { problem: project } });
  }

  return (
    <>
      <Navbar />

      <div className="min-h-screen bg-slate-50">

        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12 sm:py-20">

          <p className="text-indigo-600 uppercase tracking-widest font-semibold">
            AI Guide
          </p>

          <h1 className="text-4xl sm:text-5xl font-bold mt-4">
            Find the Right Expert
          </h1>

          <p className="text-gray-600 mt-6 text-lg max-w-3xl">
            Tell us about your project and ExpertOS will recommend the most suitable expert to help you.
          </p>

          <div className="grid lg:grid-cols-2 gap-8 lg:gap-10 mt-10 sm:mt-14">

            <div className="bg-white rounded-3xl border shadow-sm p-6 sm:p-8">

              <h2 className="text-2xl font-bold">
                Describe Your Project
              </h2>

              <textarea
                rows={10}
                value={project}
                onChange={(e) => setProject(e.target.value)}
                aria-label="Project description"
                className="w-full mt-6 border rounded-2xl p-5 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Example: I'm building an AI resume platform using React and Flask..."
              />

              {error && (
                <p className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-2xl px-4 py-3 text-sm" role="alert">
                  {error}
                </p>
              )}

              <button
                onClick={recommend}
                disabled={loading}
                className="mt-8 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-4 rounded-2xl font-semibold"
              >
                {loading ? "Finding your expert..." : "Recommend Expert →"}
              </button>

            </div>

            <div className="bg-white rounded-3xl border shadow-sm p-6 sm:p-8">

              <h2 className="text-2xl font-bold">
                Recommended Expert
              </h2>

              <div className="bg-slate-50 rounded-3xl p-6 sm:p-8 mt-6 min-h-[360px] flex flex-col justify-between">

                {!result && (
                  <div className="flex-1 flex flex-col items-center justify-center text-center text-gray-500">
                    <div className="text-5xl">{loading ? "🔍" : "🧭"}</div>
                    <p className="mt-4 max-w-sm leading-7">
                      {loading
                        ? "Matching your project to our experts..."
                        : "Describe your project and select Recommend Expert to see who should lead your consultation."}
                    </p>
                  </div>
                )}

                {result && (
                  <>
                    <div>

                      <p className="text-sm text-indigo-600 font-semibold uppercase">
                        Recommended Expert
                      </p>

                      <h2 className="text-3xl font-bold mt-4">
                        {result.expert.icon} {result.expert.name}
                      </h2>

                      <p className="text-gray-500 mt-3">
                        {result.expert.role}
                      </p>

                      <div className="mt-8">

                        <h3 className="font-semibold">
                          Why this expert?
                        </h3>

                        <p className="text-gray-600 mt-3 leading-7">
                          {result.matched.length > 0 ? (
                            <>
                              Your description mentions{" "}
                              {result.matched.map((word, i) => (
                                <span key={word}>
                                  {i > 0 && ", "}
                                  <strong>{word}</strong>
                                </span>
                              ))}
                              , which falls within {result.expert.name.split(" ")[0]}'s
                              specialization: {result.expert.description.toLowerCase()}
                            </>
                          ) : (
                            <>
                              No single specialty stood out in your description, so{" "}
                              {result.expert.name.split(" ")[0]} is the best starting point —
                              they'll review the overall design and can bring in other experts.
                            </>
                          )}
                        </p>

                      </div>

                    </div>

                    <div className="mt-8 flex flex-col sm:flex-row gap-3">

                      <button
                        onClick={startConsultation}
                        className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white py-4 rounded-2xl font-semibold"
                      >
                        Start Consultation →
                      </button>

                      <button
                        onClick={() => navigate("/experts")}
                        className="flex-1 border border-slate-300 hover:bg-white py-4 rounded-2xl font-semibold"
                      >
                        Choose Another Expert
                      </button>

                    </div>
                  </>
                )}

              </div>

            </div>

          </div>

        </div>

      </div>

    </>
  );
}

export default Guide;
