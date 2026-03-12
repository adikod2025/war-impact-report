import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { trpc } from "@/lib/trpc";
import { INDUSTRIES, COUNTRIES, COMPANY_SIZES } from "@shared/types";
import { useState, useEffect, useMemo } from "react";
import { useLocation } from "wouter";
import {
  AlertTriangle, Loader2, Shield, FileText, ArrowRight,
  Share2, Copy, Linkedin, Twitter, Mail, Check, Clock, Zap
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";

const LOADING_MESSAGES = [
  "Analyzing geopolitical risk vectors...",
  "Cross-referencing Hormuz closure data...",
  "Mapping supply chain vulnerabilities...",
  "Calculating cost impact projections...",
  "Identifying alternative suppliers...",
  "Generating risk assessment...",
  "Compiling action recommendations...",
  "Finalizing your report...",
];

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "bg-crisis-red text-white",
  HIGH: "bg-crisis-gold text-black",
  MODERATE: "bg-crisis-blue text-white",
  LOW: "bg-crisis-green text-white",
};

export default function ReportPage() {
  const [, navigate] = useLocation();
  const [formData, setFormData] = useState({
    industry: "",
    country: "",
    companySize: "",
    email: "",
    companyName: "",
    honeypot: "", // bot detection
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [phase, setPhase] = useState<"form" | "loading" | "result">("form");
  const [loadingMsgIndex, setLoadingMsgIndex] = useState(0);
  const [report, setReport] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  const generateReport = trpc.report.generateFree.useMutation({
    onSuccess: (data) => {
      setReport(data);
      setPhase("result");
    },
    onError: (error) => {
      toast.error(error.message || "Failed to generate report. Please try again.");
      setPhase("form");
    },
  });

  // Rotate loading messages
  useEffect(() => {
    if (phase !== "loading") return;
    const interval = setInterval(() => {
      setLoadingMsgIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [phase]);

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!formData.industry) errs.industry = "Please select your industry";
    if (!formData.country) errs.country = "Please select your country";
    if (!formData.companySize) errs.companySize = "Please select company size";
    if (!formData.email) {
      errs.email = "Email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errs.email = "Please enter a valid email";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    if (formData.honeypot) return; // bot detected

    setPhase("loading");
    setLoadingMsgIndex(0);
    generateReport.mutate({
      industry: formData.industry,
      country: formData.country,
      companySize: formData.companySize,
      email: formData.email,
      companyName: formData.companyName || undefined,
    });
  };

  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/report?utm_source=share&utm_medium=social`
    : "";

  const handleCopyLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    toast.success("Link copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = (platform: string) => {
    const text = `I just got my personalized Iran War business impact report. Find out how the crisis affects YOUR business:`;
    const urls: Record<string, string> = {
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`,
      twitter: `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(shareUrl)}`,
      email: `mailto:?subject=${encodeURIComponent("War Impact Report - How the Iran War Affects Your Business")}&body=${encodeURIComponent(`${text}\n\n${shareUrl}`)}`,
    };
    if (urls[platform]) window.open(urls[platform], "_blank");
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <AnimatePresence mode="wait">
          {/* FORM PHASE */}
          {phase === "form" && (
            <motion.div
              key="form"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <div className="text-center mb-10">
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-crisis-red/10 border border-crisis-red/30 mb-4">
                  <span className="w-2 h-2 rounded-full bg-crisis-red pulse-dot" />
                  <span className="font-mono text-xs text-crisis-red tracking-wider uppercase">
                    INTELLIGENCE BRIEFING
                  </span>
                </div>
                <h1 className="text-3xl sm:text-4xl font-bold mb-3">
                  Get Your Personalized Impact Report
                </h1>
                <p className="text-muted-foreground max-w-xl mx-auto">
                  Enter your business details below. Our AI will analyze how the Iran War and Hormuz crisis specifically affect your operations.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="max-w-xl mx-auto space-y-5">
                {/* Honeypot - hidden from users */}
                <input
                  type="text"
                  name="website"
                  value={formData.honeypot}
                  onChange={(e) => setFormData({ ...formData, honeypot: e.target.value })}
                  className="absolute -left-[9999px] opacity-0"
                  tabIndex={-1}
                  autoComplete="off"
                />

                {/* Industry */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">
                    Industry *
                  </label>
                  <select
                    value={formData.industry}
                    onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                    className="w-full bg-card border border-border/50 rounded-lg px-4 py-3 text-sm text-foreground focus:border-crisis-red focus:ring-1 focus:ring-crisis-red/50 transition-colors appearance-none"
                  >
                    <option value="">Select your industry</option>
                    {INDUSTRIES.map((ind) => (
                      <option key={ind} value={ind}>{ind}</option>
                    ))}
                  </select>
                  {errors.industry && <p className="text-crisis-red text-xs mt-1">{errors.industry}</p>}
                </motion.div>

                {/* Country */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">
                    Country *
                  </label>
                  <select
                    value={formData.country}
                    onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                    className="w-full bg-card border border-border/50 rounded-lg px-4 py-3 text-sm text-foreground focus:border-crisis-red focus:ring-1 focus:ring-crisis-red/50 transition-colors appearance-none"
                  >
                    <option value="">Select your country</option>
                    {COUNTRIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  {errors.country && <p className="text-crisis-red text-xs mt-1">{errors.country}</p>}
                </motion.div>

                {/* Company Size */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">
                    Company Size *
                  </label>
                  <select
                    value={formData.companySize}
                    onChange={(e) => setFormData({ ...formData, companySize: e.target.value })}
                    className="w-full bg-card border border-border/50 rounded-lg px-4 py-3 text-sm text-foreground focus:border-crisis-red focus:ring-1 focus:ring-crisis-red/50 transition-colors appearance-none"
                  >
                    <option value="">Select company size</option>
                    {COMPANY_SIZES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  {errors.companySize && <p className="text-crisis-red text-xs mt-1">{errors.companySize}</p>}
                </motion.div>

                {/* Email */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">
                    Business Email *
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="you@company.com"
                    className="w-full bg-card border border-border/50 rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-crisis-red focus:ring-1 focus:ring-crisis-red/50 transition-colors"
                  />
                  {errors.email && <p className="text-crisis-red text-xs mt-1">{errors.email}</p>}
                </motion.div>

                {/* Company Name (optional) */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 }}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">
                    Company Name <span className="text-muted-foreground/50">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={formData.companyName}
                    onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                    placeholder="Your Company"
                    className="w-full bg-card border border-border/50 rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-crisis-red focus:ring-1 focus:ring-crisis-red/50 transition-colors"
                  />
                </motion.div>

                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
                  <button
                    type="submit"
                    disabled={generateReport.isPending}
                    className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all cta-pulse disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Shield className="w-5 h-5" />
                    Generate My Impact Report
                    <ArrowRight className="w-4 h-4" />
                  </button>
                  <p className="text-center text-xs text-muted-foreground mt-3">
                    Free summary report. No credit card required. Full report available for $49.
                  </p>
                </motion.div>
              </form>
            </motion.div>
          )}

          {/* LOADING PHASE */}
          {phase === "loading" && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center py-24"
            >
              {/* Radar animation */}
              <div className="relative w-32 h-32 mb-8">
                <div className="absolute inset-0 rounded-full border-2 border-crisis-red/20" />
                <div className="absolute inset-3 rounded-full border border-crisis-red/15" />
                <div className="absolute inset-6 rounded-full border border-crisis-red/10" />
                <div className="absolute inset-0 rounded-full radar-ping border-2 border-crisis-red/30" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-3 h-3 rounded-full bg-crisis-red pulse-dot" />
                </div>
                <div className="absolute inset-0 origin-center radar-sweep">
                  <div className="absolute top-1/2 left-1/2 w-1/2 h-0.5 bg-gradient-to-r from-crisis-red/60 to-transparent origin-left" />
                </div>
              </div>

              <h2 className="font-mono text-lg font-semibold mb-2 text-center">
                GENERATING INTELLIGENCE REPORT
              </h2>
              <p className="text-sm text-muted-foreground mb-6 text-center">
                Analyzing impact for <span className="text-crisis-gold font-semibold">{formData.industry}</span> in{" "}
                <span className="text-crisis-gold font-semibold">{formData.country}</span>
              </p>

              <AnimatePresence mode="wait">
                <motion.p
                  key={loadingMsgIndex}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="font-mono text-xs text-crisis-red tracking-wider"
                >
                  {LOADING_MESSAGES[loadingMsgIndex]}
                </motion.p>
              </AnimatePresence>
            </motion.div>
          )}

          {/* RESULT PHASE */}
          {phase === "result" && report && (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
            >
              {/* Report Header */}
              <div className="bg-card border border-border/50 rounded-xl overflow-hidden mb-6">
                <div className="bg-gradient-to-r from-crisis-red/10 to-transparent p-6 border-b border-border/30">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <Shield className="w-6 h-6 text-crisis-red" />
                      <div>
                        <h2 className="font-mono text-sm font-semibold tracking-wider uppercase">
                          IMPACT ASSESSMENT
                        </h2>
                        <p className="text-xs text-muted-foreground">
                          {formData.industry} — {formData.country} — {formData.companySize}
                        </p>
                      </div>
                    </div>
                    <span className={`font-mono text-xs font-bold px-3 py-1 rounded ${RISK_COLORS[report.riskLevel] || RISK_COLORS.HIGH}`}>
                      {report.riskLevel} RISK
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> Generated in {(report.generationTimeMs / 1000).toFixed(1)}s</span>
                    <span className="flex items-center gap-1"><Zap className="w-3 h-3" /> AI-powered analysis</span>
                    {report.cached && <span className="flex items-center gap-1 text-crisis-gold">Cached result</span>}
                  </div>
                </div>

                <div className="p-6">
                  <div className="prose prose-invert prose-sm max-w-none">
                    <div className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
                      {report.content}
                    </div>
                  </div>
                </div>

                <div className="px-6 py-3 border-t border-border/30 flex items-center gap-4 text-xs text-muted-foreground">
                  <span>Sources: EIA, IMF, Bloomberg, Reuters, IATA, Clarksons Research</span>
                </div>
              </div>

              {/* Upsell Box */}
              <div className="bg-gradient-to-r from-crisis-red/5 to-crisis-gold/5 border-2 border-crisis-red/30 rounded-xl p-6 mb-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-crisis-red/10 flex items-center justify-center shrink-0">
                    <FileText className="w-6 h-6 text-crisis-red" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-bold mb-1">Unlock the Full Intelligence Report</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Get the complete 8-section analysis with alternative suppliers, 90-day cost projections, weekly action plans, and opportunity identification.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-3">
                      <button
                        onClick={() => {
                          toast("Feature coming soon", { description: "Stripe payment integration will be available shortly." });
                        }}
                        className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all cta-pulse text-sm"
                      >
                        Get Full Report — $49
                        <ArrowRight className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          toast("Feature coming soon", { description: "Subscription will be available shortly." });
                        }}
                        className="inline-flex items-center justify-center gap-2 px-5 py-2.5 border border-crisis-blue text-crisis-blue font-semibold rounded-lg hover:bg-crisis-blue/10 transition-all text-sm"
                      >
                        Subscribe for Weekly Updates — $19/mo
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Share */}
              <div className="bg-card border border-border/50 rounded-xl p-5">
                <h4 className="font-mono text-xs text-muted-foreground tracking-widest uppercase mb-3">
                  SHARE THIS REPORT
                </h4>
                <div className="flex items-center gap-3">
                  <button onClick={() => handleShare("linkedin")} className="p-2.5 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors" aria-label="Share on LinkedIn">
                    <Linkedin className="w-4 h-4" />
                  </button>
                  <button onClick={() => handleShare("twitter")} className="p-2.5 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors" aria-label="Share on X">
                    <Twitter className="w-4 h-4" />
                  </button>
                  <button onClick={() => handleShare("email")} className="p-2.5 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors" aria-label="Share via Email">
                    <Mail className="w-4 h-4" />
                  </button>
                  <button onClick={handleCopyLink} className="p-2.5 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors" aria-label="Copy link">
                    {copied ? <Check className="w-4 h-4 text-crisis-green" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <Footer />
    </div>
  );
}
