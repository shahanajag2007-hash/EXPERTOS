import { useState, useRef, useEffect } from "react";
import { streamSSE } from "../../services/api";
import { profileFor } from "../../data/experts";

// Suggested questions per expert role
const SUGGESTIONS = {
  "Software Architect": [
    "Explain your recommendation",
    "Suggest a better architecture",
    "What are the main risks?",
    "Recommend next steps",
  ],
  "Database Engineer": [
    "Normalize my schema",
    "Index suggestions",
    "Should I use PostgreSQL?",
    "Database scaling strategy",
  ],
  "Security Expert": [
    "Security audit checklist",
    "OWASP top risks",
    "JWT security best practices",
    "Authentication recommendations",
  ],
  "Cloud Consultant": [
    "AWS vs Azure for my project",
    "Estimate cloud costs",
    "Scaling strategy",
    "Deployment plan",
  ],
  "DevOps Engineer": [
    "Set up CI/CD pipeline",
    "Dockerize my project",
    "GitHub Actions setup",
    "Deployment automation",
  ],
  "Design Advisor": [
    "Improve UX flow",
    "Accessibility checklist",
    "Color palette suggestions",
    "Navigation improvements",
  ],
};

const PLACEHOLDERS = {
  "Software Architect": "Ask Ethan about architecture...",
  "Database Engineer":  "Ask Alex about databases...",
  "Security Expert":    "Ask Sarah about security...",
  "Cloud Consultant":   "Ask Daniel about cloud deployment...",
  "DevOps Engineer":    "Ask Ryan about CI/CD...",
  "Design Advisor":     "Ask Maya about UI/UX...",
};

