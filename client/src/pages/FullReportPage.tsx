import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { trpc } from "@/lib/trpc";
import {
  Shield, Printer, Download, Copy, Share2, Check, Clock, Zap,
  Linkedin, Twitter, Mail, ArrowRight, AlertTriangle, FileText
} from "lucide-react";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Streamdown } from "streamdown";
import { motion } from "framer-motion";

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "bg-crisis-red text-white",
  HIGH: "bg-crisis-gold text-black",
  MODERATE: "bg-crisis-blue text-white",
  LOW: "bg-crisis-green text-white",
};

const SECTION_ICONS: Record<string, string> = {
  "1": "shield",
  "2": "target",
  "3": "link",
  "4": "truck",
  "5": "dollar",
  "6": "zap",
  "7": "calendar",
  "8": "trending-up",
};

export default function FullReportPage() {
  const [copied, setCopied] = useState(false);
  const [showShareMenu, setShowShareMenu] = useState(false);

  // Check for report ID in URL params (after Stripe payment redirect)
  const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const reportId = urlParams?.get("report_id");
  const success = urlParams?.get("success");

  // Load report if we have an ID
  const { data: report, isLoading } = trpc.report.getById.useQuery(
    { id: Number(reportId) },
    { enabled: !!reportId }
  );

  const handlePrint = () => window.print();

  const handleCopy = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setCopied(true);
      toast.success("Report copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy");
    }
  };

  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/report?utm_source=share&utm_medium=social&utm_campaign=full_report`
    : "";

  const handleShare = (platform: string) => {
    const text = "I just received my comprehensive Iran War business impact report. Get your personalized assessment:";
    const urls: Record<string, string> = {
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`,
      twitter: `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(shareUrl)}`,
      email: `mailto:?subject=${encodeURIComponent("War Impact Report - Full Intelligence Briefing")}&body=${encodeURIComponent(`${text}\n\n${shareUrl}`)}`,
    };
    if (urls[platform]) window.open(urls[platform], "_blank");
    setShowShareMenu(false);
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(shareUrl);
    toast.success("Link copied to clipboard");
    setShowShareMenu(false);
  };

  // No report ID — show access required
  if (!reportId) {
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
            <AlertTriangle className="w-4 h-4" />
            Get Your Report
          </a>
        </div>
        <Footer />
      </div>
    );
  }

  // Loading
  if (isLoading) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <div className="flex flex-col items-center justify-center py-24">
          <div className="relative w-20 h-20 mb-6">
            <div className="absolute inset-0 rounded-full border-2 border-crisis-red/20" />
            <div className="absolute inset-0 rounded-full radar-ping border-2 border-crisis-red/30" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-3 h-3 rounded-full bg-crisis-red pulse-dot" />
            </div>
          </div>
          <p className="font-mono text-sm text-muted-foreground">Loading your report...</p>
        </div>
        <Footer />
      </div>
    );
  }

  // Report not found
  if (!report) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-24 text-center">
          <AlertTriangle className="w-16 h-16 text-crisis-red mx-auto mb-6" />
          <h1 className="text-2xl font-bold mb-3">Report Not Found</h1>
          <p className="text-muted-foreground mb-6">
            The report you're looking for doesn't exist or has expired.
          </p>
          <a
            href="/report"
            className="inline-flex items-center gap-2 px-6 py-3 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all"
          >
            Generate a New Report
          </a>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      {/* Sticky Action Bar */}
      <div className="sticky top-0 z-40 bg-card/95 backdrop-blur-sm border-b border-border/50 no-print">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-4 h-4 text-crisis-red" />
            <span className="font-mono text-xs tracking-wider uppercase text-muted-foreground">
              Full Intelligence Report
            </span>
            <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded ${RISK_COLORS[report.riskLevel || "HIGH"]}`}>
              {report.riskLevel} RISK
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrint}
              className="p-2 rounded-lg hover:bg-secondary transition-colors"
              aria-label="Print report"
            >
              <Printer className="w-4 h-4" />
            </button>
            <button
              onClick={handleCopy}
              className="p-2 rounded-lg hover:bg-secondary transition-colors"
              aria-label="Copy report"
            >
              {copied ? <Check className="w-4 h-4 text-crisis-green" /> : <Copy className="w-4 h-4" />}
            </button>
            <div className="relative">
              <button
                onClick={() => setShowShareMenu(!showShareMenu)}
                className="p-2 rounded-lg hover:bg-secondary transition-colors"
                aria-label="Share report"
              >
                <Share2 className="w-4 h-4" />
              </button>
              {showShareMenu && (
                <div className="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg p-2 min-w-[160px] z-50">
                  <button onClick={() => handleShare("linkedin")} className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded hover:bg-secondary transition-colors">
                    <Linkedin className="w-4 h-4" /> LinkedIn
                  </button>
                  <button onClick={() => handleShare("twitter")} className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded hover:bg-secondary transition-colors">
                    <Twitter className="w-4 h-4" /> X / Twitter
                  </button>
                  <button onClick={() => handleShare("email")} className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded hover:bg-secondary transition-colors">
                    <Mail className="w-4 h-4" /> Email
                  </button>
                  <button onClick={handleCopyLink} className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded hover:bg-secondary transition-colors">
                    <Copy className="w-4 h-4" /> Copy Link
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Report Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-card border border-border/50 rounded-xl overflow-hidden mb-8"
        >
          <div className="bg-gradient-to-r from-crisis-red/10 via-crisis-red/5 to-transparent p-6 border-b border-border/30">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full bg-crisis-red pulse-dot" />
              <span className="font-mono text-xs text-crisis-red tracking-widest uppercase">
                CLASSIFIED INTELLIGENCE BRIEFING
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold mb-2">
              Iran War Impact Assessment
            </h1>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
              <span><strong className="text-foreground">{report.industry}</strong></span>
              <span><strong className="text-foreground">{report.country}</strong></span>
              <span><strong className="text-foreground">{report.companySize}</strong></span>
            </div>
            <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {new Date(report.createdAt).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
              </span>
              <span className="flex items-center gap-1"><Zap className="w-3 h-3" /> AI-powered analysis</span>
              <span className={`font-mono text-xs font-bold px-2 py-0.5 rounded ${RISK_COLORS[report.riskLevel || "HIGH"]}`}>
                {report.riskLevel} RISK
              </span>
            </div>
          </div>

          {/* Report Content */}
          <div className="p-6 sm:p-8">
            <div className="prose prose-invert prose-sm max-w-none">
              <Streamdown>{report.content}</Streamdown>
            </div>
          </div>

          {/* Sources Footer */}
          <div className="px-6 py-3 border-t border-border/30 text-xs text-muted-foreground">
            <span className="font-mono tracking-wider uppercase">Sources:</span>{" "}
            EIA, IMF World Economic Outlook, Bloomberg Terminal, Reuters, IATA, Clarksons Research, Lloyd's of London, World Bank, OPEC Monthly Report
          </div>
        </motion.div>

        {/* Subscription Upsell */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gradient-to-r from-crisis-gold/5 to-crisis-blue/5 border border-crisis-gold/30 rounded-xl p-6 mb-8 no-print"
        >
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-lg bg-crisis-gold/10 flex items-center justify-center shrink-0">
              <FileText className="w-6 h-6 text-crisis-gold" />
            </div>
            <div>
              <h3 className="text-lg font-bold mb-1">Stay Ahead of the Crisis</h3>
              <p className="text-sm text-muted-foreground mb-4">
                The situation evolves daily. Get weekly AI-updated reports with the latest data, new supplier alternatives, and revised cost projections.
              </p>
              <button
                onClick={() => toast("Feature coming soon", { description: "Subscription payments will be available shortly." })}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-crisis-gold text-black font-semibold rounded-lg hover:bg-crisis-gold/90 transition-all text-sm"
              >
                Subscribe for Weekly Updates — $19/mo
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </motion.div>

        {/* Disclaimer */}
        <div className="bg-card border border-border/50 rounded-xl p-5 text-xs text-muted-foreground no-print">
          <p className="font-mono text-[10px] tracking-widest uppercase text-muted-foreground/70 mb-2">DISCLAIMER</p>
          <p>
            This report is generated by AI analysis and should be used as one input among many in business decision-making.
            Data is sourced from public reports, commodity exchanges, shipping databases, and government publications.
            Verify critical decisions with qualified professional advisors. Past performance and current analysis do not guarantee future outcomes.
          </p>
        </div>
      </div>

      <Footer />
    </div>
  );
}
