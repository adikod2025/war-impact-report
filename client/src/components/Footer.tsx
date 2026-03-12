import { Link } from "wouter";
import { Shield } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-border/50 bg-[#070A10]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="md:col-span-1">
            <div className="flex items-center gap-2.5 mb-4">
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
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              AI-powered business impact assessments for the 2026 Iran War and Strait of Hormuz crisis.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="font-mono text-xs font-semibold tracking-widest uppercase text-muted-foreground mb-4">
              Product
            </h4>
            <ul className="space-y-2.5">
              <li>
                <Link href="/report" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Free Report
                </Link>
              </li>
              <li>
                <Link href="/#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Full Report ($49)
                </Link>
              </li>
              <li>
                <Link href="/#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Weekly Updates ($19/mo)
                </Link>
              </li>
            </ul>
          </div>

          {/* Resources */}
          <div>
            <h4 className="font-mono text-xs font-semibold tracking-widest uppercase text-muted-foreground mb-4">
              Resources
            </h4>
            <ul className="space-y-2.5">
              <li>
                <Link href="/blog" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Blog
                </Link>
              </li>
              <li>
                <Link href="/blog/hormuz-closure-impact" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Hormuz Analysis
                </Link>
              </li>
              <li>
                <Link href="/blog/supply-chain-alternatives" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Supply Chain Guide
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="font-mono text-xs font-semibold tracking-widest uppercase text-muted-foreground mb-4">
              Legal
            </h4>
            <ul className="space-y-2.5">
              <li>
                <Link href="/privacy" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-border/30">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-xs text-muted-foreground">
              &copy; {new Date().getFullYear()} War Impact Report. All rights reserved.
            </p>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>Data sources: EIA, IMF, Bloomberg, Reuters, IATA, Clarksons Research</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
