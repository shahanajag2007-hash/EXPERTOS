import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON, postJSON, streamSSE } from "../../services/api";
import LiveSummary from "./LiveSummary";

export const UNLOCK_NOTICE = "You can discuss your queries and interact with the experts now.";

function newMessageId() {
  return globalThis.crypto?.randomUUID?.() || `m-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function ExpertAvatar({ expert, speaking }) {
  return (
    <span
      className={`w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center text-xl shrink-0 ${
        speaking ? "ring-2 ring-indigo-500 ring-offset-2 ring-offset-white" : ""
      }`}
      aria-hidden="true"
    >
      {expert?.emoji || "👤"}
    </span>
  );
}

function Message({ message, expert, streaming }) {
  if (message.role === "client") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] sm:max-w-xl">
          <p className="text-xs font-semibold text-gray-500 text-right mb-1">You (client)</p>
          <div className="bg-indigo-600 text-white rounded-3xl rounded-tr-md px-5 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <ExpertAvatar expert={expert} speaking={streaming} />
      <div className="max-w-[85%] sm:max-w-2xl min-w-0">
        <p className="text-xs font-semibold text-gray-700 mb-1">
          {expert?.first_name || "Expert"} <span className="font-normal text-gray-500">— {expert?.role} · AI expert</span>
        </p>
        <div className="bg-slate-100 rounded-3xl rounded-tl-md px-5 py-3 text-sm leading-relaxed text-gray-800 whitespace-pre-wrap break-words">
          {message.content}
          {streaming && <span className="inline-block w-2 h-4 ml-0.5 align-middle bg-indigo-400 animate-pulse" aria-hidden="true" />}
        </div>
      </div>
    </div>
  );
}

/**
 * Live room for a completed panel consultation. The session (transcript and
 * summary) lives on the backend, so hiding and reopening this component, or
 * reloading after a dropped connection, restores it.
 *
 * The backend decides the phase (session.phase):
 *   expert_discussion  the experts work through the agenda; this component
 *                      requests agenda rounds one after another automatically.
 *                      The message box is locked (the backend also rejects
 *                      client messages in this phase).
 *   user_interaction   agenda complete; the client can talk to the panel.
 *   closed             the Key Takeaways (LiveSummary) replace the room.
 */
function LiveConsultationRoom({ consultation, onHide }) {
  const token = consultation.token;

  const [session, setSession] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [running, setRunning] = useState(false);        // a round is streaming
  const [speaking, setSpeaking] = useState(null);       // { expert_key, text }
  const [slow, setSlow] = useState(false);
  const [notes, setNotes] = useState([]);               // per-round notices (skips, expert errors)
  const [error, setError] = useState(null);             // { message, retryable, body }
  const [input, setInput] = useState("");
  const [closing, setClosing] = useState(false);
  const [showContext, setShowContext] = useState(false);
  // Incremented after every round, so the automatic agenda loop runs again
  // even when React batches a quick round's running=true/false into one render.
  const [roundsFinished, setRoundsFinished] = useState(0);

  const abortRef = useRef(null);
  const inFlight = useRef(false);
  const bottomRef = useRef(null);
  const closingRef = useRef(false);

  const sessionId = session ? session.id : null;
  const experts = Object.fromEntries((session?.participants || []).map((p) => [p.key, p]));

  const resync = useCallback(async () => {
    if (!sessionId) return;
    try {
      setSession(await getJSON(`/live/sessions/${sessionId}`, { token }));
    } catch {
      // Keep what's on screen; the error banner explains the problem.
    }
  }, [sessionId, token]);

  const runRound = useCallback(async (body = {}) => {
    if (!sessionId || inFlight.current) return;
    inFlight.current = true;

    setRunning(true);
    setError(null);
    setNotes([]);
    setSlow(false);

    const controller = new AbortController();
    abortRef.current = controller;
    const agendaRound = body.message === undefined;
    let expertMessages = 0;
    let turnError = "";

    try {
      await streamSSE(`/live/sessions/${sessionId}/rounds`, body, {
        token,
        signal: controller.signal,
        onSlow: () => setSlow(true),
        onEvent: (event, data) => {
          if (event === "turn_start") {
            setSlow(false);
            setSpeaking({ expert_key: data.expert_key, text: "" });
          } else if (event === "token") {
            setSpeaking((prev) => ({ expert_key: data.expert_key, text: (prev?.text || "") + data.text }));
          } else if (event === "message") {
            setSpeaking(null);
            if (data.role === "expert") expertMessages += 1;
            setSession((prev) => (
              prev.messages.some((m) => m.id === data.id)
                ? prev
                : { ...prev, messages: [...prev.messages, data] }
            ));
          } else if (event === "turn_skipped") {
            setSpeaking(null);
            setNotes((n) => [...n, { key: data.expert_key, text: "had nothing to add" }]);
          } else if (event === "turn_error") {
            setSpeaking(null);
            turnError = turnError || data.error;
            setNotes((n) => [...n, { key: data.expert_key, text: `couldn't respond: ${data.error}`, error: true }]);
          } else if (event === "round_done") {
            // Never let a late round_done replace the closed session and its summary.
            setSession((prev) => (prev?.status === "closed" && prev.summary ? prev : data));
          }
        },
      });
      // An agenda round where no expert managed to speak would just repeat;
      // stop the automatic discussion and offer a retry instead.
      if (agendaRound && expertMessages === 0 && !closingRef.current) {
        setError({
          message: `The experts couldn't continue the discussion${turnError ? `: ${turnError}` : "."}`,
          retryable: true,
          body: {},
        });
      }
    } catch (err) {
      setSpeaking(null);
      if (err?.name !== "AbortError") {
        setError({ message: err.message, retryable: err.retryable !== false && err.status !== 403, body });
        await resync();   // pick up anything stored before the connection dropped
      }
    } finally {
      inFlight.current = false;
      abortRef.current = null;
      setRunning(false);
      setSlow(false);
      setRoundsFinished((n) => n + 1);
    }
  }, [sessionId, token, resync]);

  // Open (or reopen) the session.
  useEffect(() => {
    let cancelled = false;
    postJSON("/live/sessions", { consultation_id: consultation.id }, { token })
      .then((data) => !cancelled && setSession(data))
      .catch((err) => !cancelled && setLoadError(err.message));
    return () => {
      cancelled = true;
    };
  }, [consultation.id, token]);

  // The experts work through the whole agenda by themselves: request the next
  // agenda round whenever none is running, until the backend reports the
  // agenda complete. Stops on errors (Retry resumes) and when ending.
  const phase = session?.phase;
  const sessionBusy = session?.busy;
  useEffect(() => {
    if (phase !== "expert_discussion" || running || closing || error || sessionBusy) return undefined;
    const timer = setTimeout(() => runRound({}), 300);
    return () => clearTimeout(timer);
  }, [phase, running, closing, error, sessionBusy, runRound, roundsFinished]);

  // Another tab (or an interrupted request) holds the round lock: check back
  // until it's free, then the discussion continues from the saved state.
  useEffect(() => {
    if (!sessionBusy || running) return undefined;
    const timer = setTimeout(resync, 3000);
    return () => clearTimeout(timer);
  }, [sessionBusy, running, resync, session]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [session?.messages?.length, speaking?.text, notes.length]);

  function sendMessage(e) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || running || closing || !session?.can_message) return;
    setInput("");
    runRound({ message: text, message_id: newMessageId() });
  }

  async function endSession() {
    if (closing) return;
    // No new rounds start. A turn that is being written finishes and is saved
    // (the backend waits for it before summarising); no further experts speak.
    closingRef.current = true;
    setClosing(true);
    setError(null);
    try {
      setSession(await postJSON(`/live/sessions/${session.id}/close`, {}, { token }));
    } catch (err) {
      closingRef.current = false;
      setError({ message: err.message, retryable: false });
    }
    setClosing(false);
  }

  async function retrySummary() {
    setClosing(true);
    try {
      setSession(await postJSON(`/live/sessions/${session.id}/summary`, {}, { token }));
    } catch (err) {
      setError({ message: err.message, retryable: false });
    }
    setClosing(false);
  }

  if (loadError) {
    return (
      <div className="bg-white rounded-3xl border border-red-200 p-8 text-center" role="alert">
        <p className="text-red-700">{loadError}</p>
        <button onClick={onHide} className="mt-4 border px-5 py-2 rounded-full text-sm">Close</button>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="bg-white rounded-3xl border border-slate-200 p-8 text-center text-gray-500" role="status">
        Opening the live consultation room...
      </div>
    );
  }

  const closed = session.status === "closed";

  if (closed) {
    return (
      <LiveSummary
        session={session}
        experts={experts}
        consultation={consultation}
        generating={closing}
        onRetrySummary={retrySummary}
        onHide={onHide}
      />
    );
  }

  const discussing = session.phase === "expert_discussion";
  const limitReached = session.agenda_complete && session.rounds >= session.max_rounds;
  const canMessage = Boolean(session.can_message) && !running && !closing;
  const statusText = closing
    ? "Ending the discussion"
    : running
      ? speaking
        ? `${experts[speaking.expert_key]?.first_name || "An expert"} is speaking`
        : "The experts are preparing their responses"
      : discussing
        ? error
          ? "The discussion is paused"
          : `The experts are discussing: ${session.current_stage_label}`
        : "Waiting for you";
  // The unlock notice sits where the agenda discussion ended.
  const lastAgendaIndex = session.messages.reduce(
    (last, m, i) => (m.agenda_stage !== null && m.agenda_stage !== undefined ? i : last), -1,
  );
  const noticeAfter = session.agenda_complete
    ? (lastAgendaIndex >= 0 ? lastAgendaIndex : session.messages.findIndex((m) => m.role === "client") - 1)
    : null;
  const unlockNotice = (
    <p className="text-center text-sm font-medium text-indigo-600" role="status">{UNLOCK_NOTICE}</p>
  );

  return (
    <section className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden" aria-label="Live consultation room">

      {/* Header */}
      <div className="px-5 sm:px-8 py-5 border-b border-slate-100 bg-slate-50 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">Live consultation room</p>
          <h3 className="text-xl sm:text-2xl font-bold mt-1">Expert discussion of your project</h3>
          <p className="text-sm text-gray-500 mt-1" aria-live="polite">
            <span className={`inline-block w-2 h-2 rounded-full mr-2 align-middle ${running ? "bg-green-500 animate-pulse" : "bg-slate-400"}`} />
            {statusText}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={onHide}
            className="border border-slate-300 hover:bg-white px-4 py-2 rounded-full text-sm"
          >
            Hide (keeps conversation)
          </button>
          <button
            onClick={endSession}
            disabled={closing}
            className="bg-indigo-900 hover:bg-indigo-950 disabled:opacity-60 text-white px-4 py-2 rounded-full text-sm font-medium"
          >
            {closing ? "Preparing summary..." : "End & Summarize"}
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_260px]">

        {/* Transcript */}
        <div className="min-w-0 flex flex-col">
          <div className="px-5 sm:px-8 pt-4">
            <button
              onClick={() => setShowContext((v) => !v)}
              className="text-xs font-medium text-indigo-600 hover:underline"
              aria-expanded={showContext}
            >
              {showContext ? "Hide project context" : "Show project context"}
            </button>
            {showContext && (
              <p className="mt-2 text-sm text-gray-600 bg-slate-50 rounded-2xl p-4 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {session.problem}
              </p>
            )}
          </div>

          <div className="p-5 sm:p-8 space-y-5 h-[480px] overflow-y-auto" aria-live="polite">
            {session.messages.length === 0 && !speaking && (
              <p className="text-center text-sm text-gray-500 py-10">
                {running ? "The experts are reviewing the panel results..." : "No messages yet."}
              </p>
            )}

            {noticeAfter === -1 && unlockNotice}

            {session.messages.map((m, i) => (
              <div key={m.id} className="space-y-5">
                <Message message={m} expert={experts[m.expert_key]} />
                {i === noticeAfter && unlockNotice}
              </div>
            ))}

            {session.agenda_complete && noticeAfter < -1 && unlockNotice}

            {speaking && (
              <Message
                message={{ role: "expert", content: speaking.text || "…" }}
                expert={experts[speaking.expert_key]}
                streaming
              />
            )}

            {notes.map((n, i) => (
              <p key={i} className={`text-center text-xs ${n.error ? "text-red-600" : "text-gray-400"}`}>
                {experts[n.key]?.first_name || "An expert"} {n.text}
              </p>
            ))}

            {slow && running && (
              <p className="text-center text-xs text-amber-700" role="status">
                This is taking longer than usual. The experts are still responding.
              </p>
            )}

            {error && (
              <div className="text-center text-sm text-red-600" role="alert">
                <p>{error.message}</p>
                {error.retryable && error.body && (
                  <button
                    onClick={() => runRound(error.body)}
                    disabled={running}
                    className="mt-2 border border-red-200 hover:bg-red-50 px-4 py-1.5 rounded-full"
                  >
                    Retry
                  </button>
                )}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Client input */}
          <div className="border-t border-slate-100 p-4 sm:p-5">
            <form onSubmit={sendMessage} className="flex gap-3">
              <label htmlFor="live-input" className="sr-only">Message the experts</label>
              <input
                id="live-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  discussing
                    ? "The experts are discussing the agenda. You can join once they finish..."
                    : running ? "The experts are responding..." : "Ask the experts a question or answer theirs..."
                }
                maxLength={2000}
                disabled={!session.can_message || closing}
                className="flex-1 min-w-0 border border-slate-200 rounded-2xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-50"
              />
              <button
                type="submit"
                disabled={!canMessage || !input.trim()}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-5 rounded-2xl text-sm font-medium"
              >
                Send
              </button>
            </form>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <button
                onClick={() => runRound({})}
                disabled={running || closing || session.agenda_complete || limitReached}
                className="border border-indigo-200 text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 px-4 py-2 rounded-full text-sm"
              >
                Continue discussion{session.current_stage_label ? `: ${session.current_stage_label}` : ""}
              </button>
              <p className="text-xs text-gray-400">
                {discussing
                  ? "The experts work through the agenda first. You can send messages once they finish."
                  : "The experts respond when you send a message."}
              </p>
            </div>

            {limitReached && (
              <p className="mt-2 text-xs text-amber-700">This session has reached its discussion limit. End it to see the summary.</p>
            )}
          </div>
        </div>

        {/* Participants and agenda */}
        <aside className="border-t lg:border-t-0 lg:border-l border-slate-100 p-5 sm:p-6 bg-slate-50/50">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Participants</h4>
          <ul className="mt-3 space-y-3">
            {session.participants.map((p) => (
              <li key={p.key} className="flex items-center gap-3">
                <ExpertAvatar expert={p} speaking={speaking?.expert_key === p.key} />
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{p.first_name}</span>
                  <span className="block text-xs text-gray-500 truncate">{p.role}</span>
                </span>
                {speaking?.expert_key === p.key && <span className="sr-only">speaking</span>}
              </li>
            ))}
            <li className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-sm font-semibold shrink-0">You</span>
              <span className="text-sm font-semibold">Client</span>
            </li>
          </ul>

          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8">Agenda</h4>
          <ol className="mt-3 space-y-2">
            {session.agenda.map((item, i) => (
              <li key={item.key} className="flex items-center gap-2 text-sm">
                <span
                  className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center shrink-0 ${
                    i < session.stage
                      ? "bg-indigo-600 text-white"
                      : i === session.stage
                        ? "border-2 border-indigo-600 text-indigo-600"
                        : "bg-slate-200 text-gray-500"
                  }`}
                  aria-hidden="true"
                >
                  {i < session.stage ? "✓" : i + 1}
                </span>
                <span className={i === session.stage ? "font-semibold" : "text-gray-600"}>
                  {item.label}
                  {i < session.stage && <span className="sr-only"> (done)</span>}
                  {i === session.stage && <span className="sr-only"> (next)</span>}
                </span>
              </li>
            ))}
          </ol>
          <p className="text-xs text-gray-400 mt-4">
            Round {session.rounds} of up to {session.max_rounds}. All participants are AI experts.
          </p>
        </aside>
      </div>
    </section>
  );
}

export default LiveConsultationRoom;
