import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { useScrollReveal } from "@/hooks/useScrollReveal";
import { Link } from "wouter";
import {
  AlertTriangle, Fuel, Ship, Plane, Building2, TrendingUp,
  Shield, Clock, FileText, Zap, Check, ArrowRight,
  BarChart3, Globe, Factory, DollarSign
} from "lucide-react";
import { motion } from "framer-motion";

const HERO_BG = "https://d2xsxph8kpxj0f.cloudfront.net/116323800/YrVH2K4ApAZfrHCczfvwbD/hero-bg-EgZP73Mk3C7hctCHV7yeCu.webp";

const crisisCards = [
  { label: "Brent Crude", value: "$110+/bbl", change: "+37%", icon: Fuel, color: "text-crisis-gold" },
  { label: "Hormuz Traffic", value: "CLOSED", change: "-100%", icon: Ship, color: "text-crisis-red" },
  { label: "Jet Fuel", value: "$4.12/gal", change: "+68%", icon: Plane, color: "text-crisis-gold" },
  { label: "GCC GDP Forecast", value: "2.6%", change: "-1.8pts", icon: TrendingUp, color: "text-crisis-red" },
];

const disruptions = [
  { sector: "Oil & Gas", severity: "CRITICAL", desc: "Strait of Hormuz closed. 21% of global oil transit halted. Brent crude +37%.", color: "bg-crisis-red" },
  { sector: "Shipping & Logistics", severity: "CRITICAL", desc: "Maersk, CMA CGM, Hapag-Lloyd suspended all Hormuz AND Red Sea transits.", color: "bg-crisis-red" },
  { sector: "Aviation", severity: "HIGH", desc: "Middle East airspace largely closed. Dubai Airport struck. Rerouting adds 2+ hours.", color: "bg-crisis-gold" },
  { sector: "Manufacturing", severity: "HIGH", desc: "Sulfur (45% Gulf share), Helium (40% Qatar), LNG (20% Hormuz) supply disrupted.", color: "bg-crisis-gold" },
  { sector: "Agriculture", severity: "HIGH", desc: "16% of global fertilizer transits through Hormuz. Prices surging.", color: "bg-crisis-gold" },
  { sector: "Tourism", severity: "HIGH", desc: "GCC tourism losses estimated at $40B. Dubai, Doha, Riyadh events cancelled.", color: "bg-crisis-gold" },
];

const steps = [
  { num: "01", title: "Enter Your Details", desc: "Industry, country, and company size. Takes 30 seconds.", icon: FileText },
  { num: "02", title: "AI Analyzes Impact", desc: "Our AI cross-references your profile against real-time crisis data.", icon: Zap },
  { num: "03", title: "Get Your Report", desc: "Receive a personalized risk assessment with actionable recommendations.", icon: Shield },
];

