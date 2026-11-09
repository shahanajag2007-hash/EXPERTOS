function ChapterNavigation({

  page,

  total,

  previous,

  next,

  isLastPage,

  onClose

}) {

  return (

    <div
      className="
        border-t
        bg-white
        px-8
        py-5
        flex
        items-center
        justify-between
        gap-6
        shrink-0
      "
    >

      <button

        onClick={previous}

        disabled={page === 0}

        className="
          px-6
          py-3
          rounded-xl
          bg-gray-100
          hover:bg-gray-200
          disabled:opacity-40
          transition
        "

      >

        ◀ Previous

      </button>

      <div className="flex flex-col items-center">

        <p className="text-sm text-gray-500">

          Page {page + 1} of {total}

        </p>

        <div className="flex gap-2 mt-2">

          {Array.from({

            length: total

          }).map((_, index) => (

            <div

              key={index}

              className={`
                w-3
                h-3
                rounded-full
                transition-all
                duration-300
                ${
                  page === index
                    ? "bg-indigo-600 scale-125"
                    : "bg-gray-300"
                }
              `}

            />

          ))}

        </div>

      </div>

      {isLastPage ? (

        <button

          onClick={onClose}

          className="
            px-6
            py-3
            rounded-xl
            bg-green-600
            hover:bg-green-700
            text-white
            transition
          "

        >

          ✓ Finish Reading

        </button>

      ) : (

        <button

          onClick={next}

          className="
            px-6
            py-3
            rounded-xl
            bg-indigo-600
            hover:bg-indigo-700
            text-white
            transition
          "

        >

          Next ▶

        </button>

      )}

    </div>

  );

}

export default ChapterNavigation;