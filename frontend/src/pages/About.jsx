import { Link } from "react-router-dom";
import { InfoPage, InfoSection } from "../components/InfoPage/InfoPage";
import { experts } from "../data/experts";

function About() {
  return (
    <InfoPage
      eyebrow="About"
      title="About ExpertOS"
      intro="ExpertOS is an AI-powered technical consultation platform. Instead of one general chatbot, it gives you specialised AI experts who review your software project from their own discipline, individually or together as a panel."
    >
      <InfoSection title="The six AI experts">
        <p>
          Each expert is an AI persona with its own specialty, instructions and discovery questions.
          They are AI systems, not human professionals.
        </p>
        <ul className="grid sm:grid-cols-2 gap-3 pt-2">
          {Object.values(experts).map((e) => (
            <li key={e.id} className="flex gap-3 bg-slate-50 rounded-2xl p-4">
              <span className="text-2xl" aria-hidden="true">{e.icon}</span>
              <span>
                <Link to={`/expert/${e.id}`} className="font-semibold text-gray-900 hover:text-indigo-600">
                  {e.name} — {e.shortRole}
                </Link>
                <span className="block text-sm text-gray-500">{e.description}</span>
              </span>
            </li>
          ))}
        </ul>
      </InfoSection>

      <InfoSection title="What you can do">
        <ul className="list-disc pl-5 space-y-2">
          <li>
            <strong>Expert recommendations.</strong> In an Expert Room, answer a short discovery
            session and receive a recommendation report, then ask follow-up questions in a chat
            that streams the reply as it's written.
          </li>
          <li>
            <strong>Start Consultation.</strong> Describe a project once and get an architecture,
            stack, database, security and deployment analysis. Mention another expert by name in
            the follow-up chat to bring them in.
          </li>
          <li>
            <strong>Multi-expert panel.</strong> Choose several experts to analyse the same problem
            at the same time, then see a combined recommendation built from their answers.
          </li>
          <li>
            <strong>Live interaction.</strong> After a panel, open a live room where the experts
            discuss trade-offs, respond to each other and answer your questions, then end the
            session for a summary based on the actual discussion.
          </li>
          <li>
            <strong>Knowledge Explorer.</strong> Open short lessons on technologies mentioned in a
            consultation, explained in the context of your project.
          </li>
          <li>
            <strong>AI Guide and Design Advisor.</strong> Find the right starting expert for your
            problem, or take a UI/UX question straight to the design expert.
          </li>
        </ul>
      </InfoSection>

      <InfoSection title="Why use it">
        <p>
          Technical decisions cross disciplines: a database choice affects security, cost and the
          user experience. ExpertOS lets you hear each perspective separately and see where the
          experts agree, disagree and what they would do first, before you commit to a direction.
        </p>
        <p>
          Every answer is AI-generated. Treat it as a well-informed starting point, and verify
          important decisions yourself. See the <Link to="/terms" className="text-indigo-600 hover:underline">terms</Link>.
        </p>
      </InfoSection>

      <InfoSection title="Accounts and files">
        <p>
          Accounts are optional. Without one, your conversations are saved in this browser; with
          one, you can continue them from any browser. You can upload documents (PDF, Word,
          Excel, PowerPoint, ZIP, text and code) and screenshots, and the experts work from their
          actual content.
        </p>
      </InfoSection>
    </InfoPage>
  );
}

export default About;
