import { useEffect } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary/ErrorBoundary";
import ExpertRoom from "./pages/ExpertRoom";
import Home from "./pages/Home";
import Guide from "./pages/Guide";
import Recommendation from "./pages/Recommendation";
import Experts from "./pages/Experts";
import Consultation from "./pages/Consultation";
import ExpertPanel from "./pages/ExpertPanel";
import DesignAdvisor from "./pages/DesignAdvisor";
import SignIn from "./pages/SignIn";
import About from "./pages/About";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import Contact from "./pages/Contact";
import NotFound from "./pages/NotFound";

function App() {
  const { pathname } = useLocation();

  // Start each page at the top instead of keeping the previous scroll position.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    // Keyed by path so navigating away from a crashed page recovers.
    <ErrorBoundary key={pathname}>
    <Routes>

      <Route
        path="/"
        element={<Home />}
      />

      <Route
        path="/guide"
        element={<Guide />}
      />

      <Route
        path="/recommendation"
        element={<Recommendation />}
      />

      <Route
        path="/experts"
        element={<Experts />}
      />

      <Route
        path="/consultation"
        element={<Consultation />}
      />
      <Route
        path="/panel"
        element={<ExpertPanel />}
      />

      <Route
        path="/design-advisor"
        element={<DesignAdvisor />}
      />

      <Route
        path="/signin"
        element={<SignIn />}
      />
      <Route
        path="/expert/:id"
        element={<ExpertRoom />}
      />
      <Route path="/about" element={<About />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/terms" element={<Terms />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
    </ErrorBoundary>
  );
}

export default App;
