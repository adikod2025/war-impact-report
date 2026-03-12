import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-sm text-muted-foreground mb-8">Last updated: March 2, 2026</p>

        <div className="prose prose-invert prose-sm max-w-none space-y-6">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Information We Collect</h2>
            <p className="text-muted-foreground leading-relaxed">
              When you use War Impact Report, we collect the following information: your email address, industry, country, company size, and optionally your company name. This information is necessary to generate your personalized business impact assessment. We also collect standard web analytics data including IP address, browser type, and page views.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. How We Use Your Information</h2>
            <p className="text-muted-foreground leading-relaxed">
              We use your information to generate personalized impact reports using AI analysis, send you the requested reports via email, process payments for premium reports and subscriptions, send weekly update emails if you subscribe, improve our service and report quality, and comply with legal obligations.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Data Storage and Security</h2>
            <p className="text-muted-foreground leading-relaxed">
              Your data is stored securely using industry-standard encryption. We use Stripe for payment processing — we never store your credit card information directly. Report data is cached for 24 hours to improve performance and is then refreshed with the latest crisis data.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. Third-Party Services</h2>
            <p className="text-muted-foreground leading-relaxed">
              We use the following third-party services: AI language models for report generation, Stripe for payment processing, email delivery services for report distribution, and analytics services for website performance monitoring. Each of these services has their own privacy policies governing their use of data.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Your Rights</h2>
            <p className="text-muted-foreground leading-relaxed">
              You have the right to access, correct, or delete your personal data. You may unsubscribe from marketing emails at any time using the unsubscribe link in any email. To request data deletion, please contact us at privacy@warimpactreport.com.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Cookies</h2>
            <p className="text-muted-foreground leading-relaxed">
              We use essential cookies for authentication and session management. We also use analytics cookies to understand how visitors interact with our website. You can disable cookies in your browser settings, though this may affect some functionality.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Contact</h2>
            <p className="text-muted-foreground leading-relaxed">
              For any privacy-related questions or concerns, please contact us at privacy@warimpactreport.com.
            </p>
          </section>
        </div>
      </div>
      <Footer />
    </div>
  );
}
