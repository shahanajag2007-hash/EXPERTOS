import { Link } from "react-router-dom";
function AIGuide() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16">

      <div className="rounded-3xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-8 sm:p-12 shadow-xl">

        <p className="uppercase tracking-widest text-sm opacity-80">
          Featured
        </p>

        <h2 className="text-3xl sm:text-4xl font-bold mt-3">
          🤖 AI Guide
        </h2>

        <p className="mt-6 text-lg text-indigo-100 max-w-2xl">
          Answer a few simple questions and our AI Guide will analyze your
          situation, recommend the right expert, and help you frame your
          problem clearly.
        </p>

        <Link
  to="/guide"
  className="inline-block mt-8 bg-white text-indigo-700 font-semibold px-8 py-4 rounded-full hover:bg-gray-100 transition"
>
  Start with AI Guide →
</Link>

      </div>

    </section>
  );
}

export default AIGuide;