import { useNavigate } from "react-router-dom";
function ExpertPanel() {
  const navigate = useNavigate();
  const experts = [
    { icon: "💻", title: "Software Architect" },
    { icon: "🗄️", title: "Database Engineer" },
    { icon: "🛡️", title: "Security Expert" },
    { icon: "☁️", title: "Cloud Consultant" },
  ];

  return (
    <section
      id="panel-section"
      className="max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-24"
    >
      <div className="bg-white rounded-[36px] border border-gray-200 shadow-sm p-6 sm:p-12">

        <div className="grid md:grid-cols-2 gap-12 items-center">

          {/* Left Side */}
          <div>

            <span className="inline-flex items-center bg-indigo-100 text-indigo-600 px-4 py-2 rounded-full text-sm font-semibold">
              👥 AI Expert Panel
            </span>

            <h2 className="text-3xl sm:text-5xl font-bold mt-6 leading-tight">
              🤝 Multiple Experts,
              <br />
              One Conclusion
            </h2>

            <p className="text-gray-500 text-lg mt-6 leading-8">
              For complex projects, let multiple AI experts collaborate
              before providing one complete recommendation.
              Every angle covered, zero blind spots.
            </p>

            <button

              onClick={() => navigate("/panel")}

              className="mt-10 bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-full font-semibold transition"

            >

              Consult Expert Panel →

            </button>

          </div>

          {/* Right Side */}

          <div className="grid grid-cols-2 gap-4 sm:gap-6">

            {experts.map((expert) => (

              <div
                key={expert.title}
                className="bg-white rounded-3xl border border-gray-200 p-6 shadow-sm hover:shadow-lg transition"
              >

                <div className="w-14 h-14 rounded-2xl bg-indigo-100 flex items-center justify-center text-3xl">
                  {expert.icon}
                </div>

                <h3 className="font-bold text-lg mt-5">
                  {expert.title}
                </h3>

                <p className="text-gray-500 mt-2">
                  Contributing
                </p>

              </div>

            ))}

          </div>

        </div>

      </div>
    </section>
  );
}

export default ExpertPanel;