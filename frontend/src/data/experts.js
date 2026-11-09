// Display profiles for the six AI experts. `shortRole` is the backend expert
// key (backend/data/experts.json). Ratings and consultation counts are not
// stored here: they come from real data via GET /stats (hooks/useStats.js).
export const experts = {

  ethan: {

    id: "ethan",

    icon: "👨‍💻",

    color: "bg-gradient-to-br from-indigo-600 to-blue-700",

    name: "Ethan Walker",

    role: "Senior Software Architect",

    shortRole: "Software Architect",
    description:
  "Helping engineering teams build scalable, maintainable and future-proof software systems.",

    greeting:
      "Let's build a scalable architecture together.",

    analysisText:
      "Reviewing your software architecture...",

    tags: [
      "Architecture",
      "Microservices",
      "REST APIs",
      "Cloud",
      "Scalability"
    ]

  },

  maya: {

    id: "maya",

    icon: "🎨",

    color: "bg-gradient-to-br from-pink-500 to-purple-600",

    name: "Maya Chen",

    role: "UI / UX Design Advisor",

    shortRole: "Design Advisor",
    description:
      "Creating beautiful, intuitive and accessible user experiences.",

    greeting:
      "Let's create an intuitive user experience.",

    analysisText:
      "Reviewing your user experience...",

    tags: [
      "Figma",
      "UX",
      "Accessibility",
      "Design Systems",
      "UI"
    ]

  },

  alex: {

    id: "alex",

    icon: "🗄️",

    color: "bg-gradient-to-br from-cyan-500 to-blue-600",

    name: "Alex Morgan",

    role: "Database Engineer",

    shortRole: "Database Engineer",
    description:
     "Designing scalable, secure and optimized databases.",

    greeting:
      "Let's optimize your database architecture.",

    analysisText:
      "Analyzing your database design...",

    tags: [
      "PostgreSQL",
      "MySQL",
      "NoSQL",
      "Indexing",
      "Performance"
    ]

  },

  sarah: {

    id: "sarah",

    icon: "🛡️",

    color: "bg-gradient-to-br from-emerald-600 to-green-700",

    name: "Sarah Patel",

    role: "Cyber Security Expert",

    shortRole: "Security Expert",
    description:
      "Helping teams build secure software from day one.",

    greeting:
      "Let's secure your application together.",

    analysisText:
      "Performing a security assessment...",

    tags: [
      "OWASP",
      "Authentication",
      "Encryption",
      "Zero Trust",
      "Compliance"
    ]

  },

  daniel: {

    id: "daniel",

    icon: "☁️",

    color: "bg-gradient-to-br from-sky-500 to-indigo-600",

    name: "Daniel Brooks",

    role: "Cloud Consultant",

    shortRole: "Cloud Consultant",
    description:
      "Cloud architecture, Kubernetes and DevOps automation.",

    greeting:
      "Let's build reliable cloud infrastructure.",

    analysisText:
      "Reviewing your cloud architecture...",

    tags: [
      "AWS",
      "Azure",
      "Docker",
      "Kubernetes",
      "Terraform"
    ]

  },

  ryan: {

    id: "ryan",

    icon: "⚙️",

    color: "bg-gradient-to-br from-orange-500 to-red-600",

    name: "Ryan Cooper",

    role: "DevOps Engineer",

    shortRole: "DevOps Engineer",
    description:
      "Automating deployments and building reliable CI/CD pipelines.",

    greeting:
      "Let's automate your deployment workflow.",

    analysisText:
      "Reviewing your DevOps pipeline...",

    tags: [
      "GitHub Actions",
      "CI/CD",
      "Docker",
      "Monitoring",
      "Linux"
    ]

  }

};

// Display profile for a backend expert key ("Design Advisor" -> Maya's profile).
export function profileFor(key) {
  return Object.values(experts).find((e) => e.shortRole === key) || null;
}
