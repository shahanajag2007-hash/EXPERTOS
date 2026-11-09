import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import KnowledgePage from "./KnowledgePage";
import ChapterNavigation from "./ChapterNavigation";
import { postJSON } from "../../services/api";

function KnowledgeModal({
  technology,
  expert,
  project,
  onClose
}) {

  // The technology currently shown; related-technology links change it.
  const [topic, setTopic] = useState(technology);

  const [attempt, setAttempt] = useState(0);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState("");

  const [data, setData] = useState(null);

  const [page, setPage] = useState(0);

  const expertRole = expert?.role || "Software Architect";

  useEffect(() => {

    let cancelled = false;

    async function loadKnowledge() {

      setLoading(true);

      setError("");

      setData(null);

      setPage(0);

      try {

        const result = await postJSON("/knowledge", {

          project,

          technology: topic,

          expert: expertRole

        });

        if (!Array.isArray(result.pages) || result.pages.length === 0) {
          throw new Error("No lesson content was returned for this technology.");
        }

        if (!cancelled) setData(result);

      }

      catch (e) {

        if (!cancelled) setError(e.message);

      }

      finally {

        if (!cancelled) setLoading(false);

      }

    }

    loadKnowledge();

    return () => {
      cancelled = true;
    };

  }, [topic, attempt, project, expertRole]);

  const pageCount = data?.pages?.length || 0;

  useEffect(() => {

    function handleKeys(e) {

      // Escape always closes, even while loading or after an error.
      if (e.key === "Escape") {

        onClose();

        return;

      }

      if (loading) return;

      if (!pageCount) return;

      if (e.key === "ArrowLeft") {

        setPage((old) => Math.max(old - 1, 0));

      }

      if (e.key === "ArrowRight") {

        setPage((old) =>
          Math.min(
            old + 1,
            pageCount - 1
          )
        );

      }

    }

    window.addEventListener(
      "keydown",
      handleKeys
    );

    return () => {

      window.removeEventListener(
        "keydown",
        handleKeys
      );

    };

  }, [loading, pageCount, onClose]);

  function previousPage() {

    setPage((old) =>
      Math.max(old - 1, 0)
    );

  }

  function nextPage() {

    if (!pageCount) return;

    if (page >= pageCount - 1) {

      onClose();

      return;

    }

    setPage((old) => old + 1);

  }

  return (

    <AnimatePresence>

      <motion.div

        className="
          fixed
          inset-0
          z-50
          bg-black/40
          backdrop-blur-sm
          flex
          items-center
          justify-center
          p-5
        "

        initial={{
          opacity: 0
        }}

        animate={{
          opacity: 1
        }}

        exit={{
          opacity: 0
        }}

      >

        <motion.div

          initial={{
            opacity: 0,
            scale: 0.94,
            y: 20
          }}

          animate={{
            opacity: 1,
            scale: 1,
            y: 0
          }}

          exit={{
            opacity: 0,
            scale: 0.94
          }}

          transition={{
            duration: 0.25
          }}

          className="
            bg-white
            rounded-3xl
            shadow-2xl
            w-full
            max-w-6xl
            h-[92vh]
            flex
            flex-col
            overflow-hidden
          "

        >

          <div className="border-b px-8 py-6">

            <div className="flex justify-between items-start">

              <div>

                <p className="text-indigo-600 font-semibold">

                  🧠 AI Knowledge Explorer

                </p>

                <h1 className="text-3xl sm:text-5xl font-bold mt-2 break-words">

                    {data?.title || topic}

                </h1>

                {expert && (

                  <div className="mt-5 bg-indigo-50 border border-indigo-100 rounded-2xl px-5 py-4">

                    <p className="font-semibold text-lg">

                      {expert.emoji} {expert.name}

                    </p>

                    <p className="text-gray-600 mt-1">

                      {expert.role}

                    </p>

                    <p className="text-sm text-gray-500 mt-3">

                      I'll walk you through this technology and explain
                      exactly why I recommended it for your project.

                    </p>

                  </div>

                )}

              </div>

              <button

                onClick={onClose}

                aria-label="Close"

                className="
                  text-4xl
                  text-gray-400
                  hover:text-red-500
                  transition
                "

              >

                ×

              </button>

            </div>

          </div>

          <div className="flex-1 overflow-hidden">

            {loading ? (

              <div className="h-full flex items-center justify-center">

                <div className="text-center">

                  <div className="text-6xl">

                    {expert?.emoji || "👨‍💻"}

                  </div>

                  <h2 className="text-3xl font-bold mt-6">

                    {expert?.name || "Your Expert"} is preparing today's lesson...

                  </h2>

                  <p className="text-gray-500 mt-4">

                    Generating a personalized explanation...

                  </p>

                </div>

              </div>

            ) : error || !data ? (

              <div className="h-full flex items-center justify-center p-6">

                <div className="text-center max-w-md">

                  <div className="text-5xl">⚠️</div>

                  <h2 className="text-2xl font-bold mt-6">

                    Couldn't load this lesson

                  </h2>

                  <p className="text-gray-500 mt-3 leading-7">

                    {error || "Please try again."}

                  </p>

                  <div className="mt-8 flex flex-wrap justify-center gap-4">

                    <button
                      onClick={() => setAttempt((n) => n + 1)}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-xl transition"
                    >
                      Try Again
                    </button>

                    <button
                      onClick={onClose}
                      className="border px-6 py-3 rounded-xl hover:bg-gray-50 transition"
                    >
                      Close
                    </button>

                  </div>

                </div>

              </div>

            ) : (

              <>
                              <AnimatePresence mode="wait">

                  <motion.div

                    key={page}

                    initial={{
                      opacity: 0,
                      x: 120,
                      rotateY: 18
                    }}

                    animate={{
                      opacity: 1,
                      x: 0,
                      rotateY: 0
                    }}

                    exit={{
                      opacity: 0,
                      x: -120,
                      rotateY: -18
                    }}

                    transition={{
                      duration: 0.35
                    }}

                    className="h-full"

                  >

                    <KnowledgePage

                        page={data.pages[page]}

                        onTechnologyClick={setTopic}

                        onAskExpert={() => {

                            onClose();

                        }}

                    />

                  </motion.div>

                </AnimatePresence>

              </>

            )}

          </div>

          {!loading && pageCount > 0 && (

            <ChapterNavigation

              page={page}

              total={pageCount}

              previous={previousPage}

              next={nextPage}

              isLastPage={
                page === pageCount - 1
              }

              onClose={onClose}

            />

          )}

        </motion.div>

      </motion.div>

    </AnimatePresence>

  );

}

export default KnowledgeModal;