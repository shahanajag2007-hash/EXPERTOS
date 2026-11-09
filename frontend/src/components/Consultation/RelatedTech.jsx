import KnowledgeExplorer from "../KnowledgeExplorer/KnowledgeExplorer";

function RelatedTech({

  analysis,

  expert,

  project

}) {

  let technologies = [

    "React",

    "Flask",

    "PostgreSQL",

    "Docker",

    "JWT",

    "REST API"

  ];

  if (analysis) {

    const text = JSON.stringify(analysis);

    const available = [

      "React",

      "Flask",

      "PostgreSQL",

      "Docker",

      "JWT",

      "REST API",

      "Redis",

      "OAuth",

      "GraphQL",

      "Microservices",

      "CI/CD",

      "Tailwind CSS"

    ];

    technologies = available.filter((item) =>
      text.toLowerCase().includes(
        item.toLowerCase()
      )
    );

    if (technologies.length === 0) {

      technologies = available.slice(0, 6);

    }

  }

  return (

    <KnowledgeExplorer

      technologies={technologies}

      expert={expert}

      project={project}

    />

  );

}

export default RelatedTech;