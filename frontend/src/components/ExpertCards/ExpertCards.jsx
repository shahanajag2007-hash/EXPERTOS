import ExpertCard from "./ExpertCard";
import { experts } from "../../data/experts";
import { useStats } from "../../hooks/useStats";
import { NO_EXPERT_STATS } from "./expertStatsFormat";

function ExpertCards() {
  const { stats } = useStats();

  return (
    <section
      id="experts-section"
      className="max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-24 scroll-mt-20"
    >

      <p className="text-center text-indigo-600 uppercase tracking-widest font-semibold">
        Meet The Experts
      </p>

      <h2 className="text-center text-3xl sm:text-5xl font-bold mt-4">
        Choose Your AI Expert
      </h2>

      <p className="text-center text-gray-500 mt-6 max-w-2xl mx-auto">
        Each AI expert focuses on one specialty and answers from that
        perspective. Ratings and consultation counts come from real use.
      </p>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 mt-12 sm:mt-16">

        {Object.values(experts).map((expert) => (
          <ExpertCard
            key={expert.id}
            id={expert.id}
            icon={expert.icon}
            name={expert.shortRole}
            expertName={expert.name}
            stats={stats ? stats.experts?.[expert.shortRole] ?? NO_EXPERT_STATS : null}
            description={expert.description}
            tags={expert.tags.slice(0, 3)}
            color={expert.color}
          />
        ))}

      </div>

    </section>
  );
}

export default ExpertCards;
