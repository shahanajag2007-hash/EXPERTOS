import { Link } from "react-router-dom";
import { useState } from "react";
import { deleteConversation, formatWhen } from "../../services/history";
import { useSession } from "../../services/auth";

/**
 * "Your conversations" list: reopen, start new, or delete a saved conversation.
 * `list` comes from useConversationList().
 */
function ConversationHistory({ list, activeId, onOpen, onNew, onDeleted, title = "Your conversations" }) {
  const user = useSession();
  const [confirming, setConfirming] = useState(null);
  const [error, setError] = useState("");

  async function remove(id) {
    setError("");
    try {
      await deleteConversation(id);
      setConfirming(null);
      onDeleted?.(id);
      list.refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-bold text-lg">{title}</h3>
        {onNew && (
          <button onClick={onNew} className="text-sm font-medium text-indigo-600 hover:underline">
            + New
          </button>
        )}
      </div>

      {list.error && <p className="text-sm text-red-600 mt-3" role="alert">{list.error}</p>}
      {error && <p className="text-sm text-red-600 mt-3" role="alert">{error}</p>}

      {!list.error && list.conversations.length === 0 && (
        <p className="text-sm text-gray-500 mt-3">
          Conversations you have here are saved automatically, so you can come back to them.
        </p>
      )}

      {list.conversations.length > 0 && (
        <ul className="mt-4 space-y-2" aria-label={title}>
          {list.conversations.map((c) => (
            <li
              key={c.id}
              className={`rounded-2xl border px-4 py-3 ${
                c.id === activeId ? "border-indigo-200 bg-indigo-50" : "border-slate-200 hover:bg-slate-50"
              }`}
            >
              {confirming === c.id ? (
                <div className="text-sm">
                  <p className="text-gray-700">Delete this conversation and its files?</p>
                  <div className="mt-2 flex gap-3">
                    <button onClick={() => remove(c.id)} className="text-red-600 font-medium hover:underline">
                      Delete
                    </button>
                    <button onClick={() => setConfirming(null)} className="text-gray-600 hover:underline">
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <button
                    onClick={() => onOpen(c.id)}
                    className="min-w-0 flex-1 text-left"
                    aria-current={c.id === activeId ? "true" : undefined}
                  >
                    <span className="block truncate font-medium text-gray-800">{c.title}</span>
                    <span className="block text-xs text-gray-500 mt-0.5">
                      {formatWhen(c.updated_at)} · {c.message_count || 0} message{c.message_count === 1 ? "" : "s"}
                    </span>
                  </button>
                  <button
                    onClick={() => setConfirming(c.id)}
                    className="shrink-0 text-gray-400 hover:text-red-600 px-1"
                    aria-label={`Delete ${c.title}`}
                    title="Delete"
                  >
                    ✕
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {!user && (
        <p className="text-xs text-gray-400 mt-4">
          Saved in this browser. <Link to="/signin" className="text-indigo-600 hover:underline">Sign in</Link> to
          keep them with your account.
        </p>
      )}
    </div>
  );
}

export default ConversationHistory;
