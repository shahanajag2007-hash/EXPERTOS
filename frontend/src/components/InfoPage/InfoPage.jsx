import Navbar from "../Navbar/Navbar";
import Footer from "../Footer/Footer";

/** Shared layout for the About, Privacy, Terms and Contact pages. */
export function InfoPage({ eyebrow, title, intro, updated, children }) {
  return (
    <>
      <Navbar />

      <main className="min-h-screen bg-slate-50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-14 sm:py-20">
          {eyebrow && (
            <p className="text-indigo-600 uppercase tracking-widest font-semibold text-sm">{eyebrow}</p>
          )}

          <h1 className="text-4xl sm:text-5xl font-bold mt-3">{title}</h1>

          {intro && <p className="mt-6 text-lg text-gray-600 leading-8">{intro}</p>}

          {updated && <p className="mt-3 text-sm text-gray-400">Last updated: {updated}</p>}

          <div className="mt-10 space-y-6">{children}</div>
        </div>
      </main>

      <Footer />
    </>
  );
}

export function InfoSection({ title, children }) {
  return (
    <section className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8">
      <h2 className="text-xl sm:text-2xl font-bold">{title}</h2>
      <div className="mt-4 space-y-3 text-gray-600 leading-7">{children}</div>
    </section>
  );
}
