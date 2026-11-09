import { useState } from "react";
import { useLocation } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";
import { streamSSE } from "../services/api";
import { rememberConsultation } from "../services/consultations";
import LiveConsultationRoom from "../components/LiveConsultation/LiveConsultationRoom";

const DEFAULT_PANEL = [
  "Software Architect",
  "Database Engineer",
  "Security Expert",
  "Cloud Consultant",
];

// Maps frontend display key → backend expert key (must match experts.json)
const EXPERT_OPTIONS = [
  { key: "Software Architect", label: "Software Architect", icon: "💻" },
  { key: "Database Engineer",  label: "Database Engineer",  icon: "🗄️" },
  { key: "Security Expert",    label: "Security Expert",    icon: "🛡️" },
  { key: "Cloud Consultant",   label: "Cloud Consultant",   icon: "☁️" },
  { key: "DevOps Engineer",    label: "DevOps Engineer",    icon: "⚙️" },
  { key: "Design Advisor",     label: "Design Advisor",     icon: "🎨" },
];

// ─── Helper: render markdown-ish response text ───────────────────────────────
// Renders **bold** spans as text (never as HTML), so model output can't inject markup.
function Inline({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={i} className="font-semibold text-gray-900">{part.slice(2, -2)}</strong>
      : part,
  );
}

function ResponseText({ text }) {
  if (!text) return null;
  // Split on ## headings and render each section
  const lines = text.split("\n");
  return (
    <div className="space-y-2 text-sm leading-relaxed text-gray-700">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (/^#{2,3} /.test(trimmed)) {
          return (
            <p key={i} className="font-bold text-gray-900 mt-4 mb-1">
              <Inline text={trimmed.replace(/^#{2,3} /, "")} />
            </p>
          );
        }
        if (/^[-•*] /.test(trimmed)) {
          return (
            <p key={i} className="pl-4">
              • <Inline text={trimmed.slice(2)} />
            </p>
          );
        }
        if (trimmed === "") return <div key={i} className="h-1" />;
        return <p key={i}><Inline text={line} /></p>;
      })}
    </div>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  if (status === "success") {
    return (
      <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-1 rounded-full font-medium">
        ✓ Complete
      </span>
    );
  }
  if (status === "loading") {
    return (
      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full font-medium animate-pulse">
        Analysing...
      </span>
    );
  }
  return (
    <span className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded-full font-medium">
      Unavailable
    </span>
  );
}

// ─── Single expert response card ─────────────────────────────────────────────
function ExpertResponseCard({ result }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-4 sm:px-6 py-4 hover:bg-slate-50 transition"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl">{result.expert_emoji}</span>
          <div className="text-left">
            <p className="font-bold text-gray-900">{result.expert_name}</p>
            <p className="text-sm text-gray-500">{result.expert_role}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={result.status} />
          <span className="text-gray-400 text-sm">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Body */}
      {expanded && (
        <div className="px-4 sm:px-6 pb-6 border-t border-slate-100 pt-4 break-words">
          {result.status === "loading" ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-3 bg-slate-200 rounded w-3/4" />
              <div className="h-3 bg-slate-200 rounded w-full" />
              <div className="h-3 bg-slate-200 rounded w-5/6" />
            </div>
          ) : (
            <ResponseText text={result.response} />
          )}
        </div>
      )}
    </div>
  );
}

// ─── Synthesis panel ─────────────────────────────────────────────────────────
function SynthesisPanel({ synthesis }) {
  if (!synthesis) return null;

  const sections = [
    { label: "🤝 Agreements",          key: "agreements" },
    { label: "⚖️ Disagreements",       key: "disagreements" },
    { label: "🎯 Top Priorities",       key: "top_priorities" },
    { label: "⚠️ Cross-Domain Risks",   key: "risks" },
    { label: "🚀 Recommended Next Steps", key: "recommended_next_steps" },
  ];

  return (
    <div className="bg-white rounded-2xl border border-indigo-200 shadow-sm overflow-hidden mt-6">
      <div className="bg-indigo-50 px-6 py-4 border-b border-indigo-100">
        <h3 className="font-bold text-indigo-900 text-lg">
          🤝 Panel Consensus
        </h3>
        <p className="text-sm text-indigo-600 mt-1">
          Combined analysis from all experts
        </p>
      </div>

      {/* Verdict */}
      {synthesis.panel_verdict && (
        <div className="px-6 py-5 bg-indigo-600 text-white">
          <p className="text-sm font-semibold uppercase tracking-wider opacity-80 mb-2">
            Panel Verdict
          </p>
          <p className="leading-relaxed">{synthesis.panel_verdict}</p>
        </div>
      )}

      {/* Sections */}
      <div className="divide-y divide-slate-100">
        {sections.map(({ label, key }) => (
          synthesis[key] ? (
            <div key={key} className="px-6 py-4">
              <p className="font-semibold text-gray-800 text-sm mb-1">{label}</p>
              <p className="text-gray-600 text-sm leading-relaxed">{synthesis[key]}</p>
            </div>
          ) : null
        ))}
      </div>
    </div>
  );
}

