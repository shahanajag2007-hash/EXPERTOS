import Navbar from "../components/Navbar/Navbar";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import ExpertHeader from "../components/ExpertRoom/ExpertHeader";
import ConsultationWizard from "../components/ExpertRoom/ConsultationWizard";
import RecommendationReport from "../components/ExpertRoom/RecommendationReport";
import { experts, profileFor } from "../data/experts";
import ExpertChat from "../components/ExpertRoom/ExpertChat";
import { getRecommendation } from "../services/expertRecommendation";
import NotFound from "./NotFound";
import { useExpertStats } from "../hooks/useStats";
import { formatConsultations, formatRating, formatSatisfaction } from "../components/ExpertCards/expertStatsFormat";
import { rememberConsultation } from "../services/consultations";
import { useFileUploads } from "../services/files";
import {
  activeConversation, getConversation, setActiveConversation, useConversationList,
} from "../services/history";
import ConversationHistory from "../components/History/ConversationHistory";
import DownloadReportButton from "../components/Report/DownloadReportButton";
import { expertRoomReport } from "../services/reportExport";

function ExpertRoom() {
  const { id } = useParams();
  const expert = experts[id];

  if (!expert) {
    return (
      <NotFound
        title="Expert not found"
        message={`There is no expert called "${id}". Choose one of the available experts instead.`}
      />
    );
  }

  // Keyed by expert so switching rooms never shows the previous expert's
  // answers, report or chat.
  return <ExpertRoomSession key={expert.id} expert={expert} />;
}

