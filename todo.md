# War Impact Report — TODO

## Core Infrastructure
- [x] Dark theme CSS configuration with spec colors
- [x] Google Fonts: JetBrains Mono + Inter
- [x] Database schema: users, reports, payments, subscriptions, crisis_data tables
- [x] Crisis data seeding with spec values

## Landing Page (/)
- [x] Live crisis bar with pulsing red dot + "LIVE — Day X of the Iran War"
- [x] Hero section with headline, subheadline, CTA
- [x] Live Crisis Data Dashboard (4-column grid)
- [x] What's Disrupted section with severity badges
- [x] How It Works 3-step section
- [x] Pricing comparison cards
- [x] Social proof / data sources section
- [x] Footer with links

## Report Form (/report)
- [x] Searchable industry dropdown (20+ options)
- [x] Searchable country dropdown (30+ options)
- [x] Company size dropdown
- [x] Email input with validation
- [x] Optional company name field
- [x] Honeypot field for bot detection
- [x] Disposable email blocking
- [x] Input sanitization
- [x] Form validation with inline errors

## Loading State
- [x] Radar-pulse animation
- [x] Rotating status messages every 3 seconds
- [x] Personalized progress text

## Free Report Display
- [x] Risk level badge (Critical/High/Moderate/Low)
- [x] Formatted report card with markdown
- [x] Prominent upsell box for full report ($49)
- [x] Secondary subscription offer ($19/month)
- [x] Data sources footer

## Full Report Display
- [x] Long-form 8-section report layout
- [x] Sticky action bar (Print, Save PDF, Copy, Share)
- [x] Social sharing (LinkedIn, X, Email, Copy Link with UTM)
- [x] Subscription upsell at bottom

## AI Report Generation
- [x] System prompt per spec Section 5
- [x] Crisis context block from DB
- [x] Free report prompt (8-10 sentences)
- [x] Full report prompt (8 sections)
- [ ] Streaming responses
- [x] Report caching (24h, same industry+country+size)
- [x] Rate limiting (3 free/IP/hour)
- [x] Prompt injection prevention

## Payments (Stripe)
- [ ] Stripe Checkout for $49 one-time
- [ ] Stripe Checkout for $19/month subscription
- [ ] Webhook handler (checkout.session.completed, subscription events)
- [ ] Payment failure handling

## Email
- [ ] Free report email
- [ ] Full report email with PDF
- [ ] Subscription confirmation email
- [ ] Weekly update email

## PDF Generation
- [ ] Server-side PDF with branded header
- [ ] Professional formatting

## Blog (/blog)
- [x] Blog listing page
- [x] Individual blog post pages
- [x] MDX-style content
- [x] CTA in every post

## Admin (/admin)
- [x] Password protection
- [x] Metrics dashboard cards
- [x] Crisis data update form
- [x] Email list export CSV
- [x] Recent reports table
- [x] Recent payments table

## Legal & Error Pages
- [x] Privacy Policy (/privacy)
- [x] Terms of Service (/terms)
- [x] Custom 404 page
- [ ] Custom 500 page
- [x] Payment failed page
- [ ] API timeout page

## SEO
- [x] Meta tags on all pages
- [x] Open Graph tags
- [x] Twitter Card tags
- [x] JSON-LD structured data
- [x] Sitemap
- [x] Robots.txt

## Animations
- [x] Staggered entrance for crisis cards
- [x] CTA pulse animation
- [x] Form field slide-in
- [x] Radar loading animation
- [x] Scroll fade-in (intersection observer)
- [x] Toast notifications

## Tests
- [x] Vitest unit tests for core lib functions