// ─── Why no combined recommendation is shown ─────────────────────────────────
function SynthesisNotice({ error, successCount, total }) {
  let message = error;

  if (!message) {
    if (successCount === 0) {
      message = "No expert could respond this time, so there is nothing to combine. Please try again in a moment.";
    } else if (total === 1) {
      message = "Select two or more experts to get a combined panel recommendation.";
    } else if (successCount === 1) {
      message = "Only one expert responded successfully, so a combined recommendation wasn't generated. Try again to hear from the rest of the panel.";
    }
  }

  if (!message) return null;

  return (
    <div className="mt-6 bg-amber-50 border border-amber-200 text-amber-800 rounded-2xl px-6 py-4 text-sm" role="status">
      {message}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
function ExpertPanel() {

  // Other pages (Start Consultation, Expert Rooms) can hand over the problem
  // and the experts already consulted.
  const { state } = useLocation();

  const [selectedExperts, setSelectedExperts] = useState(() => {
    const handedOver = (state?.experts || []).filter((key) =>
      EXPERT_OPTIONS.some((o) => o.key === key)
    );
    return handedOver.length > 0 ? handedOver : DEFAULT_PANEL;
  });

  const [projectName, setProjectName] = useState(state?.projectName || "");
  const [problem,     setProblem]     = useState(state?.problem || "");
  const [context,     setContext]     = useState("");

  const [loading,   setLoading]   = useState(false);
  const [responses, setResponses] = useState([]);
  const [synthesis, setSynthesis] = useState(null);
  const [synthesisError, setSynthesisError] = useState("");
  const [error,     setError]     = useState("");
  const [panelDone, setPanelDone] = useState(false);
  const [slow,      setSlow]      = useState(false);

  // Set when the panel completed; needed (with its token) for the live room.
  const [consultation, setConsultation] = useState(null);
  const [liveOpen,     setLiveOpen]     = useState(false);
  const [liveStarted,  setLiveStarted]  = useState(false);

  function toggleExpert(key) {
    setSelectedExperts((prev) =>
      prev.includes(key) ? prev.filter((e) => e !== key) : [...prev, key]
    );
  }

  async function assemblePanel() {
    if (!problem.trim()) {
      setError("Please describe your project or problem.");
      return;
    }
    if (selectedExperts.length === 0) {
      setError("Please select at least one expert.");
      return;
    }

    setError("");
    setLoading(true);
    setPanelDone(false);
    setSynthesis(null);
    setSynthesisError("");

    // Show skeleton cards immediately
    const skeletons = selectedExperts.map((key) => {
      const opt = EXPERT_OPTIONS.find((o) => o.key === key) || {};
      return {
        expert_key:   key,
        expert_name:  key,
        expert_role:  "",
        expert_emoji: opt.icon || "👤",
        status:       "loading",
        response:     "",
      };
    });
    setResponses(skeletons);

    setConsultation(null);
    setLiveOpen(false);
    setLiveStarted(false);
    setSlow(false);

    const fullProblem = projectName.trim()
      ? `Project: ${projectName}\n\n${problem}`
      : problem;

    let received = 0;

    try {
      // Each expert's result arrives as soon as it's ready, so the first
      // answers are readable while slower experts are still working.
      await streamSSE("/panel/stream", {
        experts: selectedExperts,
        problem: fullProblem,
        context,
      }, {
        onSlow: () => setSlow(true),
        onEvent: (event, data) => {
          if (event === "expert") {
            received += 1;
            setResponses((prev) => prev.map((r) => (r.expert_key === data.expert_key ? data : r)));
          } else if (event === "synthesis") {
            setSynthesis(data.synthesis || null);
            setSynthesisError(data.synthesis_error || "");
          } else if (event === "done") {
            setResponses(data.responses);
            setSynthesis(data.synthesis || null);
            setSynthesisError(data.synthesis_error || "");
            if (data.consultation) {
              setConsultation(data.consultation);
              rememberConsultation(data.consultation, { kind: "panel", label: "Expert Panel consultation" });
            }
            setPanelDone(true);
          }
        },
      });

    } catch (err) {
      if (received > 0) {
        // Keep the experts who already answered; mark the rest as interrupted.
        setResponses((prev) => prev.map((r) => (
          r.status === "loading"
            ? { ...r, status: "error", response: "This expert's answer didn't arrive because the connection was interrupted." }
            : r
        )));
        setPanelDone(true);
      } else {
        setResponses([]);
      }
      setError(err.message);
    }

    setLoading(false);
    setSlow(false);
  }

  function resetPanel() {
    setResponses([]);
    setSynthesis(null);
    setSynthesisError("");
    setPanelDone(false);
    setError("");
    setLoading(false);
    setConsultation(null);
    setLiveOpen(false);
    setLiveStarted(false);
  }

  const successCount = responses.filter((r) => r.status === "success").length;
  const expertsDone = responses.length > 0 && responses.every((r) => r.status !== "loading");

  return (
    <>
      <Navbar />

      <div className="min-h-screen bg-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 sm:py-16">

          {/* Page header */}
          <p className="text-indigo-600 uppercase tracking-widest font-semibold">
            AI Expert Panel
          </p>

          <h1 className="text-4xl sm:text-5xl font-bold mt-4">
            Multiple Experts,
            <br />
            One Decision.
          </h1>

          <p className="text-gray-600 mt-6 max-w-3xl text-lg">
            Submit your project once and let multiple AI specialists analyse it
            simultaneously. Each expert provides their domain perspective, then
            the panel synthesises a combined recommendation.
          </p>

          {/* ── Input + Expert Selection ── */}
          {!panelDone && (
            <div className="grid lg:grid-cols-2 gap-8 lg:gap-10 mt-10 sm:mt-14">

              {/* Left – Input */}
              <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8">
                <h2 className="text-2xl font-bold">Project Overview</h2>

                <input
                  className="w-full mt-8 border border-slate-200 rounded-2xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  placeholder="Project Name (optional)"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                />

                <textarea
                  rows={6}
                  className="w-full mt-4 border border-slate-200 rounded-2xl px-5 py-4 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  placeholder="Describe your project, the problem you're solving, or the question you need answered..."
                  value={problem}
                  onChange={(e) => setProblem(e.target.value)}
                />

                <textarea
                  rows={3}
                  className="w-full mt-4 border border-slate-200 rounded-2xl px-5 py-4 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  placeholder="Additional context (tech stack, constraints, goals — optional)"
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                />

                {error && (
                  <p className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-2xl px-4 py-3 text-sm" role="alert">
                    {error}
                  </p>
                )}

                <div className="mt-8">
                  <h3 className="text-xl font-bold">Select Experts</h3>
                  <p className="text-gray-500 mt-2 text-sm">
                    Choose the specialists you want in your consultation panel.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-5">
                    {EXPERT_OPTIONS.map(({ key, label, icon }) => {
                      const active = selectedExperts.includes(key);
                      return (
                        <label
                          key={key}
                          className={`flex items-center gap-3 border rounded-2xl p-4 cursor-pointer transition ${
                            active
                              ? "border-indigo-400 bg-indigo-50"
                              : "border-slate-200 hover:border-slate-300"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={active}
                            onChange={() => toggleExpert(key)}
                            className="accent-indigo-600"
                          />
                          <span className="text-sm font-medium">
                            {icon} {label}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <button
                  onClick={assemblePanel}
                  disabled={loading}
                  className="mt-8 w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-4 rounded-2xl font-semibold transition"
                >
                  {loading
                    ? `Consulting ${selectedExperts.length} Expert${selectedExperts.length === 1 ? "" : "s"}...`
                    : error
                      ? "Try Again →"
                      : `Assemble Expert Panel → (${selectedExperts.length} selected)`}
                </button>
              </div>

              {/* Right – Panel preview */}
              <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8">
                <h2 className="text-2xl font-bold">Panel Members</h2>
                <p className="text-gray-500 mt-2 text-sm">
                  {selectedExperts.length === 0
                    ? "No experts selected yet."
                    : `${selectedExperts.length} expert${selectedExperts.length > 1 ? "s" : ""} selected`}
                </p>

                <div className="grid grid-cols-2 gap-4 mt-6">
                  {selectedExperts.map((key) => {
                    const opt = EXPERT_OPTIONS.find((o) => o.key === key);
                    return (
                      <div
                        key={key}
                        className="rounded-2xl bg-slate-50 border border-slate-200 p-5 text-center"
                      >
                        <div className="text-3xl mb-2">{opt?.icon}</div>
                        <p className="text-sm font-semibold text-gray-800">
                          {opt?.label || key}
                        </p>
                      </div>
                    );
                  })}
                </div>

                {/* Workflow steps */}
                <div className="mt-8">
                  <h3 className="font-bold text-gray-800 mb-4">Panel Workflow</h3>
                  <div className="space-y-3">
                    {[
                      "📝 Project Submitted",
                      "⚡ Parallel Expert Analysis",
                      "🔍 Individual Reviews",
                      "🤝 Panel Synthesis",
                      "✅ Final Recommendation",
                    ].map((step, i) => (
                      <div
                        key={step}
                        className="flex items-center gap-3 text-sm text-gray-600"
                      >
                        <span className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center text-xs font-bold flex-shrink-0">
                          {i + 1}
                        </span>
                        {step}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Results ── */}
          {(responses.length > 0 || loading) && (
            <div className="mt-12">
              <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
                <div>
                  <h2 className="text-3xl font-bold">Panel Results</h2>
                  <p className="text-gray-500 mt-1 text-sm" aria-live="polite">
                    {panelDone
                      ? `${successCount} of ${responses.length} experts responded successfully`
                      : `${responses.filter((r) => r.status !== "loading").length} of ${responses.length} experts have answered`}
                  </p>
                </div>
                {panelDone && (
                  <button
                    onClick={resetPanel}
                    className="text-indigo-600 hover:text-indigo-800 border border-indigo-200 hover:border-indigo-400 px-5 py-2 rounded-full text-sm font-medium transition"
                  >
                    ← New Consultation
                  </button>
                )}
              </div>

              {/* Individual expert cards */}
              <div className="space-y-4">
                {responses.map((result) => (
                  <ExpertResponseCard
                    key={result.expert_key}
                    result={result}
                  />
                ))}
              </div>

              {panelDone && error && (
                <p className="mt-6 bg-red-50 border border-red-200 text-red-700 rounded-2xl px-5 py-4 text-sm" role="alert">
                  {error} The answers above are complete; select New Consultation to run the panel again.
                </p>
              )}

              {/* Synthesis */}
              {loading && expertsDone && successCount >= 2 && !synthesis && (
                <div className="mt-6 text-center text-gray-500 text-sm animate-pulse" role="status">
                  Combining the experts' answers into a panel recommendation...
                </div>
              )}

              {synthesis && (
                <SynthesisPanel synthesis={synthesis} />
              )}

              {panelDone && !synthesis && (
                <SynthesisNotice
                  error={synthesisError}
                  successCount={responses.filter((r) => r.status === "success").length}
                  total={responses.length}
                />
              )}

              {/* Loading hint */}
              {loading && !expertsDone && (
                <div className="mt-6 text-center text-gray-500 text-sm" role="status">
                  <span className="animate-pulse">Experts are analysing your project simultaneously. Answers appear as each one finishes.</span>
                  {slow && (
                    <span className="block mt-1 text-amber-700">This is taking longer than usual. Still waiting for the remaining experts.</span>
                  )}
                </div>
              )}

              {/* Live interaction */}
              {panelDone && consultation && successCount >= 2 && (
                <div className="mt-10">
                  {!liveOpen ? (
                    <div className="bg-white rounded-3xl border border-indigo-200 p-6 sm:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6">
                      <div>
                        <h3 className="text-2xl font-bold">
                          {liveStarted ? "Your live discussion is saved" : "Discuss this with the experts"}
                        </h3>
                        <p className="text-gray-500 mt-2 max-w-2xl">
                          Open a live room where the {successCount} AI experts debate trade-offs, respond to each
                          other and answer your questions, then wrap up with a summary of the discussion.
                        </p>
                      </div>
                      <button
                        onClick={() => {
                          setLiveOpen(true);
                          setLiveStarted(true);
                        }}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-2xl font-semibold shrink-0"
                      >
                        {liveStarted ? "Reopen Live Discussion →" : "Live Interaction with Experts →"}
                      </button>
                    </div>
                  ) : (
                    <LiveConsultationRoom
                      consultation={consultation}
                      onHide={() => setLiveOpen(false)}
                    />
                  )}
                </div>
              )}

              {panelDone && consultation && successCount === 1 && (
                <p className="mt-8 text-sm text-gray-500 text-center">
                  Live interaction needs at least two experts who answered. Run the panel again to include more experts.
                </p>
              )}
            </div>
          )}

        </div>
      </div>
    </>
  );
}

export default ExpertPanel;