import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Link } from "wouter";
import { ArrowRight, Clock, AlertTriangle } from "lucide-react";
import { motion } from "framer-motion";

const BLOG_POSTS = [
  {
    slug: "hormuz-closure-impact",
    title: "The Strait of Hormuz Closure: What It Means for Global Trade",
    excerpt: "21% of global oil transits through the Strait of Hormuz. With the IRGC confirming closure on March 2, 2026, we analyze the cascading effects on every major industry.",
    date: "March 8, 2026",
    readTime: "8 min read",
    category: "ANALYSIS",
    categoryColor: "text-crisis-red",
  },
  {
    slug: "supply-chain-alternatives",
    title: "Alternative Supply Routes: Navigating Around the Hormuz Blockade",
    excerpt: "From the Cape of Good Hope to the Trans-Arabian Pipeline, we map every alternative route and supplier for businesses dependent on Gulf trade.",
    date: "March 6, 2026",
    readTime: "12 min read",
    category: "STRATEGY",
    categoryColor: "text-crisis-blue",
  },
  {
    slug: "oil-price-forecast-2026",
    title: "Oil Price Forecast: Where Is Brent Crude Heading in Q2 2026?",
    excerpt: "With Brent crude at $110+/barrel and futures markets pricing in a prolonged conflict, we analyze three scenarios for oil prices through Q2 2026.",
    date: "March 5, 2026",
    readTime: "6 min read",
    category: "FORECAST",
    categoryColor: "text-crisis-gold",
  },
  {
    slug: "gcc-economic-impact",
    title: "GCC Economic Impact: $40B Tourism Loss and Revised GDP Forecasts",
    excerpt: "The IMF has revised GCC GDP growth from 4.4% to 2.6%. We break down the sector-by-sector impact across Saudi Arabia, UAE, Qatar, and the wider Gulf.",
    date: "March 4, 2026",
    readTime: "10 min read",
    category: "ECONOMICS",
    categoryColor: "text-crisis-green",
  },
];

export default function BlogPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-crisis-red/10 border border-crisis-red/30 mb-4">
            <span className="w-2 h-2 rounded-full bg-crisis-red pulse-dot" />
            <span className="font-mono text-xs text-crisis-red tracking-wider uppercase">
              INTELLIGENCE BRIEFINGS
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold mb-3">Crisis Analysis Blog</h1>
          <p className="text-muted-foreground max-w-2xl">
            In-depth analysis, forecasts, and strategic guidance for businesses navigating the 2026 Iran War and Strait of Hormuz crisis.
          </p>
        </div>

        <div className="space-y-6">
          {BLOG_POSTS.map((post, i) => (
            <motion.div
              key={post.slug}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.1 }}
            >
              <Link href={`/blog/${post.slug}`}>
                <div className="bg-card border border-border/50 rounded-xl p-6 hover:border-crisis-red/30 transition-all group cursor-pointer">
                  <div className="flex items-center gap-3 mb-3">
                    <span className={`font-mono text-[10px] font-bold tracking-widest ${post.categoryColor}`}>
                      {post.category}
                    </span>
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {post.readTime}
                    </span>
                    <span className="text-xs text-muted-foreground">{post.date}</span>
                  </div>
                  <h2 className="text-xl font-semibold mb-2 group-hover:text-crisis-red transition-colors">
                    {post.title}
                  </h2>
                  <p className="text-sm text-muted-foreground leading-relaxed mb-3">
                    {post.excerpt}
                  </p>
                  <span className="inline-flex items-center gap-1 text-sm text-crisis-red font-medium">
                    Read Analysis <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
                  </span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-12 bg-gradient-to-r from-crisis-red/5 to-transparent border border-crisis-red/20 rounded-xl p-6 text-center">
          <h3 className="text-xl font-bold mb-2">Get Your Personalized Impact Report</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Don't just read the news — understand exactly how this crisis affects YOUR business.
          </p>
          <Link
            href="/report"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all cta-pulse text-sm"
          >
            <AlertTriangle className="w-4 h-4" />
            Get Your Free Report
          </Link>
        </div>
      </div>

      <Footer />
    </div>
  );
}
