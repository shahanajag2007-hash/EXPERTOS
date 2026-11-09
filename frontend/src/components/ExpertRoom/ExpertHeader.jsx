import { useExpertStats } from "../../hooks/useStats";
import { formatConsultations, formatRating } from "../ExpertCards/expertStatsFormat";

function ExpertHeader({ expert }) {

  const { expertStats } = useExpertStats(expert.shortRole);
  const rating = formatRating(expertStats);


  return (

    <div className="bg-white rounded-[32px] border border-slate-200 shadow-sm overflow-hidden">

      <div className="h-2 bg-gradient-to-r from-indigo-600 via-violet-600 to-blue-600"></div>

      <div className="flex flex-col md:flex-row justify-between md:items-center gap-6 px-6 sm:px-10 py-8">

        <div className="flex flex-col sm:flex-row sm:items-center gap-6 sm:gap-8 min-w-0">

          <div
            className={`w-20 h-20 sm:w-24 sm:h-24 shrink-0 rounded-3xl flex items-center justify-center text-5xl text-white shadow-lg ${expert.color}`}
          >

            {expert.icon}

          </div>

          <div>

            <div className="flex flex-wrap items-center gap-3 sm:gap-4">

              <h1 className="text-3xl sm:text-4xl font-bold">

                {expert.name}

              </h1>

              <span className="bg-indigo-50 text-indigo-700 px-4 py-2 rounded-full font-medium text-sm">

                AI Expert

              </span>

            </div>

            <p className="text-indigo-600 text-lg mt-2">

              {expert.role}

            </p>

            <p className="text-gray-500 mt-5 max-w-3xl leading-8">

              {expert.description}

            </p>

            <div className="flex flex-wrap gap-3 mt-6">

              {expert.tags.map((tag) => (

                <span
                  key={tag}
                  className="bg-indigo-50 text-indigo-600 px-4 py-2 rounded-full text-sm font-medium"
                >

                  {tag}

                </span>

              ))}

            </div>

          </div>

        </div>

        <div className="md:text-right shrink-0">

          <p className="text-3xl sm:text-4xl font-bold text-indigo-600">

            {rating.value}

          </p>

          {rating.detail && <p className="mt-1 text-sm text-gray-500">{rating.detail}</p>}

          <p className="mt-3 text-gray-500">

            {formatConsultations(expertStats)}

          </p>

        </div>

      </div>

    </div>

  );

}

export default ExpertHeader;