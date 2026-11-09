import { useNavigate } from "react-router-dom";

function Hero() {

  const navigate = useNavigate();

  function scrollToExperts() {

    const section = document.getElementById("experts-section");

    if (section) {

      section.scrollIntoView({
        behavior: "smooth"
      });

    }

  }

  return (

    <section className="max-w-7xl mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-12 text-center">

      <div className="inline-flex items-center gap-2 bg-indigo-100 text-indigo-700 px-5 py-2 rounded-full font-medium">

        ✨ AI-Powered Technology Consultation

      </div>

      <h1 className="mt-8 text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 leading-tight">

        Consult AI Experts.

        <br />

        Build Better Technology.

      </h1>

      <p className="mt-8 max-w-3xl mx-auto text-lg sm:text-xl text-gray-600">

        Get personalized guidance from specialized AI experts across software architecture,
        security, cloud, databases, documentation and UI design.

      </p>

      <div className="mt-10 flex flex-col sm:flex-row justify-center gap-4 sm:gap-5">

        <button

          onClick={() => navigate("/consultation")}

          className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-xl font-semibold transition"

        >

          Start Consultation →

        </button>

        <button

          onClick={scrollToExperts}

          className="border border-gray-300 px-8 py-4 rounded-xl font-semibold hover:bg-gray-100 transition"

        >

          Explore Experts

        </button>

      </div>

    </section>

  );

}

export default Hero;