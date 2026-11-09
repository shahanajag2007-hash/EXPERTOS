import { useEffect, useRef, useState } from "react";
import { FaPaperPlane } from "react-icons/fa";
import ChatMessage from "./ChatMessage";
import { postJSON } from "../../services/api";

// conversationId: the saved Start Consultation conversation (from /analyze).
// initialMessages: its saved messages when it is reopened.
function FollowUpChat({ expert, setExpert, conversationId, initialMessages = [], onHistory }) {
  const [messages, setMessages] = useState(initialMessages);

  const [message, setMessage] = useState("");

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState("");

  const bottomRef = useRef(null);

  useEffect(() => {

    bottomRef.current?.scrollIntoView({
      behavior: "smooth"
    });

  }, [messages]);

  async function sendMessage() {
    if (!message.trim() || loading) return;

    const userMessage = message;

setMessage("");

    setError("");

    setLoading(true);

    try {

     const data = await postJSON("/chat", {
       conversation_id: conversationId,
       message: userMessage
     });

onHistory?.(data.history || []);

if (data.switch) {

    setExpert(data.expert);

    setMessages(data.history);

    setLoading(false);

    return;

}
setMessages(data.history || []);

    } catch (err) {

  // Put the unsent question back so the user can retry it.
  setMessage(userMessage);

  setError(err.message);

}

    setLoading(false);

  }

  return (

    <div className="bg-white rounded-3xl shadow-xl border border-gray-200 mt-10 overflow-hidden">

      <div className="bg-slate-100 px-6 py-4 border-b">

        <h2 className="text-2xl font-bold">

          💬 Live Consultation

        </h2>

        <p className="text-gray-500 mt-2">

          Continue your consultation with {expert?.name}

        </p>

      </div>

      <div className="bg-slate-50 h-[520px] overflow-y-auto p-4 sm:p-6 space-y-6">

        {messages.length === 0 && !loading && (

          <p className="text-center text-gray-500 py-10">

            Ask {expert?.name || "your expert"} a follow-up question. Mention another
            expert by name (for example "Can Sarah review the security?") to bring them in.

          </p>

        )}

        {messages.map((chat, index) => {

    if (chat.type === "system") {

        return (

            <div
                key={index}
                className="text-center text-gray-500 text-sm py-3"
            >
                ───── {chat.message} ─────
            </div>

        );

    }

    return (

        <ChatMessage
            key={index}
            chat={chat}
        />

    );

})}

        {loading && (
                    <div className="flex">

            <div className="bg-white border rounded-3xl rounded-tl-md px-5 py-4 shadow">

              <p className="font-semibold">

                {expert?.emoji} {expert?.name}

              </p>

              <p className="mt-2 text-gray-600">

                Typing...

              </p>

            </div>

          </div>

        )}

        {error && (

          <p className="text-center text-sm text-red-600" role="alert">

            {error}

          </p>

        )}

        <div ref={bottomRef}></div>

      </div>

      <div className="border-t bg-white p-5">

        <div className="flex gap-4">

          <input

            type="text"

            value={message}

            onChange={(e) => setMessage(e.target.value)}

            onKeyDown={(e) => {

              if (e.key === "Enter" && !loading) {

                sendMessage();

              }

            }}

            placeholder={`Ask ${expert?.name} anything about your project...`}

            className="flex-1 min-w-0 border rounded-full px-5 sm:px-6 py-4 outline-none focus:ring-2 focus:ring-indigo-500"

          />

          <button

            disabled={loading || !message.trim()}

            onClick={sendMessage}

            aria-label="Send message"

            className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white rounded-full w-14 h-14 shrink-0 flex items-center justify-center transition"

          >

            <FaPaperPlane />

          </button>

        </div>

      </div>

    </div>

  );

}

export default FollowUpChat;