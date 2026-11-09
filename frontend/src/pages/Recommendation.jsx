import { useLocation, Link } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";

function Recommendation() {
  const { state } = useLocation();

  const answers = state || {};

  let expert = {
    id: "ethan",
    name: "Software Architect",
    icon: "💻",
    reason:
      "Based on your answers, planning and architecture should be your first priority.",
  };

  if (answers[1] === "Database") {
    expert = {
      id: "alex",
      name: "Database Engineer",
      icon: "🗄️",
      reason:
        "Your responses indicate that database design and optimization are the main focus.",
    };
  }

  if (answers[1] === "Security") {
    expert = {
      id: "sarah",
      name: "Security Expert",
      icon: "🛡️",
      reason:
        "Security appears to be the biggest challenge in your project.",
    };
  }

  if (answers[1] === "UI/UX") {
    expert = {
      id: "maya",
      name: "AI Design Advisor",
      icon: "✨",
      reason:
        "Improving the user experience and interface is your current priority.",
    };
  }

  return (
    <>
    <Navbar />

    <div className="min-h-[calc(100vh-73px)] bg-slate-50 flex items-center justify-center px-4 sm:px-6 py-12">

      <div className="bg-white rounded-3xl shadow-xl p-8 sm:p-12 max-w-2xl w-full text-center">

        <div className="text-7xl">
          {expert.icon}
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold mt-6">
          {expert.name}
        </h1>

        <p className="text-gray-500 mt-6 text-lg leading-8">
          {expert.reason}
        </p>

        <div className="mt-10 flex flex-col sm:flex-row justify-center gap-4 sm:gap-6">

          <Link
            to="/guide"
            className="border px-8 py-4 rounded-full hover:bg-gray-50 transition"
          >
            Start Again
          </Link>

          <Link
  to={`/expert/${expert.id}`}
  className="bg-indigo-600 hover:bg-indigo-700 transition text-white px-8 py-4 rounded-full"
>
  Consult Expert →
</Link>

        </div>

      </div>

    </div>
    </>
  );
}

export default Recommendation;
