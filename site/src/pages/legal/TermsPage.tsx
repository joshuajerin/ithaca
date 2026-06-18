import LegalLayout from "./LegalLayout";

export default function TermsPage() {
  return (
    <LegalLayout
      title="Terms of Service"
      subtitle="By using Doomberg you agree to these terms. Please read them carefully."
      effectiveDate="June 18, 2026"
      lastUpdated="June 18, 2026"
      sections={[
        {
          heading: "Acceptance & Eligibility",
          content: (
            <div>
              <p>By accessing or using the Doomberg platform ("Platform"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree, do not use the Platform.</p>
              <p className="mt-3">You must be at least 18 years old and legally capable of entering into a binding contract in your jurisdiction. If you are using the Platform on behalf of an organization, you represent that you have authority to bind that organization to these Terms.</p>
            </div>
          ),
        },
        {
          heading: "What Doomberg Is — and Is Not",
          content: (
            <div>
              <p>Doomberg is a <strong>financial tool-platform</strong> that allows AI agents and developers to access market data, run backtests on declarative strategy specifications, and simulate paper trading. It is a research and development tool.</p>
              <p className="mt-3">Doomberg is <strong>not</strong>:</p>
              <ul className="mt-2 list-disc pl-5 space-y-1">
                <li>A registered broker-dealer with FINRA or the SEC</li>
                <li>A registered investment adviser with the SEC or any state regulator</li>
                <li>A commodity trading adviser registered with the CFTC</li>
                <li>A cryptocurrency exchange or money services business</li>
              </ul>
              <p className="mt-3">Nothing on the Platform constitutes investment advice, a recommendation to buy or sell any security, or a solicitation to engage in any investment activity. All tools and data are provided for informational and educational purposes only.</p>
            </div>
          ),
        },
        {
          heading: "License Grant",
          content: (
            <p>Subject to these Terms, Doomberg grants you a limited, non-exclusive, non-transferable, revocable license to access and use the Platform for your personal or internal business purposes. This license does not include the right to sublicense, resell, or redistribute the Platform or its data.</p>
          ),
        },
        {
          heading: "Prohibited Uses",
          content: (
            <div>
              <p>You agree not to:</p>
              <ul className="mt-2 list-disc pl-5 space-y-1">
                <li>Reverse engineer, decompile, disassemble, or attempt to derive source code from the Platform</li>
                <li>Scrape, crawl, or systematically download data from the Platform without written permission</li>
                <li>Use the Platform to build a competing product or service</li>
                <li>Create multiple accounts or circumvent account restrictions</li>
                <li>Attempt to gain unauthorized access to any part of the Platform or its infrastructure</li>
                <li>Use the Platform in any way that violates applicable laws, including securities laws and regulations</li>
                <li>Transmit malware, viruses, or other harmful code</li>
                <li>Impersonate any person or entity or misrepresent your affiliation with any person or entity</li>
              </ul>
            </div>
          ),
        },
        {
          heading: "Account Terms",
          content: (
            <div>
              <p>You are responsible for maintaining the confidentiality of your account credentials and for all activity that occurs under your account. You must notify us immediately at <a href="mailto:security@doomberg.me" className="text-olive hover:underline">security@doomberg.me</a> of any unauthorized access.</p>
              <p className="mt-3">We reserve the right to suspend or terminate your account at any time, for any reason, with or without notice. Upon termination, your right to use the Platform immediately ceases.</p>
            </div>
          ),
        },
        {
          heading: "Financial Data & Backtest Disclaimer",
          content: (
            <div>
              <p>The Platform provides access to historical market data, backtesting tools, and simulated paper trading. These are provided <strong>for research purposes only</strong>.</p>
              <p className="mt-3 rounded border border-line bg-sand/50 p-4 font-mono text-[0.82rem] leading-relaxed text-ink-soft">
                <strong>HYPOTHETICAL PERFORMANCE NOTICE (CFTC Rule 4.41):</strong> These results are based on simulated or hypothetical performance results that have certain inherent limitations. Unlike the results shown in an actual performance record, these results do not represent actual trading. Also, because these trades have not actually been executed, these results may have under- or over-compensated for the impact, if any, of certain market factors, such as lack of liquidity. Simulated or hypothetical trading programs in general are also subject to the fact that they are designed with the benefit of hindsight. No representation is being made that any account will or is likely to achieve profits or losses similar to those being shown.
              </p>
              <p className="mt-3">Past performance is not indicative of future results. You should not rely on any data, analysis, or tool provided by the Platform as the basis for actual trading or investment decisions.</p>
            </div>
          ),
        },
        {
          heading: "Disclaimer of Warranties",
          content: (
            <div>
              <p>THE PLATFORM IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT.</p>
              <p className="mt-3">WE DO NOT WARRANT THAT: (A) THE PLATFORM WILL BE UNINTERRUPTED OR ERROR-FREE; (B) ANY DATA OR CONTENT IS ACCURATE, COMPLETE, OR TIMELY; (C) ANY DEFECTS WILL BE CORRECTED; OR (D) THE PLATFORM IS FREE OF VIRUSES OR OTHER HARMFUL COMPONENTS.</p>
            </div>
          ),
        },
        {
          heading: "Limitation of Liability",
          content: (
            <div>
              <p>TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL DOOMBERG, ITS OFFICERS, DIRECTORS, EMPLOYEES, AGENTS, LICENSORS, OR SERVICE PROVIDERS BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING OUT OF OR IN CONNECTION WITH YOUR USE OF THE PLATFORM.</p>
              <p className="mt-3">OUR TOTAL AGGREGATE LIABILITY TO YOU FOR ANY CLAIMS ARISING UNDER THESE TERMS SHALL NOT EXCEED <strong>$100 USD</strong> OR THE AMOUNT YOU PAID TO US IN THE TWELVE MONTHS PRIOR TO THE EVENT GIVING RISE TO THE CLAIM, WHICHEVER IS GREATER.</p>
              <p className="mt-3">Some jurisdictions do not allow the exclusion of certain warranties or the limitation of liability for incidental or consequential damages. In such jurisdictions, our liability shall be limited to the greatest extent permitted by law.</p>
            </div>
          ),
        },
        {
          heading: "Dispute Resolution & Arbitration",
          content: (
            <div>
              <p><strong>PLEASE READ THIS SECTION CAREFULLY. IT AFFECTS YOUR LEGAL RIGHTS.</strong></p>
              <p className="mt-3">Any dispute, claim, or controversy arising out of or relating to these Terms or your use of the Platform shall be resolved by binding arbitration administered by the American Arbitration Association ("AAA") under its Commercial Arbitration Rules, rather than in court.</p>
              <p className="mt-3"><strong>No Class Actions:</strong> You and Doomberg agree that each party may bring claims against the other only in an individual capacity, and not as a plaintiff or class member in any purported class or representative proceeding.</p>
              <p className="mt-3">Notwithstanding the foregoing, either party may seek injunctive or other equitable relief in a court of competent jurisdiction to prevent irreparable harm.</p>
            </div>
          ),
        },
        {
          heading: "Intellectual Property",
          content: (
            <p>The Platform, including its software, data, designs, and content (excluding user-generated data), is owned by Doomberg and protected by intellectual property laws. You may not copy, modify, distribute, sell, or lease any part of the Platform without our prior written consent. You retain ownership of any strategy specifications or data you provide to the Platform.</p>
          ),
        },
        {
          heading: "Governing Law",
          content: (
            <p>These Terms are governed by the laws of the State of Delaware, without regard to conflict of law principles. Any court proceedings (to the extent arbitration is not required) shall be brought in the federal or state courts located in New York County, New York, and you consent to the personal jurisdiction of such courts.</p>
          ),
        },
        {
          heading: "Changes to Terms",
          content: (
            <p>We may modify these Terms at any time. We will notify you of material changes by posting the updated Terms on the Platform with a new effective date. Your continued use of the Platform after such changes constitutes your acceptance of the updated Terms.</p>
          ),
        },
        {
          heading: "Contact",
          content: (
            <p>
              Questions about these Terms? Email us at{" "}
              <a href="mailto:legal@doomberg.me" className="text-olive hover:underline">legal@doomberg.me</a>.
            </p>
          ),
        },
      ]}
    />
  );
}
