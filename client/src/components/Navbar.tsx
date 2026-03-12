import { Link, useLocation } from "wouter";
import { useState, useEffect } from "react";
import { Menu, X, Shield, AlertTriangle } from "lucide-react";

function getDayCount(): number {
  const warStart = new Date("2026-03-02");
  const now = new Date();
  return Math.max(1, Math.ceil((now.getTime() - warStart.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function Navbar() {
  const [location] = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dayCount, setDayCount] = useState(getDayCount());

  useEffect(() => {
    const interval = setInterval(() => setDayCount(getDayCount()), 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      {/* Crisis Bar */}
      <div className="w-full bg-crisis-red/10 border-b border-crisis-red/30 py-1.5 px-4 font-mono text-xs">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-crisis-red pulse-dot" />
            <span className="text-crisis-red font-semibold tracking-wider uppercase">
              LIVE — Day {dayCount} of the Iran War
            </span>
          </div>
          <div className="hidden md:flex items-center gap-6 text-muted-foreground">
            <span>Strait of Hormuz: <span className="text-crisis-red font-semibold">CLOSED</span></span>
            <span>Brent Crude: <span className="text-crisis-gold font-semibold">$110+/bbl</span></span>
            <span>GCC GDP: <span className="text-crisis-red font-semibold">-1.8pts</span></span>
          </div>
        </div>
      </div>

      {/* Main Nav */}
      <nav className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded bg-crisis-red/20 flex items-center justify-center">
                <Shield className="w-5 h-5 text-crisis-red" />
              </div>
              <div className="flex flex-col">
                <span className="font-mono text-sm font-bold tracking-tight text-foreground">
                  WAR IMPACT
                </span>
                <span className="font-mono text-[10px] text-muted-foreground tracking-widest uppercase">
                  REPORT
                </span>
              </div>
            </Link>

            {/* Desktop links */}
            <div className="hidden md:flex items-center gap-6">
              <Link href="/#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                Pricing
              </Link>
              <Link href="/blog" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                Blog
              </Link>
              <Link href="/report" className="inline-flex items-center gap-2 px-4 py-2 bg-crisis-red text-white text-sm font-semibold rounded-md hover:bg-crisis-red/90 transition-colors cta-pulse">
                <AlertTriangle className="w-4 h-4" />
                Get Your Report
              </Link>
            </div>

            {/* Mobile menu button */}
            <button
              className="md:hidden p-2 text-muted-foreground"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle menu"
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="md:hidden border-t border-border/50 bg-background/95 backdrop-blur-xl">
            <div className="px-4 py-4 space-y-3">
              <Link href="/#pricing" onClick={() => setMobileOpen(false)} className="block text-sm text-muted-foreground hover:text-foreground">
                Pricing
              </Link>
              <Link href="/blog" onClick={() => setMobileOpen(false)} className="block text-sm text-muted-foreground hover:text-foreground">
                Blog
              </Link>
              <Link href="/report" onClick={() => setMobileOpen(false)} className="block w-full text-center px-4 py-2 bg-crisis-red text-white text-sm font-semibold rounded-md">
                Get Your Report
              </Link>
            </div>
          </div>
        )}
      </nav>
    </>
  );
}
