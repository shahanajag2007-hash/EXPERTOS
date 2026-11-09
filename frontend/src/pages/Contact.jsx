import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { InfoPage, InfoSection } from "../components/InfoPage/InfoPage";
import { postJSON } from "../services/api";
import { validateContact } from "../services/validation";

const EMPTY = { name: "", email: "", subject: "", message: "", website: "" };
function Field({ id, label, optional, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700">
        {label} {optional && <span className="font-normal text-gray-400">(optional)</span>}
      </label>
      {children}
      {error && <p id={`${id}-error`} className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  );
}

function Contact() {
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState("idle");   // idle | sending | sent
  const [serverError, setServerError] = useState("");
  const sending = useRef(false);

  const update = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((errs) => ({ ...errs, [field]: undefined }));
  };

  async function submit(e) {
    e.preventDefault();
    if (sending.current) return;

    const found = validateContact(form);
    setErrors(found);
    setServerError("");
    if (Object.keys(found).length) return;

    sending.current = true;
    setStatus("sending");
    try {
      await postJSON("/contact", {
        name: form.name.trim(),
        email: form.email.trim(),
        subject: form.subject.trim(),
        message: form.message.trim(),
        website: form.website,
      });
      setStatus("sent");
      setForm(EMPTY);
    } catch (err) {
      setErrors(err.fields || {});
      setServerError(err.message);
      setStatus("idle");
    } finally {
      sending.current = false;
    }
  }

  const input = "mt-1 w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500";
  const describedBy = (field) => (errors[field] ? `contact-${field}-error` : undefined);

  return (
    <InfoPage
      eyebrow="Contact"
      title="Contact Us"
      intro="Questions, feedback or a problem with ExpertOS? Send a message to the people running this installation."
    >
      <InfoSection title="How messages are handled">
        <p>
          Messages are saved securely on this ExpertOS server for its operator to read. No email
          notification is sent automatically and no support email address is configured, so a reply
          isn't guaranteed. If you include your email address, the operator can reply to you.
        </p>
        <p>
          For feedback on a consultation itself, the rating section on the{" "}
          <Link to="/" className="text-indigo-600 hover:underline">homepage</Link> is the quickest route.
        </p>
      </InfoSection>

      <section className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8">
        {status === "sent" ? (
          <div className="text-center py-6" role="status">
            <p className="text-xl font-semibold">Your message was received.</p>
            <p className="text-gray-500 mt-2">Thank you. It has been saved for the ExpertOS operator.</p>
            <button onClick={() => setStatus("idle")} className="mt-5 text-indigo-600 hover:underline text-sm">
              Send another message
            </button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="space-y-5">
            <h2 className="text-xl sm:text-2xl font-bold">Send a message</h2>

            <div className="grid sm:grid-cols-2 gap-5">
              <Field id="contact-name" label="Name" optional error={errors.name}>
                <input id="contact-name" className={input} value={form.name} onChange={update("name")}
                  maxLength={100} autoComplete="name" aria-invalid={Boolean(errors.name)} aria-describedby={describedBy("name")} />
              </Field>
              <Field id="contact-email" label="Email" error={errors.email}>
                <input id="contact-email" type="email" className={input} value={form.email} onChange={update("email")}
                  maxLength={254} autoComplete="email" required aria-invalid={Boolean(errors.email)} aria-describedby={describedBy("email")} />
              </Field>
            </div>

            <Field id="contact-subject" label="Subject" error={errors.subject}>
              <input id="contact-subject" className={input} value={form.subject} onChange={update("subject")}
                maxLength={150} required aria-invalid={Boolean(errors.subject)} aria-describedby={describedBy("subject")} />
            </Field>

            <Field id="contact-message" label="Message" error={errors.message}>
              <textarea id="contact-message" rows={6} className={`${input} resize-y`} value={form.message}
                onChange={update("message")} maxLength={5000} required
                aria-invalid={Boolean(errors.message)} aria-describedby={describedBy("message")} />
            </Field>

            {/* Honeypot: hidden from people, filled in by many bots. */}
            <div className="hidden" aria-hidden="true">
              <label htmlFor="contact-website">Website</label>
              <input id="contact-website" tabIndex={-1} autoComplete="off" value={form.website} onChange={update("website")} />
            </div>

            {serverError && (
              <p className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm" role="alert">
                {serverError}
              </p>
            )}

            <button
              type="submit"
              disabled={status === "sending"}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-3 rounded-full font-semibold"
            >
              {status === "sending" ? "Sending..." : "Send Message"}
            </button>

            <p className="text-xs text-gray-400">
              See the <Link to="/privacy" className="hover:underline">privacy policy</Link> for how contact
              messages are stored and when they are deleted.
            </p>
          </form>
        )}
      </section>
    </InfoPage>
  );
}

export default Contact;