// Real statistics for this expert (GET /stats); see hooks/useStats.js.
function ExpertStatTiles({ expertKey }) {
  const { expertStats } = useExpertStats(expertKey);
  const rating = formatRating(expertStats);

  const tiles = [
    { label: "Consultations", value: expertStats ? String(expertStats.consultations) : "—" },
    { label: "Rating", value: rating.value, detail: rating.detail },
    { label: "Satisfied", value: formatSatisfaction(expertStats), detail: expertStats?.ratings ? "4–5 stars" : "" },
  ];

  return (
    <div className="mt-8">
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((tile) => (
          <div key={tile.label} className="bg-slate-50 rounded-2xl p-3">
            <p className="text-gray-500 text-xs">{tile.label}</p>
            <p className="text-lg font-bold mt-1 leading-tight">{tile.value}</p>
            {tile.detail && <p className="text-xs text-gray-400 mt-1">{tile.detail}</p>}
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400 mt-3">
        {formatConsultations(expertStats)} recorded on this ExpertOS installation.
      </p>
    </div>
  );
}

function ExpertRoomSession({ expert }) {
    const navigate = useNavigate();
    const { state } = useLocation();
    const firstName = expert.name.split(" ")[0];

    const [phase, setPhase] = useState("discovery");
    const [recommendation, setRecommendation] = useState(null);
    // { message, retryAt, attempt } while the latest request has failed.
    const [recommendationError, setRecommendationError] = useState(null);
    const [failedAttempts, setFailedAttempts] = useState(0);
    // Blocks overlapping requests (double clicks) before React re-renders, so
    // one click can never produce two reports or two consultation records.
    const inFlight = useRef(false);
    // A problem described elsewhere (AI Guide, Design Advisor) pre-fills the wizard.
    const [answers, setAnswers] = useState(() =>
      state?.problem ? { description: state.problem } : {}
    );

    // Project files (Design Advisor screenshots arrive already uploaded).
    const uploads = useFileUploads({ initial: state?.files || [] });

    // The saved conversation this room shows (services/history.js).
    const slot = `room.${expert.id}`;
    const [conversationId, setConversationId] = useState(null);
    const [savedMessages, setSavedMessages] = useState([]);
    const [conversationFiles, setConversationFiles] = useState([]);
    const [chatMessages, setChatMessages] = useState([]);
    const [chatVersion, setChatVersion] = useState(0);
    const [openError, setOpenError] = useState("");
    const history = useConversationList({ kind: "expert_room", expert: expert.shortRole });

    // Two separate identities:
    //   expert     the room's expert (from the URL): page heading, profile
    //              card, stats, expertise, conversation list. Never changes
    //              inside this room.
    //   activeKey  the chatbot's active role: who answers in the chat. It
    //              changes when the user asks for another expert; the backend
    //              decides and saves it per conversation (active_expert).
    const [activeKey, setActiveKey] = useState(expert.shortRole);
    const activeChatRole = profileFor(activeKey) || expert;

    function showConversation(data) {
        setConversationId(data.id);
        setActiveConversation(slot, data.id);
        setAnswers(data.answers || {});
        setRecommendation(data.report || null);
        setSavedMessages(data.messages || []);
        setConversationFiles(data.files || []);
        setActiveKey(data.active_expert || expert.shortRole);
        setChatMessages([]);
        setRecommendationError(null);
        setChatVersion((v) => v + 1);
        setPhase(data.report ? "report" : "discovery");
    }

    async function openConversation(id, { silent = false } = {}) {
        setOpenError("");
        try {
            showConversation(await getConversation(id));
            uploads.clear();
        } catch (e) {
            if (silent) setActiveConversation(slot, null);
            else setOpenError(e.message);
        }
    }

    function startNewConversation() {
        setConversationId(null);
        setActiveConversation(slot, null);
        setAnswers({});
        setRecommendation(null);
        setRecommendationError(null);
        setSavedMessages([]);
        setConversationFiles([]);
        setActiveKey(expert.shortRole);
        setChatMessages([]);
        uploads.clear();
        setPhase("discovery");
    }

    // After a reload, continue the conversation that was open (unless this
    // visit brings a new problem from the AI Guide or Design Advisor).
    useEffect(() => {
        if (state?.problem || state?.files?.length) return undefined;
        const id = activeConversation(slot);
        if (!id) return undefined;
        let cancelled = false;
        getConversation(id)
            .then((data) => {
                if (!cancelled) showConversation(data);
            })
            .catch(() => setActiveConversation(slot, null));
        return () => {
            cancelled = true;
        };
        // Runs once per room; showConversation only uses stable setters.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function requestRecommendation(currentAnswers) {
        if (inFlight.current) return;
        inFlight.current = true;

        setAnswers(currentAnswers);
        setRecommendation(null);
        setRecommendationError(null);
        setPhase("analysis");

        try {
            const result = await getRecommendation(expert.shortRole, currentAnswers, {
                fileIds: uploads.ids,
                conversationId,
            });
            rememberConsultation(result.consultation, {
                kind: "expert_room",
                label: `${expert.shortRole} recommendation`,
            });
            setFailedAttempts(0);
            setRecommendation(result);
            setConversationId(result.conversation_id);
            setActiveConversation(slot, result.conversation_id);
            history.refresh();
            // Show what was saved (earlier messages stay when answers are revised).
            try {
                const saved = await getConversation(result.conversation_id);
                setSavedMessages(saved.messages || []);
                setConversationFiles(saved.files || []);
                setActiveKey(saved.active_expert || expert.shortRole);
            } catch {
                // The report is shown regardless; the history list can reopen it.
            }
            setChatMessages([]);
            setChatVersion((v) => v + 1);
            setPhase("report");
        } catch (e) {
            const attempt = failedAttempts + 1;
            setFailedAttempts(attempt);
            setRecommendationError({ message: e.message, retryAt: e.retryAt || null, attempt });
        } finally {
            inFlight.current = false;
        }
    }

    function inviteAnotherExpert() {
        navigate("/panel", {
            state: {
                problem: answers.description || "",
                projectName: answers.project_name || "",
                experts: [expert.shortRole],
            },
        });
    }

  return (

    <>

      <Navbar />

      <div className="min-h-screen bg-slate-100">

        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 sm:py-10 space-y-8">

          <Link
            to="/experts"
            className="inline-flex items-center text-sm font-medium text-gray-500 hover:text-indigo-600 transition"
          >
            ← All Experts
          </Link>

         <ExpertHeader expert={expert} />

          <div className="grid lg:grid-cols-3 gap-8">

            <div className="lg:col-span-2 space-y-8 min-w-0">

                {phase === "discovery" && (

  <ConsultationWizard

      key={`wizard-${chatVersion}`}

      expert={expert}

      initialAnswers={answers}

      onReview={requestRecommendation}

      uploads={uploads}

  />

)}

{phase === "analysis" && (

  <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm p-8 sm:p-16 text-center">

    {!recommendationError ? (

      <>

        <div className="text-7xl animate-pulse">

          🧠

        </div>

        <h2 className="text-3xl sm:text-4xl font-bold mt-8">

          {firstName} is Reviewing Your Project

        </h2>

        <p className="text-gray-500 mt-6 max-w-xl mx-auto leading-8">

          {expert.analysisText}

          <br />

          Gathering project context...

          <br />

          Preparing recommendations...

        </p>

        <div
          className="mt-10 mx-auto h-10 w-10 rounded-full border-4 border-indigo-200 border-t-indigo-600 animate-spin"
          role="status"
          aria-label="Loading recommendation"
        />

      </>

    ) : (

      <>

        <div className="text-6xl">⚠️</div>

        <h2 className="text-2xl sm:text-3xl font-bold mt-6">

          {firstName} couldn't finish the review

        </h2>

        <p className="text-gray-500 mt-4 max-w-xl mx-auto leading-7" role="alert">

          {recommendationError.message}

        </p>

        {recommendationError.retryAt && (

          <p className="text-sm text-gray-500 mt-3">

            Expected to be available again around{" "}
            {recommendationError.retryAt.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}{" "}
            (your local time).

          </p>

        )}

        {recommendationError.attempt > 1 && (

          <p className="text-sm text-amber-700 mt-3">

            Still unavailable after {recommendationError.attempt} attempts. Your answers are kept on this page while it stays open.

          </p>

        )}

        <div className="mt-10 flex flex-wrap justify-center gap-4">

          <button

            onClick={() => requestRecommendation(answers)}

            className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-2xl font-semibold"

          >

            Try Again

          </button>

          <button

            onClick={() => setPhase("discovery")}

            className="border border-slate-300 hover:bg-slate-50 px-8 py-4 rounded-2xl font-semibold"

          >

            ← Edit Answers

          </button>

        </div>

      </>

    )}

  </div>

)}

{phase === "report" && (

  <div className="space-y-8">

   <button

      onClick={() => setPhase("discovery")}

      className="text-sm font-medium text-gray-500 hover:text-indigo-600 transition"

   >

      ← Revise answers

   </button>

   <RecommendationReport

      expert={expert}

      report={recommendation}

      actions={recommendation && (
        <DownloadReportButton
          build={() => expertRoomReport({
            expert,
            answers,
            report: recommendation,
            messages: chatMessages.length
              ? chatMessages.slice(1)
              : savedMessages.map((m) => (m.type === "system"
                ? { type: "system", text: m.message }
                : { sender: m.sender, text: m.message, expertName: m.expert?.name })),
            files: conversationFiles,
          })}
        />
      )}

  />

   <ExpertChat
              key={`chat-${conversationId || "new"}-${chatVersion}`}
              expert={expert}
              activeExpert={activeChatRole}
              onSwitch={setActiveKey}
              project={answers.description || answers.project_name || ""}
              analysis={recommendation || {}}
              conversationId={conversationId}
              initialMessages={savedMessages}
              onExchange={(messages) => {
                setChatMessages(messages);
                history.refresh();
              }}
            />

  </div>

)}

            </div>

            <div>

                <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm p-6 sm:p-8 lg:sticky lg:top-28">

                    <div className="flex items-center gap-4">

                    <div
                      className={`w-16 h-16 shrink-0 rounded-2xl ${expert.color} flex items-center justify-center text-3xl text-white`}
                    >

                      {expert.icon}

                    </div>

                    <div>

                        <h2 className="text-2xl font-bold">

                        {expert.name}

                        </h2>

                        <p className="text-indigo-600">

                        {expert.role}

                        </p>

                    </div>

                    </div>

                    <ExpertStatTiles expertKey={expert.shortRole} />

                    <hr className="my-8" />

                    <h3 className="font-bold text-lg">

                    Expertise

                    </h3>

                    <div className="flex flex-wrap gap-2 mt-5">

                    {expert.tags.map((item) => (

                    <span
                        key={item}
                        className="bg-indigo-100 text-indigo-700 px-3 py-2 rounded-full text-sm"
                    >

                        {item}

                    </span>

                    ))}

                    </div>

                    <button
                      onClick={inviteAnotherExpert}
                      className="w-full mt-8 bg-indigo-600 hover:bg-indigo-700 text-white py-4 rounded-2xl font-semibold"
                    >

                    Invite Another Expert →

                    </button>

                    <p className="text-xs text-gray-500 mt-3 text-center">

                    Opens the Expert Panel with {firstName} selected and your project description carried over.

                    </p>

                    <hr className="my-8" />

                    {openError && (

                      <p className="text-sm text-red-600 mb-3" role="alert">{openError}</p>

                    )}

                    <ConversationHistory
                      list={history}
                      activeId={conversationId}
                      onOpen={(id) => openConversation(id)}
                      onNew={startNewConversation}
                      onDeleted={(id) => {
                        if (id === conversationId) startNewConversation();
                      }}
                    />

                </div>

                </div>
          </div>

        </div>

      </div>

    </>

  );

}

export default ExpertRoom;
