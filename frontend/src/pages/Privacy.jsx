import { Link } from "react-router-dom";
import { InfoPage, InfoSection } from "../components/InfoPage/InfoPage";

// Describes what this codebase actually does. Update it whenever storage,
// retention or AI providers change (backend/services/consultations.py,
// backend/migrations/, backend/providers/).
function Privacy() {
  return (
    <InfoPage
      eyebrow="Privacy"
      title="Privacy Policy"
      intro="This page explains what information ExpertOS handles, where it goes and how long it is kept. It describes how the software works; the operator of each ExpertOS installation is responsible for how they run it."
      updated="19 October 2026"
    >
      <InfoSection title="What you enter">
        <p>
          Consultations use the text you type (project descriptions, answers to discovery
          questions, chat messages and questions in the live room) and any files you upload.
          An account is optional; if you create one, ExpertOS stores your email address, an
          optional name and a one-way hash of your password (never the password itself).
        </p>
        <p>
          Please don't enter passwords, personal data about other people, or confidential
          information you aren't allowed to share with third-party AI services.
        </p>
      </InfoSection>

      <InfoSection title="Data sent to AI providers">
        <p>
          To generate answers, the text of your consultation, including text extracted from
          files you upload and any uploaded images, is sent to an external AI provider.
          ExpertOS tries <strong>OpenRouter</strong> first, which forwards requests to the
          underlying model's provider. If that fails it may fall back to <strong>Google
          Gemini</strong>, <strong>Groq</strong>, or a local <strong>Ollama</strong> server,
          depending on how the installation is configured.
        </p>
        <p>
          Those services process your text under their own terms and privacy policies. Some free
          AI models may log prompts or use them to improve their services. ExpertOS cannot
          control or delete data held by these providers.
        </p>
      </InfoSection>

      <InfoSection title="What ExpertOS stores">
        <p>The server keeps a database with:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>Consultation records:</strong> the type of consultation, which experts took
            part and when. These records contain no project text and are used for the
            consultation count.
          </li>
          <li>
            <strong>Expert Panel content:</strong> the problem description and the experts'
            answers, kept so the live room can discuss them.
          </li>
          <li>
            <strong>Live discussions:</strong> the transcript and the closing summary.
          </li>
          <li>
            <strong>Saved conversations:</strong> Expert Room and Start Consultation
            conversations (your answers or project description, the report or analysis, and the
            chat messages), so you can reopen and continue them.
          </li>
          <li>
            <strong>Uploaded files:</strong> the file and the text extracted from it. Files are
            stored privately on the server, are never published, and can only be used by the
            browser or account that uploaded them.
          </li>
          <li>
            <strong>Accounts</strong> (if you create one): email, optional name, password hash and
            sign-in sessions.
          </li>
          <li>
            <strong>Ratings:</strong> the star rating and any written feedback you add.
          </li>
          <li>
            <strong>Contact messages:</strong> the name, email, subject and message you submit.
          </li>
          <li>
            <strong>Performance measurements:</strong> how long AI responses took, whether they
            succeeded, and which AI provider and model answered. These contain no consultation text.
          </li>
        </ul>
        <p>
          Without an account, saved conversations and uploads belong to this browser (identified
          by a random ID stored in it). With an account they belong to the account, and signing in
          moves this browser's conversations to it.
        </p>
        <p>
          The server's console log can include request details and AI responses for debugging.
          How long that log is kept depends on how the operator runs the server.
        </p>
      </InfoSection>

      <InfoSection title="In your browser">
        <p>
          ExpertOS stores in your browser's local storage the IDs and access tokens of
          consultations you completed, which let you rate them and reopen live discussions, a
          random browser ID that your saved conversations belong to, your sign-in session if you
          signed in, and your light or dark theme choice. ExpertOS does not use advertising or
          analytics cookies.
        </p>
        <p>
          Access tokens are stored on the server only as a one-way hash. Anyone with the token
          from your browser can open that consultation's live room, so treat your device
          accordingly. Clearing site data removes the tokens.
        </p>
      </InfoSection>

      <InfoSection title="Retention and deletion">
        <ul className="list-disc pl-5 space-y-1">
          <li>
            Panel problem descriptions, expert answers, live transcripts and summaries are deleted
            automatically 30 days after the consultation (the operator can change this period).
          </li>
          <li>
            You can delete a live discussion and its panel content sooner with{" "}
            <em>Delete this conversation</em> on its summary.
          </li>
          <li>Contact messages are deleted automatically after 180 days.</li>
          <li>
            Conversations saved without an account are deleted after 90 days without activity.
            Conversations of an account are kept until you delete them.
          </li>
          <li>
            Deleting a conversation (✕ in its history list) deletes its messages and uploaded
            files. Uploaded files that are never used in a conversation are deleted after a day.
          </li>
          <li>
            Consultation records, ratings with their feedback, and performance measurements are
            kept so the statistics stay accurate. Deleting content does not remove these
            anonymous records.
          </li>
        </ul>
      </InfoSection>

      <InfoSection title="Abuse prevention">
        <p>
          To limit spam, the server counts recent rating and contact submissions per IP address in
          memory. IP addresses are not written to the database.
        </p>
      </InfoSection>

      <InfoSection title="Security">
        <p>
          ExpertOS limits who can open a consultation's data to holders of its access token and
          keeps API keys on the server only. No system is perfectly secure, and the protection of
          data in transit depends on the installation using HTTPS.
        </p>
      </InfoSection>

      <InfoSection title="Questions">
        <p>
          Use the <Link to="/contact" className="text-indigo-600 hover:underline">contact page</Link>{" "}
          to reach the operator of this installation.
        </p>
      </InfoSection>
    </InfoPage>
  );
}

export default Privacy;
