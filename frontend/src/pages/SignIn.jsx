import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar/Navbar";
import { register, signIn, signOut, useSession } from "../services/auth";

// Optional accounts. Everything works without one; signing in keeps your
// conversations and uploads with your account so you can reopen them from any
// browser. Conversations started in this browser before signing in are moved
// to the account.
function SignIn() {
  const navigate = useNavigate();
  const user = useSession();

  const [mode, setMode] = useState("signin");   // signin | register
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);

  const input = "mt-1 w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500";
  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  function validate() {
    const next = {};
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) next.email = "Please enter a valid email address.";
    if (!form.password) next.password = "Please enter your password.";
    else if (mode === "register" && (form.password.length < 8 || form.password.length > 128)) {
      next.password = "Use a password of 8 to 128 characters.";
    }
    if (form.name.length > 100) next.name = "Name must be 100 characters or fewer.";
    return next;
  }

  async function submit(e) {
    e.preventDefault();
    const found = validate();
    setErrors(found);
    setServerError("");
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      if (mode === "register") {
        await register({ name: form.name.trim(), email: form.email.trim(), password: form.password });
      } else {
        await signIn({ email: form.email.trim(), password: form.password });
      }
      setForm({ name: "", email: "", password: "" });
      navigate("/experts");
    } catch (err) {
      setErrors(err.fields || {});
      setServerError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next) {
    setMode(next);
    setErrors({});
    setServerError("");
  }

  return (
    <>
      <Navbar />

      <div className="min-h-[calc(100vh-73px)] bg-slate-50 flex items-center justify-center px-4 py-12">

        <div className="bg-white rounded-3xl shadow-xl p-8 sm:p-12 w-full max-w-[520px] text-center">

          {user ? (
            <>
              <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">
                Signed in
              </p>

              <h1 className="text-3xl sm:text-4xl font-bold mt-3">
                {user.name ? `Welcome, ${user.name.split(" ")[0]}` : "You're signed in"}
              </h1>

              <p className="text-gray-500 mt-4 leading-7">
                Signed in as <strong>{user.email}</strong>. Your conversations and uploaded files are
                saved to your account, so you can reopen them from any browser.
              </p>

              <div className="mt-8 flex flex-col sm:flex-row justify-center gap-4">
                <Link
                  to="/experts"
                  className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-xl font-semibold"
                >
                  Browse the experts
                </Link>
                <button
                  onClick={signOut}
                  className="border border-slate-300 hover:bg-slate-50 px-8 py-4 rounded-xl font-semibold"
                >
                  Sign out
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">
                {mode === "register" ? "Create account" : "Sign in"}
              </p>

              <h1 className="text-3xl sm:text-4xl font-bold mt-3">
                {mode === "register" ? "Create your ExpertOS account" : "Welcome back"}
              </h1>

              <p className="text-gray-500 mt-4 leading-7">
                An account is optional. It keeps your conversations and uploaded files so you can
                continue them from any browser. Conversations from this browser are added to it.
              </p>

              <form onSubmit={submit} noValidate className="mt-8 space-y-5 text-left">

                {mode === "register" && (
                  <label className="block text-sm font-medium text-gray-700">
                    Name <span className="text-gray-400 font-normal">(optional)</span>
                    <input className={input} value={form.name} onChange={update("name")} maxLength={100}
                      autoComplete="name" aria-invalid={Boolean(errors.name)} />
                    {errors.name && <span className="block mt-1 text-sm text-red-600">{errors.name}</span>}
                  </label>
                )}

                <label className="block text-sm font-medium text-gray-700">
                  Email
                  <input className={input} type="email" value={form.email} onChange={update("email")} maxLength={254}
                    autoComplete="email" required aria-invalid={Boolean(errors.email)} />
                  {errors.email && <span className="block mt-1 text-sm text-red-600">{errors.email}</span>}
                </label>

                <label className="block text-sm font-medium text-gray-700">
                  Password
                  <input className={input} type="password" value={form.password} onChange={update("password")}
                    maxLength={128} required aria-invalid={Boolean(errors.password)}
                    autoComplete={mode === "register" ? "new-password" : "current-password"} />
                  {errors.password && <span className="block mt-1 text-sm text-red-600">{errors.password}</span>}
                  {mode === "register" && !errors.password && (
                    <span className="block mt-1 text-xs text-gray-400">At least 8 characters.</span>
                  )}
                </label>

                {serverError && (
                  <p className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm" role="alert">
                    {serverError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={busy}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-4 rounded-xl font-semibold"
                >
                  {busy ? "Please wait..." : mode === "register" ? "Create account" : "Sign in"}
                </button>
              </form>

              <p className="text-gray-500 mt-6 text-sm">
                {mode === "register" ? "Already have an account? " : "New to ExpertOS? "}
                <button
                  type="button"
                  onClick={() => switchMode(mode === "register" ? "signin" : "register")}
                  className="text-indigo-600 hover:underline font-medium"
                >
                  {mode === "register" ? "Sign in" : "Create an account"}
                </button>
              </p>

              <p className="text-gray-500 mt-3 text-sm leading-6">
                See the{" "}
                <Link to="/privacy" className="text-indigo-600 hover:underline">privacy page</Link>{" "}
                for what is stored.
              </p>
            </>
          )}

        </div>

      </div>

    </>
  );
}

export default SignIn;
