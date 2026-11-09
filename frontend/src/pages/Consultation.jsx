import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Navbar from "../components/Navbar/Navbar";
import ConsultationHeader from "../components/Consultation/ConsultationHeader";
import ExecutiveSummary from "../components/Consultation/ExecutiveSummary";
import AnalysisCard from "../components/Consultation/AnalysisCard";
import FollowUpChat from "../components/Consultation/FollowUpChat";
import RelatedTech from "../components/Consultation/RelatedTech";
import { postJSON } from "../services/api";
import { rememberConsultation } from "../services/consultations";
import { DOCUMENT_ACCEPT, useFileUploads } from "../services/files";
import {
  activeConversation, getConversation, setActiveConversation, useConversationList,
} from "../services/history";
import { ChooseFilesButton, FileList } from "../components/FileUpload/FileList";
import ConversationHistory from "../components/History/ConversationHistory";
import DownloadReportButton from "../components/Report/DownloadReportButton";
import { consultationReport } from "../services/reportExport";

const SLOT = "consultation";

function Consultation() {

  const navigate = useNavigate();

  const [project, setProject] = useState("");

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState("");

  const [consultationStarted, setConsultationStarted] = useState(false);

  const [expert, setExpert] = useState(null);

  const [analysis, setAnalysis] = useState(null);

  const uploads = useFileUploads();

  // The saved conversation (services/history.js) behind this consultation.
  const [conversationId, setConversationId] = useState(null);
  const [savedMessages, setSavedMessages] = useState([]);
  const [chatHistory, setChatHistory] = useState([]);
  const [conversationFiles, setConversationFiles] = useState([]);
  const history = useConversationList({ kind: "quick_consultation" });

  function showConversation(data) {
    setProject(data.project || "");
    setAnalysis(data.report || null);
    setExpert(data.expert || null);
    setSavedMessages(data.messages || []);
    setChatHistory(data.messages || []);
    setConversationFiles(data.files || []);
    setConversationId(data.id);
    setActiveConversation(SLOT, data.id);
    setConsultationStarted(Boolean(data.report));
    setError("");
  }

  async function openConversation(id, { silent = false } = {}) {
    try {
      showConversation(await getConversation(id));
    } catch (err) {
      if (silent) setActiveConversation(SLOT, null);
      else setError(err.message);
    }
  }

  // After a reload, continue the consultation that was open.
  useEffect(() => {
    const id = activeConversation(SLOT);
    if (!id) return undefined;
    let cancelled = false;
    getConversation(id)
      .then((data) => {
        if (!cancelled) showConversation(data);
      })
      .catch(() => setActiveConversation(SLOT, null));
    return () => {
      cancelled = true;
    };
    // Runs once; showConversation only uses stable setters.
  }, []);

  async function startConsultation() {

    if (!project.trim()) {

      setError("Please describe your project so an expert can review it.");

      return;

    }

    setError("");

    setLoading(true);

    try {

      const data = await postJSON("/analyze", {
        prompt: project,
        file_ids: uploads.ids,
      });

      if (!data.analysis) {
        throw new Error("The consultation service returned an incomplete response. Please try again.");
      }

      rememberConsultation(data.consultation, { kind: "quick_consultation", label: "Start Consultation analysis" });

      setExpert(data.expert);

      setAnalysis(data.analysis);

      setConversationId(data.conversation_id);

      setActiveConversation(SLOT, data.conversation_id);

      setSavedMessages([]);

      setChatHistory([]);

      setConversationFiles(uploads.done);

      uploads.clear();

      history.refresh();

      setConsultationStarted(true);

    } catch (err) {

      setError(err.message);

    }

    setLoading(false);

  }

  function consultPanel() {

    navigate("/panel", { state: { problem: project } });

  }

  function startOver() {

    setConsultationStarted(false);

    setExpert(null);

    setAnalysis(null);

    setError("");

    setConversationId(null);

    setActiveConversation(SLOT, null);

    setSavedMessages([]);

    setChatHistory([]);

  }

  return (

    <>

    <Navbar />

    <div className="min-h-screen bg-slate-50">

      <div className="max-w-6xl mx-auto py-10 sm:py-16 px-4 sm:px-6">

        {!consultationStarted && (

          <div className="bg-white rounded-3xl shadow-xl p-6 sm:p-10">

            <h1 className="text-3xl sm:text-4xl font-bold">

              Start Consultation

            </h1>

            <p className="text-gray-500 mt-3">

              Describe your software project in detail.

              The most suitable expert will review your project
              before joining the consultation.

            </p>

            <textarea

              rows={10}

              value={project}

              onChange={(e) =>
                setProject(e.target.value)
              }

              disabled={loading}

              placeholder="Describe your project..."

              aria-label="Project description"

              className="w-full mt-8 border rounded-3xl p-6 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"

            />

            {error && (

              <div className="mt-6 bg-red-50 border border-red-200 text-red-700 rounded-2xl px-5 py-4" role="alert">

                {error}

              </div>

            )}

            <div className="flex flex-wrap gap-4 mt-8">

              <button

                onClick={startConsultation}

                disabled={loading || uploads.uploading}

                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-3 rounded-full"

              >

                {loading ? "Preparing Consultation..." : uploads.uploading ? "Uploading files..." : error ? "Try Again →" : "Start Consultation →"}

              </button>

              <button

                onClick={consultPanel}

                disabled={loading}

                className="border px-6 py-3 rounded-full hover:bg-gray-100 disabled:opacity-50"

              >

                👥 Consult Multiple Experts

              </button>

            </div>

            <p className="text-sm text-gray-500 mt-4">

              📎{" "}
              <ChooseFilesButton
                uploads={uploads}
                accept={DOCUMENT_ACCEPT}
                label="Attach files"
                className="text-indigo-600 hover:underline font-medium"
              />{" "}
              (PDF, Word, Excel, PowerPoint, ZIP, text, code or images; up to 5 files, 10 MB each). The expert reads their content.

            </p>

            <FileList uploads={uploads} />

            {history.conversations.length > 0 && (

              <div className="mt-10 border-t pt-8">

                <ConversationHistory
                  list={history}
                  activeId={conversationId}
                  onOpen={(id) => openConversation(id)}
                  title="Previous consultations"
                />

              </div>

            )}

          </div>

        )}

        {loading && (

          <div className="bg-white rounded-3xl shadow-xl mt-10 p-6 sm:p-10" role="status">

            <h2 className="text-2xl sm:text-3xl font-bold">

              Preparing Consultation...

            </h2>

            <div className="mt-8 space-y-5 animate-pulse">

              <p>🧠 Understanding your project...</p>

              <p>👨‍💻 Selecting the most suitable expert...</p>

              <p>📝 Preparing recommendations...</p>

            </div>

          </div>

        )}

        {consultationStarted && analysis && (
                    <>

            <div className="flex flex-wrap justify-between items-center gap-4 mb-6">

              <button

                onClick={startOver}

                className="text-sm font-medium text-gray-500 hover:text-indigo-600 transition"

              >

                ← Edit project description

              </button>

              <div className="flex flex-wrap gap-3">

              <DownloadReportButton
                build={() => consultationReport({ project, analysis, messages: chatHistory, files: conversationFiles })}
                className="text-sm font-medium text-gray-600 border border-slate-200 hover:border-slate-400 px-5 py-2 rounded-full transition"
              />

              <button

                onClick={consultPanel}

                className="text-sm font-medium text-indigo-600 border border-indigo-200 hover:border-indigo-400 px-5 py-2 rounded-full transition"

              >

                👥 Get a second opinion from the Expert Panel

              </button>

              </div>

            </div>

            <ConsultationHeader expert={expert} />

            <ExecutiveSummary
              summary={analysis.recommendation}
            />

            <div className="mt-8 space-y-6">

              <AnalysisCard
                title="🏗 Architecture Overview"
                content={analysis.architecture}
              />

              <AnalysisCard
                title="💻 Recommended Tech Stack"
                content={analysis.tech_stack}
              />

              <AnalysisCard
                title="🗄 Database Recommendation"
                content={analysis.database}
              />

              <AnalysisCard
                title="🔒 Security Suggestions"
                content={analysis.security}
              />

              <AnalysisCard
                title="🚀 Deployment Strategy"
                content={analysis.deployment}
              />

              <AnalysisCard
                title="⭐ Final Recommendation"
                content={analysis.recommendation}
              />

              <RelatedTech
                analysis={analysis}
                expert={expert}
                project={project}
              />

              <FollowUpChat
                  key={conversationId || "new"}
                  expert={expert}
                  setExpert={setExpert}
                  conversationId={conversationId}
                  initialMessages={savedMessages}
                  onHistory={(messages) => {
                    setChatHistory(messages);
                    history.refresh();
                  }}
/>

            </div>

          </>

        )}

      </div>

    </div>

    </>

  );

}

export default Consultation;
