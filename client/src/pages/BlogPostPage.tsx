import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Link, useParams } from "wouter";
import { ArrowLeft, Clock, AlertTriangle } from "lucide-react";
import { Streamdown } from "streamdown";

const BLOG_CONTENT: Record<string, { title: string; date: string; readTime: string; category: string; content: string }> = {
  "hormuz-closure-impact": {
    title: "The Strait of Hormuz Closure: What It Means for Global Trade",
    date: "March 8, 2026",
    readTime: "8 min read",
    category: "ANALYSIS",
    content: `## The Strategic Chokepoint

The Strait of Hormuz, a narrow waterway between Iran and Oman, has been the world's most critical oil transit chokepoint for decades. Approximately **21% of global petroleum liquids** and **20% of global LNG** transited through this 21-mile-wide passage before the closure.

On March 2, 2026, the Islamic Revolutionary Guard Corps (IRGC) officially confirmed the closure of the Strait following the outbreak of hostilities. Within 72 hours, war-risk insurance was pulled by all major underwriters, effectively making commercial transit impossible even before physical blockade measures were fully in place.

## Immediate Market Impact

The closure triggered immediate and severe market reactions:

- **Brent Crude** surged from approximately $80/barrel to over $110/barrel — a 37% increase in under two weeks
- **Jet fuel** prices spiked to $4.12/gallon, a 68% increase that is already forcing airlines to implement emergency fuel surcharges
- **LNG spot prices** in Asia jumped 45% as Qatar's massive LNG export capacity was effectively landlocked
- **Shipping insurance** premiums for the Persian Gulf region increased by 500-800%

## Supply Chain Cascading Effects

The impact extends far beyond oil. The Strait of Hormuz is a critical transit point for:

- **45% of global sulfur exports** (essential for fertilizers, chemicals, and mining)
- **40% of global helium** (Qatar is the world's second-largest producer)
- **16% of global fertilizer** trade
- **Significant petrochemical feedstock** flows to Asia and Europe

Major shipping lines including Maersk, CMA CGM, and Hapag-Lloyd have suspended not only Hormuz transits but also Red Sea passages, citing the expanded threat environment. Rerouting via the Cape of Good Hope adds 2-4 weeks to delivery times and significantly increases fuel costs.

## What Businesses Should Do Now

1. **Audit your supply chain** for any direct or indirect Gulf dependency
2. **Identify alternative suppliers** outside the conflict zone
3. **Review contracts** for force majeure clauses
4. **Build inventory buffers** for critical inputs
5. **Monitor futures markets** for hedging opportunities

The situation remains fluid, and businesses that act decisively now will be better positioned regardless of how the conflict evolves.`,
  },
  "supply-chain-alternatives": {
    title: "Alternative Supply Routes: Navigating Around the Hormuz Blockade",
    date: "March 6, 2026",
    readTime: "12 min read",
    category: "STRATEGY",
    content: `## The Rerouting Challenge

With the Strait of Hormuz closed and Red Sea transits suspended by major carriers, global supply chains face their most significant disruption since World War II. This analysis maps the available alternatives and their implications for businesses.

## Alternative Oil Routes

### Trans-Arabian Pipeline (Petroline)
Saudi Arabia's East-West pipeline can transport approximately **5 million barrels per day** from the Eastern Province to Yanbu on the Red Sea coast. However, this capacity is already being maximized, and Red Sea security concerns limit its effectiveness.

### UAE's Habshan-Fujairah Pipeline
The Abu Dhabi Crude Oil Pipeline bypasses the Strait entirely, connecting Abu Dhabi's oil fields to the port of Fujairah on the Gulf of Oman. Capacity: **1.5 million bbl/day**. This is currently the most viable bypass route.

### Iraqi Northern Route
Iraq's Kirkuk-Ceyhan pipeline to Turkey offers an alternative for Iraqi crude, with capacity of approximately **900,000 bbl/day**. However, this route has its own security considerations.

## Shipping Alternatives

The Cape of Good Hope route adds:
- **2-4 weeks** to Asia-Europe transit times
- **$1-2 million** in additional fuel costs per voyage for large tankers
- Significant port congestion at alternative hubs

## Recommendations

Businesses should diversify suppliers across multiple regions, build strategic inventory reserves, and explore nearshoring options where feasible. The crisis is accelerating trends toward supply chain regionalization that were already underway.`,
  },
  "oil-price-forecast-2026": {
    title: "Oil Price Forecast: Where Is Brent Crude Heading in Q2 2026?",
    date: "March 5, 2026",
    readTime: "6 min read",
    category: "FORECAST",
    content: `## Current Situation

Brent crude has surged past $110/barrel following the Strait of Hormuz closure, representing a 37% increase from pre-conflict levels of approximately $80/barrel. The question now is: where do prices go from here?

## Three Scenarios

### Scenario 1: Prolonged Closure (Base Case — 50% probability)
If the Strait remains closed through Q2 2026, Brent crude is likely to stabilize in the **$105-$120 range**. Strategic petroleum reserve releases and demand destruction will partially offset supply losses, but the fundamental supply gap of 6.7 million bbl/day from GCC production disruption cannot be fully compensated.

### Scenario 2: Escalation (25% probability)
If the conflict expands to include direct strikes on Saudi or UAE oil infrastructure, prices could spike to **$130-$150/barrel**. This scenario would trigger a global recession and significant demand destruction.

### Scenario 3: De-escalation (25% probability)
A ceasefire or partial reopening of the Strait could see prices retreat to **$85-$95/barrel** within weeks. However, a full return to pre-conflict levels is unlikely given persistent risk premiums.

## Implications for Businesses

At current prices, energy-intensive industries face margin compression of 15-30%. Businesses should:
- Lock in fuel contracts where possible
- Accelerate energy efficiency investments
- Review pricing strategies to pass through unavoidable cost increases
- Monitor futures markets for hedging opportunities`,
  },
  "gcc-economic-impact": {
    title: "GCC Economic Impact: $40B Tourism Loss and Revised GDP Forecasts",
    date: "March 4, 2026",
    readTime: "10 min read",
    category: "ECONOMICS",
    content: `## Revised Forecasts

The IMF has revised its GCC GDP growth forecast from **4.4% to 2.6%** — a 1.8 percentage point reduction that translates to approximately **$80 billion in lost economic output** across the six Gulf states.

## Tourism Devastation

The GCC tourism sector, which had been a cornerstone of economic diversification strategies, has been devastated:

- **Estimated losses: $40 billion** in the first quarter alone
- Dubai Airport, the world's busiest international hub, was struck in the initial attacks
- Emirates has only partially resumed operations with significant route restrictions
- Major events including Expo follow-ups, Formula 1, and cultural festivals have been cancelled
- Hotel occupancy rates across the GCC have dropped below 20%

## Sector-by-Sector Impact

### Saudi Arabia
Vision 2030 projects face significant delays. The NEOM megaproject and Red Sea tourism development are particularly affected. Oil revenue is paradoxically higher due to price spikes, but export volumes are constrained.

### UAE
Dubai's position as a global business hub is under severe stress. Free zone activity has declined sharply, and real estate markets are seeing rapid price corrections in prime areas.

### Qatar
As the world's largest LNG exporter, Qatar faces the most direct impact from the Hormuz closure. LNG export revenues have effectively ceased, though long-term contracts provide some financial buffer.

## Recovery Timeline

Historical precedents suggest that even after conflict resolution, full economic recovery for the GCC region could take **18-24 months**. Businesses with GCC exposure should plan for a prolonged disruption period.`,
  },
};

