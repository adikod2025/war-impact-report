import { COOKIE_NAME } from "@shared/const";
import { DISPOSABLE_EMAIL_DOMAINS } from "@shared/types";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, protectedProcedure, adminProcedure, router } from "./_core/trpc";
import { TRPCError } from "@trpc/server";
import { z } from "zod";
import {
  createReportUser,
  createReport,
  getCachedReport,
  setCachedReport,
  getReportById,
  getRecentReports,
  getReportStats,
  getAllReportUsers,
  getRecentPayments,
  getCrisisDataMap,
  upsertCrisisData,
} from "./db";
import { generateFreeReport, generateFullReport, generateCacheKey, sanitizeInput } from "./ai";

// Simple in-memory rate limiter
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

function checkRateLimit(ip: string, maxRequests = 3, windowMs = 3600000): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(ip);
  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(ip, { count: 1, resetAt: now + windowMs });
    return true;
  }
  if (entry.count >= maxRequests) return false;
  entry.count++;
  return true;
}

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(opts => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),

  report: router({
    generateFree: publicProcedure
      .input(z.object({
        industry: z.string().min(1).max(100),
        country: z.string().min(1).max(100),
        companySize: z.string().min(1).max(100),
        email: z.string().email().max(254),
        companyName: z.string().max(200).optional(),
      }))
      .mutation(async ({ input, ctx }) => {
        // Rate limiting
        const ip = ctx.req.headers["x-forwarded-for"] as string || ctx.req.socket?.remoteAddress || "unknown";
        if (!checkRateLimit(ip)) {
          throw new TRPCError({
            code: "TOO_MANY_REQUESTS",
            message: "Rate limit exceeded. Free reports are limited to 3 per hour. Please try again later.",
          });
        }

        // Disposable email check
        const emailDomain = input.email.split("@")[1]?.toLowerCase();
        if (emailDomain && DISPOSABLE_EMAIL_DOMAINS.includes(emailDomain)) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: "Please use a business email address. Disposable emails are not accepted.",
          });
        }

        // Sanitize inputs
        const industry = sanitizeInput(input.industry);
        const country = sanitizeInput(input.country);
        const companySize = sanitizeInput(input.companySize);
        const email = input.email.trim().toLowerCase();

        // Check cache
        const cacheKey = generateCacheKey(industry, country, companySize, "free");
        let cached: Awaited<ReturnType<typeof getCachedReport>> | undefined;
        try {
          cached = await getCachedReport(cacheKey);
        } catch { /* ignore cache errors */ }

        if (cached) {
          const userId = await createReportUser({
            email,
            industry,
            country,
            companySize,
            companyName: input.companyName,
            source: "direct",
          });
          const reportId = await createReport({
            userId,
            reportType: "free",
            content: cached.content,
            industry,
            country,
            companySize,
            riskLevel: cached.riskLevel,
            generationTimeMs: 0,
          });
          return {
            content: cached.content,
            riskLevel: cached.riskLevel || "HIGH",
            reportId,
            userId,
            generationTimeMs: 0,
            cached: true,
          };
        }

        // Generate report
        const startTime = Date.now();
        const { content, riskLevel } = await generateFreeReport(industry, country, companySize);
        const generationTimeMs = Date.now() - startTime;

        // Save user
        const userId = await createReportUser({
          email,
          industry,
          country,
          companySize,
          companyName: input.companyName,
          source: "direct",
        });

        // Save report
        const reportId = await createReport({
          userId,
          reportType: "free",
          content,
          industry,
          country,
          companySize,
          riskLevel,
          generationTimeMs,
        });

        // Cache the result
        try {
          await setCachedReport({ cacheKey, content, riskLevel });
        } catch { /* ignore cache errors */ }

        return {
          content,
          riskLevel,
          reportId,
          userId,
          generationTimeMs,
          cached: false,
        };
      }),

    getById: publicProcedure
      .input(z.object({ id: z.number() }))
      .query(async ({ input }) => {
        const report = await getReportById(input.id);
        if (!report) {
          throw new TRPCError({ code: "NOT_FOUND", message: "Report not found" });
        }
        return report;
      }),
  }),

  admin: router({
    stats: adminProcedure.query(async () => {
      const reportStats = await getReportStats();
      const users = await getAllReportUsers();
      const paymentsData = await getRecentPayments(100);
      return {
        ...reportStats,
        totalUsers: users.length,
        totalRevenue: paymentsData
          .filter((p: any) => p.status === "completed")
          .reduce((sum: number, p: any) => sum + p.amountCents, 0) / 100,
      };
    }),

    recentReports: adminProcedure.query(async () => {
      return getRecentReports(50);
    }),

    emailList: adminProcedure.query(async () => {
      return getAllReportUsers();
    }),

    recentPayments: adminProcedure.query(async () => {
      return getRecentPayments(50);
    }),

    crisisData: adminProcedure.query(async () => {
      return getCrisisDataMap();
    }),

    updateCrisisData: adminProcedure
      .input(z.object({
        key: z.string().min(1).max(100),
        value: z.string().min(1),
      }))
      .mutation(async ({ input }) => {
        await upsertCrisisData(input.key, input.value);
        return { success: true };
      }),
  }),
});

export type AppRouter = typeof appRouter;
