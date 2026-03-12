/**
 * Stripe Product & Price Configuration
 * 
 * These are placeholder price IDs. Once Stripe keys are configured,
 * create products in Stripe Dashboard and update these IDs.
 * 
 * Products:
 * 1. Full Intelligence Report — $49 one-time
 * 2. Weekly Update Subscription — $19/month
 */

export const STRIPE_PRODUCTS = {
  fullReport: {
    name: "Full Intelligence Report",
    description: "Comprehensive 8-section AI-powered business impact assessment for the Iran War crisis",
    priceAmountCents: 4900,
    currency: "usd",
    mode: "payment" as const,
    // Replace with actual Stripe Price ID after creating in Stripe Dashboard
    stripePriceId: process.env.STRIPE_FULL_REPORT_PRICE_ID || "price_full_report_placeholder",
  },
  weeklySubscription: {
    name: "Weekly Update Subscription",
    description: "Weekly AI-updated crisis impact reports delivered to your inbox",
    priceAmountCents: 1900,
    currency: "usd",
    mode: "subscription" as const,
    // Replace with actual Stripe Price ID after creating in Stripe Dashboard
    stripePriceId: process.env.STRIPE_SUBSCRIPTION_PRICE_ID || "price_subscription_placeholder",
  },
} as const;

export type ProductKey = keyof typeof STRIPE_PRODUCTS;
