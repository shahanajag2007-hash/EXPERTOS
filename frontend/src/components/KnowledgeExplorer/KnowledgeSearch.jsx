import { useState } from "react";

const technologies = [

  "React",
  "React Router",
  "React Query",
  "Redux",

  "Flask",
  "FastAPI",
  "Django",

  "Docker",
  "Kubernetes",

  "JWT",
  "OAuth",

  "REST API",
  "GraphQL",

  "Redis",
  "RabbitMQ",

  "PostgreSQL",
  "MongoDB",
  "SQLite",

  "Tailwind CSS",

  "CI/CD",

  "Git",

  "Microservices"

];

function KnowledgeSearch({ onSelect }) {

  const [query, setQuery] = useState("");

  const filtered = technologies.filter((item) =>
    item.toLowerCase().includes(
      query.toLowerCase()
    )
  );

  return (

    <div className="mt-6 relative">

      <input

        value={query}

        onChange={(e) =>
          setQuery(e.target.value)
        }

        placeholder="Search technologies..."

        className="w-full border rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-indigo-500"

      />

      {query && (

        <div className="absolute z-20 mt-2 w-full bg-white border rounded-xl shadow-lg max-h-64 overflow-auto">

          {filtered.length === 0 && (

            <div className="p-4 text-gray-500">

              No technologies found.

            </div>

          )}

          {filtered.map((item) => (

            <button

              key={item}

              onClick={() => {

                onSelect(item);

                setQuery("");

              }}

              className="w-full text-left px-4 py-3 hover:bg-indigo-50 transition"

            >

              {item}

            </button>

          ))}

        </div>

      )}

    </div>

  );

}

export default KnowledgeSearch;