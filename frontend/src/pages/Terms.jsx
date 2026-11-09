import { Link } from "react-router-dom";
import { InfoPage, InfoSection } from "../components/InfoPage/InfoPage";

function Terms() {
  return (
    <InfoPage
      eyebrow="Terms"
      title="Terms of Use"
      intro="These terms describe how ExpertOS may be used and the limits of its AI-generated advice. They are a plain-language summary written for this application and have not been reviewed by a lawyer."
      updated="19 October 2026"
    >
      <InfoSection title="1. What ExpertOS is">
        <p>
          ExpertOS provides AI-generated technical consultations. The experts are AI personas, not
          licensed or certified human professionals, and no professional relationship is created
          by using the service.
        </p>
      </InfoSection>

      <InfoSection title="2. Limits of AI-generated recommendations">
        <ul className="list-disc pl-5 space-y-1">
          <li>Answers can be wrong, incomplete, outdated or inconsistent between experts.</li>
          <li>
            The experts only know what you tell them. They cannot inspect your systems, code or
            infrastructure.
          </li>
          <li>
            Suggested metrics and targets are goals to measure against, not measured results.
            Live discussions and summaries are generated from the conversation and may misstate
            it.
          </li>
          <li>
            Don't rely on ExpertOS alone for security, legal, compliance, financial or
            safety-critical decisions. Have a qualified person review them.
          </li>
        </ul>
      </InfoSection>

      <InfoSection title="3. Your responsibilities">
        <ul className="list-disc pl-5 space-y-1">
          <li>Review, test and verify recommendations before implementing them.</li>
          <li>
            Only submit information you have the right to share with the third-party AI providers
            described in the <Link to="/privacy" className="text-indigo-600 hover:underline">privacy policy</Link>.
          </li>
          <li>Keep your browser's consultation access tokens to yourself.</li>
        </ul>
      </InfoSection>

      <InfoSection title="4. Acceptable use">
        <p>Don't use ExpertOS to:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>break the law or infringe anyone's rights;</li>
          <li>attack, probe or disrupt systems you aren't authorised to test;</li>
          <li>generate malware or plan harm to people or systems;</li>
          <li>overload the service, bypass its rate limits or automate abusive traffic;</li>
          <li>submit other people's personal data without permission.</li>
        </ul>
      </InfoSection>

      <InfoSection title="5. Availability">
        <p>
          ExpertOS depends on external AI providers that can be slow, rate-limited or unavailable,
          and free AI tiers have daily limits. The service is provided as available, without any
          guaranteed uptime or response time. Features may change or be removed.
        </p>
      </InfoSection>

      <InfoSection title="6. Content and intellectual property">
        <p>
          You keep any rights you have in what you submit. You may use the AI-generated answers
          for your own projects, subject to the terms of the underlying AI providers. Answers may
          resemble content generated for other users. The ExpertOS name, design and software
          belong to their respective owners.
        </p>
      </InfoSection>

      <InfoSection title="7. Disclaimer">
        <p>
          ExpertOS is provided "as is", without warranties of any kind. To the extent permitted by
          law, its operators are not liable for losses resulting from using or relying on
          AI-generated content.
        </p>
      </InfoSection>

      <InfoSection title="8. Changes">
        <p>
          These terms may be updated. The date above shows the latest version. Questions can be
          sent through the <Link to="/contact" className="text-indigo-600 hover:underline">contact page</Link>.
        </p>
      </InfoSection>
    </InfoPage>
  );
}

export default Terms;
