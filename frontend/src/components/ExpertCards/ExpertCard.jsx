import { useNavigate } from "react-router-dom";
import { formatConsultations, formatRating } from "./expertStatsFormat";

function ExpertCard({
  id,
  icon,
  name,
  expertName,
  description,
  tags = [],
  stats,
  color,
}) {

  const navigate = useNavigate();
  const rating = formatRating(stats);

  return (
    <div className="bg-white rounded-3xl border border-gray-200 p-6 sm:p-8 shadow-sm hover:shadow-xl hover:-translate-y-2 transition duration-300 flex flex-col">

      <div className="flex justify-between items-center">

        <div
          className={`${color} w-14 h-14 rounded-2xl flex items-center justify-center text-white text-2xl`}
        >
          {icon}
        </div>

        <span className="text-right">
          <span className="block font-semibold text-gray-700">{rating.value}</span>
          {rating.detail && <span className="block text-xs text-gray-400">{rating.detail}</span>}
        </span>

      </div>

      <h3 className="text-2xl font-bold mt-6">
        {name}
      </h3>

      {expertName && (
        <p className="text-indigo-600 text-sm font-medium mt-1">
          {expertName}
        </p>
      )}

      <p className="text-gray-500 mt-3">
        {description}
      </p>

      <div className="flex flex-wrap gap-2 mt-6">

        {tags.map((tag) => (
          <span
            key={tag}
            className="bg-indigo-50 text-indigo-600 px-3 py-1 rounded-full text-sm"
          >
            {tag}
          </span>
        ))}

      </div>

      <div className="flex justify-between items-center gap-4 mt-auto pt-8">

        <span className="text-gray-500 text-sm">
          {formatConsultations(stats)}
        </span>

        <button

          onClick={() => navigate(`/expert/${id}`)}

          className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-full transition shrink-0"

          aria-label={`Consult ${expertName || name}`}

        >

          Consult →

        </button>

      </div>

    </div>
  );
}

export default ExpertCard;
