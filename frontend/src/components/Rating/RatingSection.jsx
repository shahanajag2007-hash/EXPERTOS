import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { postJSON } from "../../services/api";
import { listConsultations, markRated } from "../../services/consultations";
import { refreshStats } from "../../hooks/useStats";

const LABELS = ["", "Poor", "Fair", "Good", "Very good", "Excellent"];
const FEEDBACK_MAX = 1000;

function unratedConsultations() {
  return listConsultations().filter((c) => !c.rated);
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

/**
 * Homepage rating. Each rating belongs to a consultation completed in this
 * browser (its access token proves that), so every consultation counts once
 * toward the satisfaction rate, and the backend rejects repeats.
 */
function RatingSection() {
  const [candidates, setCandidates] = useState(unratedConsultations);
  const [selectedId, setSelectedId] = useState(() => unratedConsultations()[0]?.id || "");
  const [stars, setStars] = useState(0);
  const [hover, setHover] = useState(0);
  const [feedback, setFeedback] = useState("");
  const [status, setStatus] = useState("idle");   // idle | submitting | success
  const [error, setError] = useState("");
  const submitting = useRef(false);

  useEffect(() => {
    const update = () => {
      const list = unratedConsultations();
      setCandidates(list);
      setSelectedId((current) => (list.some((c) => c.id === current) ? current : list[0]?.id || ""));
    };
    window.addEventListener("expertos:consultations", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("expertos:consultations", update);
      window.removeEventListener("storage", update);
    };
  }, []);

  const selected = candidates.find((c) => c.id === selectedId);

  async function submit(e) {
    e.preventDefault();
    if (submitting.current) return;

    if (!stars) {
      setError("Please choose a rating from 1 to 5 stars.");
      return;
    }
    if (!selected) return;

    submitting.current = true;
    setStatus("submitting");
    setError("");

    try {
      await postJSON(
        `/consultations/${selected.id}/rating`,
        { stars, feedback: feedback.trim() },
        { token: selected.token },
      );
      markRated(selected.id);
      refreshStats({ force: true });
      setStatus("success");
    } catch (err) {
      if (err.status === 409) {
        // Already rated (e.g. from another tab): don't count it twice.
        markRated(selected.id);
        setStatus("success");
      } else {
        setError(err.message);
        setStatus("idle");
      }
    } finally {
      submitting.current = false;
    }
  }

  function rateAnother() {
    setStars(0);
    setFeedback("");
    setError("");
    setStatus("idle");
  }

  const shown = hover || stars;

  return (
    <section className="max-w-3xl mx-auto px-4 sm:px-6 py-16" aria-labelledby="rating-heading">
      <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-6 sm:p-10 text-center">

        <h2 id="rating-heading" className="text-2xl sm:text-3xl font-bold">
          How was your ExpertOS experience?
        </h2>

        <p className="text-gray-500 mt-3">
          Help us improve your AI consulting experience. Your feedback matters.
        </p>

        {status === "success" && (
          <div className="mt-8" role="status">
            <p className="text-4xl" aria-hidden="true">🎉</p>
            <p className="mt-3 text-lg font-semibold text-gray-900">Thank you for helping us improve ExpertOS!</p>
            {candidates.length > 0 && (
              <button onClick={rateAnother} className="mt-4 text-sm text-indigo-600 hover:underline">
                Rate another consultation
              </button>
            )}
          </div>
        )}

        {status !== "success" && !selected && (
          <div className="mt-8 bg-slate-50 rounded-2xl p-6">
            <p className="text-gray-700">
              {listConsultations().length > 0
                ? "You've rated all the consultations from this browser. Thank you!"
                : "Ratings are tied to a completed consultation, so each one counts once. Finish a consultation and you can rate it here."}
            </p>
            <Link
              to="/experts"
              className="inline-block mt-4 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-full font-semibold"
            >
              Start a consultation
            </Link>
          </div>
        )}

        {status !== "success" && selected && (
          <form onSubmit={submit} className="mt-8 text-left" noValidate>

            {candidates.length > 1 ? (
              <div>
                <label htmlFor="rating-consultation" className="block text-sm font-medium text-gray-700">
                  Consultation
                </label>
                <select
                  id="rating-consultation"
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
                  className="mt-1 w-full border border-slate-200 rounded-xl px-4 py-3 bg-white"
                >
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label || "Consultation"} — {formatDate(c.createdAt)}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <p className="text-sm text-gray-500 text-center">
                Rating: <span className="font-medium text-gray-700">{selected.label || "your consultation"}</span>
                {selected.createdAt && ` (${formatDate(selected.createdAt)})`}
              </p>
            )}

            <fieldset className="mt-6 text-center">
              <legend className="sr-only">Rating from 1 to 5 stars</legend>
              <div className="inline-flex gap-1" onMouseLeave={() => setHover(0)}>
                {[1, 2, 3, 4, 5].map((value) => (
                  <label
                    key={value}
                    className="cursor-pointer p-1 rounded-lg focus-within:ring-2 focus-within:ring-indigo-500"
                    onMouseEnter={() => setHover(value)}
                  >
                    <input
                      type="radio"
                      name="stars"
                      value={value}
                      checked={stars === value}
                      onChange={() => {
                        setStars(value);
                        setError("");
                      }}
                      className="sr-only"
                      aria-label={`${value} star${value === 1 ? "" : "s"}: ${LABELS[value]}`}
                    />
                    <svg
                      viewBox="0 0 24 24"
                      className={`w-10 h-10 sm:w-11 sm:h-11 transition ${value <= shown ? "text-amber-400" : "text-slate-300"}`}
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3 6.1 20.6l1.3-6.6L2.5 9.4l6.6-.8L12 2.5z" />
                    </svg>
                  </label>
                ))}
              </div>
              <p className="mt-2 h-5 text-sm font-medium text-gray-700" aria-live="polite">
                {shown ? `${shown} of 5: ${LABELS[shown]}` : "Select a rating"}
              </p>
            </fieldset>

            <label htmlFor="rating-feedback" className="block mt-6 text-sm font-medium text-gray-700">
              Feedback <span className="font-normal text-gray-400">(optional)</span>
            </label>
            <textarea
              id="rating-feedback"
              rows={4}
              maxLength={FEEDBACK_MAX}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="What worked well? What should we improve?"
              className="mt-1 w-full border border-slate-200 rounded-2xl px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-xs text-gray-400 text-right">{feedback.length}/{FEEDBACK_MAX}</p>

            {error && (
              <p className="mt-2 text-sm text-red-600" role="alert">{error}</p>
            )}

            <div className="text-center mt-4">
              <button
                type="submit"
                disabled={status === "submitting"}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-3 rounded-full font-semibold"
              >
                {status === "submitting" ? "Submitting..." : "Submit Rating"}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

export default RatingSection;