export default function Home() {
  const scrollRef = useScrollReveal();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      {/* Hero Section */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center opacity-20"
          style={{ backgroundImage: `url(${HERO_BG})` }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/60 via-background/80 to-background" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-24 sm:pt-28 sm:pb-32">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="max-w-3xl"
          >
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-crisis-red/10 border border-crisis-red/30 mb-6">
              <span className="w-2 h-2 rounded-full bg-crisis-red pulse-dot" />
              <span className="font-mono text-xs text-crisis-red tracking-wider uppercase">
                SITUATION REPORT — MARCH 2026
              </span>
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.1] mb-6">
              How Does the Iran War{" "}
              <span className="text-crisis-red">Affect Your Business?</span>
            </h1>
            <p className="text-lg sm:text-xl text-muted-foreground leading-relaxed mb-8 max-w-2xl">
              Get an AI-powered personalized impact assessment in 30 seconds. Understand your risk exposure, supply chain vulnerabilities, and receive an actionable crisis response plan.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <Link
                href="/report"
                className="inline-flex items-center justify-center gap-2 px-6 py-3.5 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all cta-pulse text-base"
              >
                <AlertTriangle className="w-5 h-5" />
                Get Your Free Report
                <ArrowRight className="w-4 h-4" />
              </Link>
              <a
                href="#pricing"
                className="inline-flex items-center justify-center gap-2 px-6 py-3.5 bg-secondary text-secondary-foreground font-semibold rounded-lg hover:bg-secondary/80 transition-all text-base border border-border/50"
              >
                View Pricing
              </a>
            </div>
            <div className="mt-8 flex items-center gap-6 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5"><Check className="w-4 h-4 text-crisis-green" /> Free summary report</span>
              <span className="flex items-center gap-1.5"><Check className="w-4 h-4 text-crisis-green" /> No credit card required</span>
              <span className="flex items-center gap-1.5"><Clock className="w-4 h-4 text-crisis-green" /> 30-second analysis</span>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Crisis Dashboard */}
      <section className="py-16 border-t border-border/30" ref={scrollRef}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-8">
            <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">
              SECTION 01 //
            </span>
            <span className="font-mono text-xs text-crisis-red tracking-widest uppercase font-semibold">
              LIVE CRISIS DATA
            </span>
            <div className="flex-1 h-px bg-border/30" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {crisisCards.map((card, i) => (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                className="bg-card border border-border/50 rounded-lg p-5 hover:border-crisis-red/30 transition-colors"
              >
                <div className="flex items-center justify-between mb-3">
                  <card.icon className={`w-5 h-5 ${card.color}`} />
                  <span className={`font-mono text-xs font-semibold ${card.color}`}>
                    {card.change}
                  </span>
                </div>
                <p className="font-mono text-2xl font-bold text-foreground mb-1">{card.value}</p>
                <p className="text-xs text-muted-foreground">{card.label}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* What's Disrupted */}
      <section className="py-16 bg-card/30 border-t border-border/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-8">
            <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">
              SECTION 02 //
            </span>
            <span className="font-mono text-xs text-crisis-gold tracking-widest uppercase font-semibold">
              DISRUPTION MAP
            </span>
            <div className="flex-1 h-px bg-border/30" />
          </div>

          <h2 className="text-3xl font-bold mb-2">What's Being Disrupted</h2>
          <p className="text-muted-foreground mb-8 max-w-2xl">
            The Iran War and Strait of Hormuz closure are creating cascading disruptions across every major sector.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {disruptions.map((d, i) => (
              <motion.div
                key={d.sector}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.08 }}
                className="bg-card border border-border/50 rounded-lg p-5 hover:border-border transition-colors"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-mono text-sm font-semibold">{d.sector}</h3>
                  <span className={`${d.color} text-[10px] font-mono font-bold px-2 py-0.5 rounded text-white`}>
                    {d.severity}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">{d.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-16 border-t border-border/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-8">
            <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">
              SECTION 03 //
            </span>
            <span className="font-mono text-xs text-crisis-blue tracking-widest uppercase font-semibold">
              PROCESS
            </span>
            <div className="flex-1 h-px bg-border/30" />
          </div>

          <h2 className="text-3xl font-bold mb-2">How It Works</h2>
          <p className="text-muted-foreground mb-12 max-w-2xl">
            Three steps to understand your exposure and build a crisis response plan.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {steps.map((step, i) => (
              <motion.div
                key={step.num}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.15 }}
                className="relative"
              >
                <div className="font-mono text-5xl font-bold text-border/30 mb-4">{step.num}</div>
                <div className="w-12 h-12 rounded-lg bg-crisis-blue/10 flex items-center justify-center mb-4">
                  <step.icon className="w-6 h-6 text-crisis-blue" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{step.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-16 bg-card/30 border-t border-border/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-8">
            <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">
              SECTION 04 //
            </span>
            <span className="font-mono text-xs text-crisis-green tracking-widest uppercase font-semibold">
              PRICING
            </span>
            <div className="flex-1 h-px bg-border/30" />
          </div>

          <h2 className="text-3xl font-bold mb-2">Choose Your Intelligence Level</h2>
          <p className="text-muted-foreground mb-12 max-w-2xl">
            From a quick risk snapshot to ongoing strategic intelligence — pick the plan that matches your exposure.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {/* Free */}
            <div className="bg-card border border-border/50 rounded-xl p-6 flex flex-col">
              <div className="font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">FREE</div>
              <div className="text-3xl font-bold mb-1">$0</div>
              <p className="text-sm text-muted-foreground mb-6">Quick risk snapshot</p>
              <ul className="space-y-3 mb-8 flex-1">
                {["Risk level assessment", "8-10 sentence summary", "One key action item", "90-day outlook"].map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <Check className="w-4 h-4 text-crisis-green mt-0.5 shrink-0" />
                    <span className="text-muted-foreground">{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href="/report"
                className="w-full text-center py-2.5 rounded-lg border border-border text-sm font-semibold hover:bg-secondary transition-colors"
              >
                Get Free Report
              </Link>
            </div>

            {/* Full Report - Featured */}
            <div className="bg-card border-2 border-crisis-red rounded-xl p-6 flex flex-col relative">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-crisis-red text-white text-xs font-mono font-bold rounded-full">
                MOST POPULAR
              </div>
              <div className="font-mono text-xs text-crisis-red tracking-widest uppercase mb-2">FULL REPORT</div>
              <div className="text-3xl font-bold mb-1">$49</div>
              <p className="text-sm text-muted-foreground mb-6">One-time purchase</p>
              <ul className="space-y-3 mb-8 flex-1">
                {[
                  "Everything in Free",
                  "8-section deep analysis",
                  "Alternative suppliers list",
                  "90-day cost projections",
                  "Weekly action plan",
                  "Opportunity identification",
                  "PDF download",
                ].map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <Check className="w-4 h-4 text-crisis-green mt-0.5 shrink-0" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href="/report"
                className="w-full text-center py-2.5 rounded-lg bg-crisis-red text-white text-sm font-semibold hover:bg-crisis-red/90 transition-colors cta-pulse"
              >
                Get Full Report — $49
              </Link>
            </div>

            {/* Subscription */}
            <div className="bg-card border border-border/50 rounded-xl p-6 flex flex-col">
              <div className="font-mono text-xs text-crisis-blue tracking-widest uppercase mb-2">WEEKLY UPDATES</div>
              <div className="text-3xl font-bold mb-1">$19<span className="text-lg text-muted-foreground font-normal">/mo</span></div>
              <p className="text-sm text-muted-foreground mb-6">Ongoing intelligence</p>
              <ul className="space-y-3 mb-8 flex-1">
                {[
                  "Everything in Full Report",
                  "Weekly updated reports",
                  "New data as conflict evolves",
                  "Updated supplier alternatives",
                  "Revised cost projections",
                  "Priority email support",
                  "Cancel anytime",
                ].map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <Check className="w-4 h-4 text-crisis-green mt-0.5 shrink-0" />
                    <span className="text-muted-foreground">{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href="/report"
                className="w-full text-center py-2.5 rounded-lg border border-crisis-blue text-crisis-blue text-sm font-semibold hover:bg-crisis-blue/10 transition-colors"
              >
                Subscribe — $19/mo
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Social Proof / Data Sources */}
      <section className="py-16 border-t border-border/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-8">
            <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">
              SECTION 05 //
            </span>
            <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase font-semibold">
              DATA SOURCES
            </span>
            <div className="flex-1 h-px bg-border/30" />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-6">
            {[
              { name: "EIA", icon: BarChart3 },
              { name: "IMF", icon: Globe },
              { name: "Bloomberg", icon: TrendingUp },
              { name: "Reuters", icon: FileText },
              { name: "IATA", icon: Plane },
              { name: "Clarksons", icon: Ship },
            ].map((source) => (
              <div key={source.name} className="flex flex-col items-center gap-2 py-4 px-2 rounded-lg bg-card/50 border border-border/30">
                <source.icon className="w-6 h-6 text-muted-foreground" />
                <span className="font-mono text-xs text-muted-foreground">{source.name}</span>
              </div>
            ))}
          </div>

          <div className="mt-12 text-center">
            <p className="text-muted-foreground mb-6 max-w-xl mx-auto">
              Our AI analyzes data from 6+ authoritative sources to generate your personalized business impact assessment.
            </p>
            <Link
              href="/report"
              className="inline-flex items-center gap-2 px-6 py-3 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all cta-pulse"
            >
              <AlertTriangle className="w-5 h-5" />
              Get Your Free Report Now
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