// ─── Message bubble ────────────────────────────────────────────────────────────
function MessageBubble({ msg, expert }) {
  if (msg.sender === "system") {
    return <p className="text-center text-xs text-gray-400">{msg.text}</p>;
  }
  // Each reply shows the expert who wrote it (the active expert can change).
  if (msg.expertKey) expert = profileFor(msg.expertKey) || expert;
  if (msg.sender === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-indigo-600 text-white rounded-3xl rounded-tr-md px-6 py-4 max-w-xl text-sm leading-relaxed">
          {msg.text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <div className="w-9 h-9 rounded-xl bg-slate-200 flex items-center justify-center text-lg flex-shrink-0">
        {expert?.icon || "👤"}
      </div>
      <div className="bg-slate-100 rounded-3xl rounded-tl-md px-6 py-4 max-w-xl text-sm leading-relaxed text-gray-800 whitespace-pre-wrap">
        {msg.text}
        {msg.streaming && <span className="inline-block w-2 h-4 ml-0.5 align-middle bg-indigo-400 animate-pulse" aria-hidden="true" />}
      </div>
    </div>
  );
}

// ─── Thinking indicator ───────────────────────────────────────────────────────
function ThinkingIndicator({ expert, slow }) {
  return (
    <div className="flex gap-3" role="status">
      <div className="w-9 h-9 rounded-xl bg-slate-200 flex items-center justify-center text-lg flex-shrink-0">
        {expert?.icon || "👤"}
      </div>
      <div className="bg-slate-100 rounded-3xl rounded-tl-md px-6 py-4 text-sm text-gray-500">
        <span className="animate-pulse">{expert?.name?.split(" ")[0] || "Expert"} is thinking...</span>
        {slow && (
          <span className="block mt-1 text-xs text-amber-700">
            This is taking longer than usual. Still waiting for a reply.
          </span>
        )}
      </div>
    </div>
  );
}

function toHistory(messages, expert) {
  // History in the format the backend expects.
  return messages.filter((m) => m.sender !== "system").map((m) => ({
    type:    "chat",
    sender:  m.sender,
    message: m.text,
    ...(m.sender === "expert" ? { expert: { name: expert?.name, role: expert?.shortRole } } : {}),
  }));
}

// ─── ExpertChat ───────────────────────────────────────────────────────────────
/**
 * Props:
 *   expert       – expert object from experts.js (id, name, shortRole, icon, …)
 *   project      – string: the project description used in the recommendation
 *   analysis     – object: the recommendation data returned by /expert/recommend
 *   conversationId  – saved conversation: the server keeps the history and
 *                     saves each exchange (the client's copy isn't sent)
 *   initialMessages – saved messages to show when reopening a conversation
 *
 *   activeExpert    – the chatbot's active role: the expert currently
 *                     answering (may differ from `expert`, the room's own
 *                     expert, after the user asks for someone else). It only
 *                     affects who answers; the chat's title, greeting,
 *                     placeholder and suggestions stay the room expert's.
 *   onSwitch        – called with the backend expert key when the backend
 *                     switches the active role
 *
 * Replies stream from /expert/chat/stream so text appears as it's generated.
 */
function ExpertChat({ expert, activeExpert = null, project = "", analysis = {}, conversationId = null,
                      initialMessages = [], onExchange, onSwitch }) {
  const responder = activeExpert || expert;
  const [messages, setMessages] = useState(() => [
    {
      sender: "expert",
      text:   expert?.greeting || `Hi! I'm ${expert?.name}. What else would you like to discuss?`,
    },
    ...initialMessages.map((m) => (m.type === "system"
      ? { sender: "system", text: m.message }
      : { sender: m.sender, text: m.message, expertKey: m.expert_key, expertName: m.expert?.name })),
  ]);
  const [input,   setInput]   = useState("");
  const [status,  setStatus]  = useState("idle");   // idle | thinking | streaming
  const [slow,    setSlow]    = useState(false);
  const [error,   setError]   = useState(null);     // { message, retryable, question }

  // Guards against double submission before React re-renders.
  const inFlight = useRef(false);
  const abortRef = useRef(null);
  const bottomRef = useRef(null);

  const busy = status !== "idle";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, status]);

  // Stop any in-progress stream when leaving the room.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function ask(question, { retry = false } = {}) {
    if (!question || inFlight.current) return;
    inFlight.current = true;

    setError(null);
    setSlow(false);
    setStatus("thinking");

    // On retry the question is already in the transcript.
    const base = retry ? messages : [...messages, { sender: "user", text: question }];
    if (!retry) setMessages(base);

    const controller = new AbortController();
    abortRef.current = controller;
    let reply = "";
    // Who is answering: the backend may switch experts for this message.
    let speaker = { expertKey: responder?.shortRole, expertName: responder?.name };
    const previousRole = responder?.shortRole;
    let shown = base;

    try {
      const expertKey = expert?.shortRole || expert?.role || "Software Architect";
      await streamSSE("/expert/chat/stream", conversationId
        ? { expert: expertKey, conversation_id: conversationId, message: question }
        : {
            expert:   expertKey,
            project,
            analysis,
            history:  toHistory(base, expert),
            message:  question,
          }, {
        signal: controller.signal,
        onSlow: () => setSlow(true),
        onEvent: (event, data) => {
          if (event === "switch") {
            speaker = { expertKey: data.expert_key, expertName: data.expert?.name };
            shown = [...base, { sender: "system", text: data.notice }];
            setMessages(shown);
            onSwitch?.(data.expert_key);
          } else if (event === "token") {
            reply += data.text;
            setStatus("streaming");
            setMessages([...shown, { sender: "expert", text: reply, streaming: true, ...speaker }]);
          } else if (event === "done") {
            const final = [...shown, { sender: "expert", text: data.reply || reply, ...speaker }];
            setMessages(final);
            if (data.saved === false && data.save_error) {
              setError({ message: data.save_error, retryable: false, question });
            }
            onExchange?.(final);
          }
        },
      });
    } catch (err) {
      if (err?.name !== "AbortError") {
        // Keep any partial reply visible, clearly marked as incomplete. A
        // failed reply also cancels a switch (the backend keeps the previous
        // expert), so the notice is removed.
        setMessages(reply
          ? [...shown, { sender: "expert", text: `${reply.trim()}\n\n[Reply interrupted]`, ...speaker }]
          : base);
        if (!reply && shown !== base) onSwitch?.(previousRole);
        setError({ message: err.message, retryable: err.retryable !== false, question });
      }
    } finally {
      inFlight.current = false;
      abortRef.current = null;
      setStatus("idle");
      setSlow(false);
    }
  }

  function sendMessage(text) {
    const question = (text || input).trim();
    if (!question || busy) return;
    setInput("");
    ask(question);
  }

  const suggestions = SUGGESTIONS[expert?.shortRole] || [];
  const placeholder = PLACEHOLDERS[expert?.shortRole] || "Ask your expert anything...";

  return (
    <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm overflow-hidden">

      {/* Header */}
      <div className="px-6 sm:px-8 py-6 border-b border-slate-100">
        <h2 className="text-2xl sm:text-3xl font-bold">💬 Continue Discussion</h2>
        <p className="text-gray-500 mt-2 text-sm">
          Ask follow-up questions and continue working with {expert?.name}, an AI expert.
        </p>
      </div>

      {/* Messages */}
      <div className="p-4 sm:p-8 space-y-5 h-[450px] overflow-y-auto" aria-live="polite">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} expert={expert} />
        ))}
        {status === "thinking" && <ThinkingIndicator expert={responder} slow={slow} />}
        {status === "streaming" && slow && (
          <p className="text-xs text-amber-700 text-center">Still writing. This reply is taking longer than usual.</p>
        )}
        {error && (
          <div className="text-center text-sm text-red-600" role="alert">
            <p>{error.message}</p>
            {error.retryable && (
              <button
                onClick={() => ask(error.question, { retry: true })}
                className="mt-2 border border-red-200 hover:bg-red-50 px-4 py-1.5 rounded-full text-sm"
              >
                Retry
              </button>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions */}
      {suggestions.length > 0 && (
        <div className="border-t border-slate-100 px-6 py-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Suggested Questions
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((q) => (
              <button
                key={q}
                disabled={busy}
                onClick={() => sendMessage(q)}
                className="bg-slate-100 hover:bg-slate-200 disabled:opacity-50 px-4 py-2 rounded-full text-sm transition"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form
        className="border-t border-slate-100 p-4 sm:p-5 flex gap-3 sm:gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage();
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          aria-label={`Message ${expert?.name || "the expert"}`}
          maxLength={4000}
          className="flex-1 min-w-0 border border-slate-200 rounded-2xl px-5 py-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-6 rounded-2xl font-medium text-sm transition"
        >
          {busy ? "..." : "Send →"}
        </button>
      </form>

    </div>
  );
}

export default ExpertChat;
