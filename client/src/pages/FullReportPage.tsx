import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Shield, Printer, Download, Copy, Share2, Check, Clock, Zap } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Streamdown } from "streamdown";

export default function FullReportPage() {
  const [copied, setCopied] = useState(false);

  // In production, this would load from URL params/session after Stripe payment
  // For now, show a placeholder
  const report = null;

  const handlePrint = () => window.print();
  const handleCopy = () => {
    toast("Feature coming soon", { description: "Copy functionality will be available with full reports." });
  };

  if (!report) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-24 text-center">
          <Shield className="w-16 h-16 text-muted-foreground mx-auto mb-6" />
          <h1 className="text-2xl font-bold mb-3">Full Report Access Required</h1>
          <p className="text-muted-foreground mb-6 max-w-md mx-auto">
            Purchase a full report ($49) or subscribe to weekly updates ($19/mo) to access the complete 8-section intelligence briefing.
          </p>
          <a
            href="/report"
            className="inline-flex items-center gap-2 px-6 py-3 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all"
          >
            Get Your Report
          </a>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <p className="text-muted-foreground">Full report will render here after payment.</p>
      </div>
      <Footer />
    </div>
  );
}