export default function BlogPostPage() {
  const params = useParams<{ slug: string }>();
  const post = BLOG_CONTENT[params.slug || ""];

  if (!post) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <div className="max-w-4xl mx-auto px-4 py-24 text-center">
          <h1 className="text-2xl font-bold mb-3">Article Not Found</h1>
          <p className="text-muted-foreground mb-6">The article you're looking for doesn't exist.</p>
          <Link href="/blog" className="text-crisis-red hover:underline">Back to Blog</Link>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      <article className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <Link href="/blog" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Blog
        </Link>

        <div className="mb-8">
          <span className="font-mono text-xs text-crisis-red tracking-widest uppercase font-semibold">
            {post.category}
          </span>
          <h1 className="text-3xl sm:text-4xl font-bold mt-2 mb-4">{post.title}</h1>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>{post.date}</span>
            <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {post.readTime}</span>
          </div>
        </div>

        <div className="prose prose-invert prose-sm max-w-none mb-12">
          <Streamdown>{post.content}</Streamdown>
        </div>

        {/* CTA */}
        <div className="bg-gradient-to-r from-crisis-red/5 to-transparent border border-crisis-red/20 rounded-xl p-6 text-center">
          <h3 className="text-xl font-bold mb-2">How Does This Affect YOUR Business?</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Get a personalized impact assessment for your specific industry, country, and company size.
          </p>
          <Link
            href="/report"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all text-sm"
          >
            <AlertTriangle className="w-4 h-4" />
            Get Your Free Report
          </Link>
        </div>
      </article>

      <Footer />
    </div>
  );
}
