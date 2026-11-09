import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { FaBars, FaMoon, FaSun, FaTimes } from "react-icons/fa";
import { useTheme } from "../../theme";
import { useSession } from "../../services/auth";
import logo from "../../assets/expertos-icon.png";

const NAV_LINKS = [
  { to: "/experts", label: "Experts" },
  { to: "/guide", label: "AI Guide" },
  { to: "/panel", label: "Expert Panel" },
  { to: "/design-advisor", label: "Design Advisor" },
];

function Navbar() {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const user = useSession();
  const accountLabel = user ? (user.name?.split(" ")[0] || "Account") : "Sign In";
  const nextTheme = theme === "dark" ? "light" : "dark";

  const linkClass = ({ isActive }) =>
    `transition ${isActive ? "text-indigo-600" : "hover:text-indigo-600"}`;

  return (
    <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-gray-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4">

        {/* Logo */}
        <Link
          to="/"
          className="flex items-center gap-3 shrink-0"
          onClick={() => setMenuOpen(false)}
        >

          <img
            src={logo}
            alt="ExpertOS Logo"
            className="w-10 h-10 object-contain"
          />

          <span className="text-2xl font-bold tracking-tight">
            Expert<span className="text-indigo-600">OS</span>
          </span>

        </Link>

        {/* Navigation */}
        <div className="hidden md:flex items-center gap-8 lg:gap-10 text-gray-600 font-medium">

          {NAV_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} className={linkClass}>
              {link.label}
            </NavLink>
          ))}

        </div>

        {/* Right Side */}
        <div className="flex items-center gap-3 sm:gap-5">

          <button
            onClick={toggleTheme}
            className="p-2 rounded-full text-gray-600 hover:text-indigo-600 hover:bg-gray-100 transition"
            aria-label={`Switch to ${nextTheme} mode`}
            title={`Switch to ${nextTheme} mode`}
          >
            {theme === "dark" ? <FaSun aria-hidden="true" /> : <FaMoon aria-hidden="true" />}
          </button>

          <button
            onClick={() => navigate("/signin")}
            className="hidden sm:block text-gray-700 hover:text-indigo-600 transition"
            title={user ? `Signed in as ${user.email}` : "Sign in to keep your conversations"}
          >
            {accountLabel}
          </button>

          <button
            onClick={() => navigate("/experts")}
            className="hidden sm:block bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-full font-semibold shadow-md transition"
          >
            Start Free →
          </button>

          <button
            onClick={() => setMenuOpen((open) => !open)}
            className="md:hidden p-2 text-gray-700 text-xl"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
          >
            {menuOpen ? <FaTimes /> : <FaBars />}
          </button>

        </div>

      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div id="mobile-menu" className="md:hidden border-t border-gray-100 bg-white px-4 pb-6 pt-2">

          <div className="flex flex-col font-medium text-gray-700">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `py-3 border-b border-gray-100 ${isActive ? "text-indigo-600" : ""}`
                }
              >
                {link.label}
              </NavLink>
            ))}

            <NavLink
              to="/signin"
              onClick={() => setMenuOpen(false)}
              className="py-3 border-b border-gray-100 sm:hidden"
            >
              {accountLabel}
            </NavLink>
          </div>

          <button
            onClick={() => {
              setMenuOpen(false);
              navigate("/experts");
            }}
            className="sm:hidden mt-5 w-full bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-full font-semibold transition"
          >
            Start Free →
          </button>

        </div>
      )}
    </nav>
  );
}

export default Navbar;
