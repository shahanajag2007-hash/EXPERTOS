import { Component } from "react";
import { Link } from "react-router-dom";

/**
 * Catches rendering errors so one broken section shows a recovery message
 * instead of blanking the whole application.
 */
class ErrorBoundary extends Component {

  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) {
      console.error("ExpertOS render error:", error, info.componentStack);
    }
  }

  render() {

    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4 py-16">
        <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-8 sm:p-12 max-w-xl w-full text-center">

          <div className="text-5xl">⚠️</div>

          <h1 className="text-2xl sm:text-3xl font-bold mt-6">
            Something went wrong on this page
          </h1>

          <p className="text-gray-500 mt-4 leading-7">
            This section couldn't be displayed. Your other ExpertOS pages are
            unaffected. Try again, or head back to the homepage.
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-4">

            <button
              onClick={() => this.setState({ error: null })}
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-full font-semibold transition"
            >
              Try Again
            </button>

            <Link
              to="/"
              onClick={() => this.setState({ error: null })}
              className="border border-gray-300 hover:bg-gray-100 px-6 py-3 rounded-full font-semibold transition"
            >
              Go Home
            </Link>

          </div>

        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
