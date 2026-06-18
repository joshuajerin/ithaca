import LegalLayout from "./LegalLayout";

export default function PrivacyPage() {
  return (
    <LegalLayout
      title="Privacy Policy"
      subtitle="We collect only what we need, store it securely, and never sell it."
      effectiveDate="June 18, 2026"
      lastUpdated="June 18, 2026"
      sections={[
        {
          heading: "Who We Are",
          content: (
            <p>Doomberg ("we," "us," or "our") operates the Doomberg platform at doomberg.me — a financial tool-platform for AI agents and developers. This Privacy Policy explains how we collect, use, disclose, and protect your personal information. For privacy inquiries, contact us at <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a>.</p>
          ),
        },
        {
          heading: "Information We Collect",
          content: (
            <div>
              <p><strong>Account information:</strong> When you create an account, we collect your name, email address, and (if using OAuth) your provider ID from Google or GitHub. We never store your Google or GitHub password.</p>
              <p className="mt-3"><strong>Usage data:</strong> We collect information about how you use the Platform — including strategy specifications you create, backtest runs, API calls made, and feature interactions. This data is tied to your account.</p>
              <p className="mt-3"><strong>Technical data:</strong> IP address, browser type, operating system, referring URLs, and session identifiers. This is collected automatically when you access the Platform.</p>
              <p className="mt-3"><strong>Communications:</strong> If you contact us by email, we retain those communications.</p>
              <p className="mt-3"><strong>What we do NOT collect:</strong> We do not collect payment card information (we don't currently charge for the service), social security numbers, or government identification numbers.</p>
            </div>
          ),
        },
        {
          heading: "How We Use Your Information",
          content: (
            <div>
              <p>We use the information we collect to:</p>
              <ul className="mt-2 list-disc pl-5 space-y-1">
                <li>Provide, operate, and maintain the Platform</li>
                <li>Authenticate your account and secure your data</li>
                <li>Process and execute your requests (backtests, data queries, paper trading)</li>
                <li>Monitor and improve Platform performance and security</li>
                <li>Communicate with you about your account, updates, and support</li>
                <li>Comply with legal obligations</li>
                <li>Enforce our Terms of Service</li>
              </ul>
              <p className="mt-3">We do <strong>not</strong> use your personal information for targeted advertising, nor do we sell or share it with advertising networks.</p>
            </div>
          ),
        },
        {
          heading: "Legal Basis for Processing (EU / GDPR Users)",
          content: (
            <div>
              <p>If you are located in the European Economic Area, the United Kingdom, or Switzerland, we process your personal data under the following legal bases:</p>
              <ul className="mt-2 list-disc pl-5 space-y-2">
                <li><strong>Contract performance:</strong> Processing necessary to provide the Platform to you (account creation, executing requests).</li>
                <li><strong>Legitimate interests:</strong> Security monitoring, fraud prevention, service improvement — where these interests are not overridden by your data protection rights.</li>
                <li><strong>Legal obligation:</strong> Where processing is required to comply with applicable law.</li>
                <li><strong>Consent:</strong> For any processing based on consent, you have the right to withdraw it at any time by contacting us at <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a>.</li>
              </ul>
            </div>
          ),
        },
        {
          heading: "Data Sharing & Third Parties",
          content: (
            <div>
              <p>We share your information with third parties only in the following circumstances:</p>
              <ul className="mt-2 list-disc pl-5 space-y-2">
                <li><strong>Service providers:</strong> DigitalOcean (cloud hosting and database services) processes data on our behalf under data processing agreements. They do not use your data for their own purposes.</li>
                <li><strong>OAuth providers:</strong> When you sign in with Google or GitHub, those providers confirm your identity. We receive only the information you authorized them to share (name, email, provider ID). We do not share your data back with them.</li>
                <li><strong>Legal requirements:</strong> We may disclose information if required by law, regulation, subpoena, court order, or government request, or to protect the rights, property, or safety of Doomberg, our users, or others.</li>
                <li><strong>Business transfers:</strong> If Doomberg is acquired or merges with another company, your information may be transferred as part of that transaction. We will notify you before your data is subject to a different privacy policy.</li>
              </ul>
              <p className="mt-3"><strong>We do not sell your personal information to third parties.</strong></p>
            </div>
          ),
        },
        {
          heading: "Data Retention",
          content: (
            <div>
              <p>We retain your personal information for as long as your account is active. When you delete your account, we delete your personal information within <strong>30 days</strong>, except where we are required to retain it longer for legal compliance (such as fraud prevention records, which we may retain for up to 5 years).</p>
              <p className="mt-3">Server logs and usage data are retained for <strong>90 days</strong>. Aggregated, de-identified analytics data may be retained indefinitely.</p>
            </div>
          ),
        },
        {
          heading: "Cookies & Local Storage",
          content: (
            <div>
              <p>The Platform uses <strong>localStorage</strong> (not third-party cookies) to store your session token and user preferences locally in your browser. This data never leaves your device except as part of authenticated API requests to doomberg.me.</p>
              <p className="mt-3">We do <strong>not</strong> use:</p>
              <ul className="mt-2 list-disc pl-5 space-y-1">
                <li>Third-party advertising cookies</li>
                <li>Cross-site tracking pixels</li>
                <li>Social media tracking scripts</li>
              </ul>
              <p className="mt-3">If we add analytics or tracking in the future, we will update this policy and provide appropriate consent mechanisms before doing so.</p>
            </div>
          ),
        },
        {
          heading: "Your Privacy Rights",
          content: (
            <div>
              <p>Depending on your location, you may have the following rights regarding your personal data:</p>
              <ul className="mt-2 list-disc pl-5 space-y-2">
                <li><strong>Access:</strong> Request a copy of the personal data we hold about you.</li>
                <li><strong>Correction:</strong> Request correction of inaccurate or incomplete data.</li>
                <li><strong>Deletion:</strong> Request deletion of your personal data ("right to be forgotten").</li>
                <li><strong>Portability:</strong> Request your data in a machine-readable format.</li>
                <li><strong>Objection:</strong> Object to processing based on legitimate interests.</li>
                <li><strong>Restriction:</strong> Request restriction of processing in certain circumstances.</li>
              </ul>
              <p className="mt-3">To exercise any of these rights, email us at <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a>. We will respond within 30 days (45 days for complex requests).</p>
            </div>
          ),
        },
        {
          heading: "California Residents (CCPA / CPRA)",
          content: (
            <div>
              <p>If you are a California resident, you have additional rights under the California Consumer Privacy Act (CCPA) and California Privacy Rights Act (CPRA):</p>
              <ul className="mt-2 list-disc pl-5 space-y-2">
                <li><strong>Right to Know:</strong> The categories and specific pieces of personal information we collect, the sources, the business purpose, and the third parties we share it with.</li>
                <li><strong>Right to Delete:</strong> Request deletion of personal information we have collected, subject to legal exceptions.</li>
                <li><strong>Right to Correct:</strong> Request correction of inaccurate personal information.</li>
                <li><strong>Right to Opt-Out of Sale/Sharing:</strong> We do not sell or share your personal information for cross-context behavioral advertising. There is nothing to opt out of, but you have this right.</li>
                <li><strong>Right to Non-Discrimination:</strong> We will not discriminate against you for exercising your CCPA rights.</li>
              </ul>
              <p className="mt-3">To submit a California privacy request, email <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a> with the subject line "California Privacy Request."</p>
            </div>
          ),
        },
        {
          heading: "EU / EEA Residents (GDPR)",
          content: (
            <div>
              <p>For EU/EEA residents, in addition to the rights listed above, you have the right to lodge a complaint with your local data protection supervisory authority if you believe we have processed your data unlawfully.</p>
              <p className="mt-3">Our data protection contact is <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a>. If your complaint is not resolved to your satisfaction, you can contact your national data protection authority.</p>
            </div>
          ),
        },
        {
          heading: "Children's Privacy",
          content: (
            <div>
              <p>The Platform is not directed to children under 13 years of age (under 16 for EU/EEA residents). We do not knowingly collect personal information from children. If we learn that we have collected personal information from a child under the applicable age threshold, we will delete it promptly.</p>
              <p className="mt-3">If you believe a child has provided us with personal information, contact us at <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a>.</p>
            </div>
          ),
        },
        {
          heading: "Security",
          content: (
            <p>We implement appropriate technical and organizational security measures to protect your personal information against unauthorized access, alteration, disclosure, or destruction. These include encrypted storage, encrypted data in transit (TLS), access controls, and regular security reviews. However, no method of transmission over the Internet or method of electronic storage is 100% secure. We cannot guarantee absolute security.</p>
          ),
        },
        {
          heading: "International Transfers",
          content: (
            <p>Your information is processed and stored on servers located in the United States (DigitalOcean, New York region). If you access the Platform from outside the United States, your information will be transferred to, processed, and stored in the US, where data protection laws may differ from those in your jurisdiction. By using the Platform, you consent to this transfer.</p>
          ),
        },
        {
          heading: "Changes to This Policy",
          content: (
            <p>We may update this Privacy Policy from time to time. We will notify you of material changes by posting the updated policy with a new effective date and, for significant changes, by sending an email notification to the address associated with your account. Your continued use of the Platform after such changes constitutes your acceptance of the updated policy.</p>
          ),
        },
        {
          heading: "Contact Us",
          content: (
            <div>
              <p>For any privacy questions, requests, or concerns:</p>
              <p className="mt-2">
                <strong>Email:</strong>{" "}
                <a href="mailto:privacy@doomberg.me" className="text-olive hover:underline">privacy@doomberg.me</a>
              </p>
              <p className="mt-1">We aim to respond to all privacy inquiries within 5 business days.</p>
            </div>
          ),
        },
      ]}
    />
  );
}
