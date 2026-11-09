import { useCallback, useEffect, useRef, useState } from "react";
import { deleteJSON, postForm } from "./api";

// Mirrors backend/services/files.py; the backend makes the final decision.
export const MAX_FILE_MB = 10;
export const MAX_FILES = 5;
export const DOCUMENT_ACCEPT =
  ".pdf,.docx,.xlsx,.pptx,.zip,.txt,.md,.csv,.tsv,.json,.yaml,.yml,.xml,.html,.sql,.log," +
  ".py,.js,.jsx,.ts,.tsx,.java,.c,.cpp,.cs,.go,.rs,.rb,.php,.css,.sh,.toml,.ini," +
  ".png,.jpg,.jpeg,.webp,.gif";
export const IMAGE_ACCEPT = ".png,.jpg,.jpeg,.webp,.gif";

const OLD_OFFICE = /\.(doc|xls|ppt)$/i;

export function uploadFile(file, { conversationId, onProgress, signal } = {}) {
  const form = new FormData();
  form.append("files", file);
  if (conversationId) form.append("conversation_id", conversationId);
  return postForm("/files", form, { onProgress, signal }).then((data) => data.files[0]);
}

export function deleteFile(id) {
  return deleteJSON(`/files/${encodeURIComponent(id)}`);
}

export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function checkLocally(file, accept) {
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > MAX_FILE_MB * 1024 * 1024) return `${file.name} is larger than ${MAX_FILE_MB} MB.`;
  if (OLD_OFFICE.test(file.name)) return `${file.name} uses an old Office format. Save it as a newer format (.docx, .xlsx, .pptx) or PDF.`;
  const ext = `.${file.name.split(".").pop().toLowerCase()}`;
  if (accept && !accept.split(",").includes(ext)) return `${file.name}: this file type isn't supported here.`;
  return null;
}

let nextLocalId = 1;

/**
 * Upload state for one upload area.
 * items: [{ key, name, size, status: "uploading"|"done"|"error", progress, file?, error? }]
 * `file` is the backend's description once uploaded ({ id, kind, characters, note, ... }).
 * `initial` are already-uploaded files to show (e.g. carried over from Design Advisor).
 */
export function useFileUploads({ conversationId, accept = DOCUMENT_ACCEPT, max = MAX_FILES, initial = [] } = {}) {
  const [items, setItems] = useState(() =>
    initial.map((file) => ({ key: `f${nextLocalId++}`, name: file.filename, size: file.size_bytes,
                             status: "done", progress: 1, file })),
  );
  const controllers = useRef(new Map());

  useEffect(() => {
    const active = controllers.current;
    return () => active.forEach((c) => c.abort());
  }, []);

  const patch = (key, changes) =>
    setItems((list) => list.map((item) => (item.key === key ? { ...item, ...changes } : item)));

  // The current list, for decisions made outside state updaters (updaters
  // must stay free of side effects such as starting uploads).
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  const add = useCallback((fileList) => {
    const incoming = Array.from(fileList || []);
    const active = itemsRef.current.filter((i) => i.status !== "error").length;
    const room = Math.max(0, max - active);

    const added = incoming.slice(0, room).map((f) => {
      const problem = checkLocally(f, accept);
      return { key: `f${nextLocalId++}`, name: f.name, size: f.size, progress: 0, source: f,
               status: problem ? "error" : "uploading", error: problem };
    });
    const extra = incoming.slice(room).map((f) => ({
      key: `f${nextLocalId++}`, name: f.name, size: f.size, status: "error", progress: 0,
      error: `You can attach up to ${max} files.`,
    }));

    itemsRef.current = [...itemsRef.current, ...added, ...extra];
    const withoutSource = (item) => {
      const copy = { ...item };
      delete copy.source;
      return copy;
    };
    setItems((list) => [...list, ...added.map(withoutSource), ...extra]);

    added.filter((item) => item.status === "uploading").forEach((item) => {
      const controller = new AbortController();
      controllers.current.set(item.key, controller);
      uploadFile(item.source, { conversationId, signal: controller.signal,
                                onProgress: (p) => patch(item.key, { progress: p }) })
        .then((file) => patch(item.key, { status: "done", progress: 1, file }))
        .catch((err) => {
          if (err?.name !== "AbortError") patch(item.key, { status: "error", error: err.message });
        })
        .finally(() => controllers.current.delete(item.key));
    });
  }, [accept, conversationId, max]);

  const remove = useCallback((key) => {
    const item = itemsRef.current.find((i) => i.key === key);
    controllers.current.get(key)?.abort();
    // Removing a file deletes it, so the experts stop reading it in this conversation too.
    if (item?.file?.id) deleteFile(item.file.id).catch(() => {});
    itemsRef.current = itemsRef.current.filter((i) => i.key !== key);
    setItems((list) => list.filter((i) => i.key !== key));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const ids = items.filter((i) => i.status === "done").map((i) => i.file.id);
  const uploading = items.some((i) => i.status === "uploading");
  const done = items.filter((i) => i.status === "done").map((i) => i.file);

  return { items, add, remove, clear, ids, uploading, done };
}
