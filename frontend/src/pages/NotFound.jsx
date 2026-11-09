import { Link } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";

function NotFound({
  title = "Page not found",
  message = "The page you're looking for doesn't exist or has moved.",
}) {
  return (
    <>
      <Navbar />

      <div className="min-h-[70vh] bg-slate-50 flex items-center justify-center px-4 py-16">

        <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-8 sm:p-12 max-w-xl w-full text-center">

          <p className="text-indigo-600 font-semibold uppercase tracking-widest">
            404
          </p>

          <h1 className="text-3xl sm:text-4xl font-bold mt-4">
            {title}
          </h1>

          <p className="text-gray-500 mt-4 leading-7">
            {message}
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-4">

            <Link
              to="/experts"
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-full font-semibold transition"
            >
              Browse Experts
            </Link>

            <Link
              to="/"
              className="border border-gray-300 hover:bg-gray-100 px-6 py-3 rounded-full font-semibold transition"
            >
              Go Home
            </Link>

          </div>

        </div>

      </div>
    </>
  );
}

export default NotFound;
