import "dotenv/config";
import express from "express";
import { createServer } from "http";
import net from "net";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { registerOAuthRoutes } from "./oauth";
import { appRouter } from "../routers";
import { createContext } from "./context";
import { serveStatic, setupVite } from "./vite";

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);

  // Stripe webhook route MUST be registered BEFORE express.json()
  // so the raw body is available for signature verification
  app.post("/api/stripe/webhook", express.raw({ type: "application/json" }), async (req, res) => {
    try {
      const { handleWebhookEvent, isStripeConfigured } = await import("../stripe");
      if (!isStripeConfigured()) {
        return res.status(503).json({ error: "Stripe is not configured" });
      }
      const sig = req.headers["stripe-signature"] as string;
      if (!sig) {
        return res.status(400).json({ error: "Missing stripe-signature header" });
      }
      const result = await handleWebhookEvent(req.body, sig);
      return res.json(result);
    } catch (err: any) {
      console.error("[Stripe Webhook Error]", err.message);
      return res.status(400).json({ error: err.message });
    }
  });

  // Configure body parser with larger size limit for file uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));

  // Stripe checkout API route
  app.post("/api/stripe/checkout", async (req, res) => {
    try {
      const { createCheckoutSession, isStripeConfigured } = await import("../stripe");
      if (!isStripeConfigured()) {
        return res.status(503).json({ error: "Stripe payments are not yet configured. Coming soon." });
      }
      const { product, userId, userEmail, userName, reportId } = req.body;
      const origin = req.headers.origin || req.protocol + "://" + req.get("host");
      const result = await createCheckoutSession({
        product,
        userId,
        userEmail,
        userName,
        reportId,
        origin,
      });
      return res.json(result);
    } catch (err: any) {
      console.error("[Stripe Checkout Error]", err.message);
      return res.status(500).json({ error: err.message });
    }
  });

  // Stripe configuration check
  app.get("/api/stripe/status", async (_req, res) => {
    try {
      const { isStripeConfigured } = await import("../stripe");
      res.json({ configured: isStripeConfigured() });
    } catch {
      res.json({ configured: false });
    }
  });

  // OAuth callback under /api/oauth/callback
  registerOAuthRoutes(app);
  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );
  // development mode uses Vite, production mode uses static files
  if (process.env.NODE_ENV === "development") {
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  const preferredPort = parseInt(process.env.PORT || "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using port ${port} instead`);
  }

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
