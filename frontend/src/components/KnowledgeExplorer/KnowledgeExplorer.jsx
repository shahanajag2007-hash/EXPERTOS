import { useState } from "react";
import KnowledgeSearch from "./KnowledgeSearch";
import KnowledgeModal from "./KnowledgeModal";

function KnowledgeExplorer({
  technologies = [],
  expert,
  project
}) {

  const [selectedTech, setSelectedTech] = useState(null);

  const popular = [
    "React",
    "Flask",
    "REST API",
    "JWT",
    "Docker",
    "Redis",
    "OAuth",
    "PostgreSQL",
    "Microservices",
    "CI/CD"
  ];

  function openTechnology(tech) {
    setSelectedTech(tech);
  }

  return (
    <>
      <div className="bg-white rounded-3xl border border-gray-200 p-6 mt-8">

        <h2 className="text-2xl font-bold">
          🧠 AI Knowledge Explorer
        </h2>

        <p className="text-gray-500 mt-2">
          Search any technology or explore recommendations from your consultation.
        </p>

        <KnowledgeSearch
          onSelect={openTechnology}
        />

        <h3 className="font-semibold mt-8">
          ⭐ Recommended For This Project
        </h3>

        <div className="flex flex-wrap gap-3 mt-4">

          {technologies.map((tech) => (

            <button
              key={tech}
              onClick={() => openTechnology(tech)}
              className="px-4 py-2 rounded-full bg-indigo-100 text-indigo-700 hover:bg-indigo-600 hover:text-white transition"
            >
              {tech}
            </button>

          ))}

        </div>

        <h3 className="font-semibold mt-8">
          🔥 Popular Technologies
        </h3>

        <div className="flex flex-wrap gap-3 mt-4">

          {popular.map((tech) => (

            <button
              key={tech}
              onClick={() => openTechnology(tech)}
              className="px-4 py-2 rounded-full bg-gray-100 hover:bg-indigo-600 hover:text-white transition"
            >
              {tech}
            </button>

          ))}

        </div>

      </div>

      {selectedTech && (

        <KnowledgeModal
          technology={selectedTech}
          expert={expert}
          project={project}
          onClose={() => setSelectedTech(null)}
        />

      )}

    </>
  );
}

export default KnowledgeExplorer;