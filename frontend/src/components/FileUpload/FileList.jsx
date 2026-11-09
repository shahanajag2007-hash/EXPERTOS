import { useRef } from "react";
import { formatSize } from "../../services/files";

/**
 * File picker button plus the list of chosen files, designed to sit inside
 * the existing upload areas without changing them. `uploads` comes from
 * useFileUploads().
 */
export function ChooseFilesButton({ uploads, accept, label = "Choose files", multiple = true, className = "" }) {
  const input = useRef(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        className="sr-only"
        accept={accept}
        multiple={multiple}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          uploads.add(e.target.files);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        className={className || "mt-4 border border-slate-300 hover:bg-slate-50 px-5 py-2 rounded-full text-sm font-medium transition"}
      >
        {label}
      </button>
    </>
  );
}

function statusText(item) {
  if (item.status === "uploading") return `Uploading… ${Math.round((item.progress || 0) * 100)}%`;
  if (item.status === "error") return item.error;
  const file = item.file;
  if (file.kind === "image") return "Image ready";
  if (!file.characters) return file.note ? `No text found: ${file.note}` : "No text found";
  return `${file.characters.toLocaleString()} characters read${file.note ? ` (${file.note})` : ""}`;
}

export function FileList({ uploads, className = "mt-4" }) {
  if (!uploads.items.length) return null;
  return (
    <ul className={`${className} space-y-2 text-left`} aria-label="Attached files">
      {uploads.items.map((item) => (
        <li
          key={item.key}
          className={`flex items-center gap-3 rounded-xl border px-4 py-2 text-sm ${
            item.status === "error" ? "border-red-200 bg-red-50" : "border-slate-200 bg-white"
          }`}
        >
          <span aria-hidden="true">{item.file?.kind === "image" ? "🖼" : "📄"}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-gray-800" title={item.name}>
              {item.name} <span className="font-normal text-gray-400">· {formatSize(item.size || 0)}</span>
            </span>
            <span
              className={`block text-xs ${item.status === "error" ? "text-red-700" : "text-gray-500"}`}
              role={item.status === "error" ? "alert" : undefined}
            >
              {statusText(item)}
            </span>
            {item.status === "uploading" && (
              <span className="mt-1 block h-1 rounded-full bg-slate-200 overflow-hidden" aria-hidden="true">
                <span className="block h-full bg-indigo-600 transition-all" style={{ width: `${Math.round((item.progress || 0) * 100)}%` }} />
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={() => uploads.remove(item.key)}
            className="shrink-0 text-gray-400 hover:text-red-600 px-2"
            aria-label={`Remove ${item.name}`}
            title="Remove"
          >
            ✕
          </button>
        </li>
      ))}
    </ul>
  );
}
