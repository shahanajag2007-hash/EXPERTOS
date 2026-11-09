import { Link } from "react-router-dom";
import logo from "../../assets/expertos-icon.png";

function Footer() {
  return (
    <footer className="border-t mt-24">

      <div className="max-w-7xl mx-auto px-6 py-8 flex flex-col md:flex-row justify-between items-center gap-4 text-center md:text-left">

        <div className="flex items-center gap-3">

          <img
            src={logo}
            alt="ExpertOS"
            className="w-10 h-10"
          />

          <h2 className="text-xl font-bold">
            Expert<span className="text-indigo-600">OS</span>
          </h2>

        </div>

        <p className="text-gray-500 text-sm">
          © 2026 ExpertOS Platform. Built for developers who build the future.
        </p>

        <div className="flex flex-wrap justify-center gap-6 sm:gap-8 text-gray-500">

          <Link to="/about" className="hover:text-indigo-600 transition">About</Link>

          <Link to="/privacy" className="hover:text-indigo-600 transition">Privacy</Link>

          <Link to="/terms" className="hover:text-indigo-600 transition">Terms</Link>

          <Link to="/contact" className="hover:text-indigo-600 transition">Contact</Link>

        </div>

      </div>

    </footer>
  );
}

export default Footer;
