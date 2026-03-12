/**
 * Stripe Integration Module
 * 
 * Provides checkout session creation and webhook handling.
 * Requires STRIPE_SECRET_KEY and VITE_STRIPE_PUBLISHABLE_KEY env vars.
 * Stripe keys can be added later via Settings → Payment.
 */

import { STRIPE_PRODUCTS, type ProductKey } from "./stripe-products";

// Lazy-load Stripe to avoid crashes when keys aren't configured
let stripeInstance: any = null;

async function getStripe() {
  if (stripeInstance) return stripeInstance;

  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    throw new Error("STRIPE_SECRET_KEY is not configured. Add it via Settings → Payment.");
  }

  const { default: Stripe } = await import("stripe");
  stripeInstance = new Stripe(secretKey, {
    apiVersion: "2024-12-18.acacia" as any,
  });
  return stripeInstance;
}

export function isStripeConfigured(): boolean {
  return !!(process.env.STRIPE_SECRET_KEY && process.env.VITE_STRIPE_PUBLISHABLE_KEY);
}

export interface CreateCheckoutParams {
  product: ProductKey;
  userId: number;
  userEmail: string;
  userName?: string;
  reportId?: number;
  origin: string;
}

export async function createCheckoutSession(params: CreateCheckoutParams) {
  const stripe = await getStripe();
  const product = STRIPE_PRODUCTS[params.product];

  const sessionConfig: any = {
    payment_method_types: ["card"],
    mode: product.mode,
    customer_email: params.userEmail,
    client_reference_id: params.userId.toString(),
    allow_promotion_codes: true,
    metadata: {
      user_id: params.userId.toString(),
      customer_email: params.userEmail,
      customer_name: params.userName || "",
      product_key: params.product,
      report_id: params.reportId?.toString() || "",
    },
    success_url: `${params.origin}/report/full?session_id={CHECKOUT_SESSION_ID}&success=true`,
    cancel_url: `${params.origin}/payment-failed`,
  };

  if (product.mode === "payment") {
    sessionConfig.line_items = [{
      price_data: {
        currency: product.currency,
        product_data: {
          name: product.name,
          description: product.description,
        },
        unit_amount: product.priceAmountCents,
      },
      quantity: 1,
    }];
  } else {
    // Subscription mode — use price_data with recurring
    sessionConfig.line_items = [{
      price_data: {
        currency: product.currency,
        product_data: {
          name: product.name,
          description: product.description,
        },
        unit_amount: product.priceAmountCents,
        recurring: {
          interval: "month",
        },
      },
      quantity: 1,
    }];
  }

  const session = await stripe.checkout.sessions.create(sessionConfig);
  return { url: session.url, sessionId: session.id };
}

export async function handleWebhookEvent(payload: Buffer, signature: string) {
  const stripe = await getStripe();
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  if (!webhookSecret) {
    throw new Error("STRIPE_WEBHOOK_SECRET is not configured.");
  }

  const event = stripe.webhooks.constructEvent(payload, signature, webhookSecret);

  // Handle test events
  if (event.id.startsWith("evt_test_")) {
    console.log("[Webhook] Test event detected, returning verification response");
    return { verified: true, test: true };
  }

  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object;
      console.log("[Stripe] Checkout completed:", {
        sessionId: session.id,
        userId: session.metadata?.user_id,
        product: session.metadata?.product_key,
      });
      // Payment fulfillment would happen here:
      // 1. Mark payment as completed in DB
      // 2. Generate full report if product is full_report
      // 3. Create subscription record if product is subscription
      // 4. Send confirmation email
      return { verified: true, eventType: event.type, sessionId: session.id };
    }

    case "customer.subscription.updated":
    case "customer.subscription.deleted": {
      const subscription = event.data.object;
      console.log("[Stripe] Subscription event:", {
        type: event.type,
        subscriptionId: subscription.id,
        status: subscription.status,
      });
      return { verified: true, eventType: event.type };
    }

    case "invoice.paid": {
      const invoice = event.data.object;
      console.log("[Stripe] Invoice paid:", invoice.id);
      return { verified: true, eventType: event.type };
    }

    default:
      console.log("[Stripe] Unhandled event type:", event.type);
      return { verified: true, eventType: event.type };
  }
}
