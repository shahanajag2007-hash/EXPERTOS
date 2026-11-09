function KnowledgePage({

  page,

  onTechnologyClick,

  onAskExpert

}) {

  if (!page) return null;

  return (

    <div className="h-full overflow-y-auto px-10 py-8">

      <div className="max-w-4xl mx-auto">

        <h1 className="text-4xl font-bold">

          {page.title}

        </h1>

        <div className="mt-8 rounded-2xl border border-indigo-100 bg-indigo-50 p-6">

          <p className="font-semibold text-indigo-600">

            💡 Expert's Advice

          </p>

          <p className="mt-3 text-gray-700 leading-8">

            Don't memorize technologies.

            Understand why they exist.

            Every technology solves a problem.

          </p>

        </div>

        <div className="mt-10">

          <p className="text-lg leading-9 whitespace-pre-wrap text-gray-700">

            {page.content}

          </p>

        </div>

        {page.related && page.related.length > 0 && (

          <>

            <h2 className="mt-12 text-2xl font-bold">

              🔗 Continue Learning

            </h2>

            <p className="text-gray-500 mt-2">

              Click any technology to instantly open its lesson.

            </p>

            <div className="flex flex-wrap gap-3 mt-6">

              {page.related.map((item) => (

                <button

                  key={item}

                  onClick={() => onTechnologyClick(item)}

                  className="
                    px-5
                    py-3
                    rounded-full
                    bg-indigo-100
                    text-indigo-700
                    hover:bg-indigo-600
                    hover:text-white
                    transition
                  "

                >

                  {item}

                </button>

              ))}

            </div>

          </>

        )}

        <div className="mt-16 rounded-2xl border bg-slate-50 p-8">

          <h2 className="text-2xl font-bold">

            💬 Still have questions?

          </h2>

          <p className="text-gray-600 mt-3">

            Continue the discussion with your expert.

          </p>

          <button

            onClick={onAskExpert}

            className="
              mt-6
              bg-indigo-600
              hover:bg-indigo-700
              text-white
              px-6
              py-3
              rounded-xl
              transition
            "

          >

            Ask Expert About This →

          </button>

        </div>

      </div>

    </div>

  );

}

export default KnowledgePage;