import { int, mysqlEnum, mysqlTable, text, timestamp, varchar, boolean } from "drizzle-orm/mysql-core";

/**
 * Core user table backing auth flow.
 * Extend this file with additional tables as your product grows.
 * Columns use camelCase to match both database fields and generated types.
 */
export const users = mysqlTable("users", {
  /**
   * Surrogate primary key. Auto-incremented numeric value managed by the database.
   * Use this for relations between tables.
   */
  id: int("id").autoincrement().primaryKey(),
  /** Manus OAuth identifier (openId) returned from the OAuth callback. Unique per user. */
  openId: varchar("openId", { length: 64 }).notNull().unique(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

// Report users (public, no auth required)
export const reportUsers = mysqlTable("report_users", {
  id: int("id").autoincrement().primaryKey(),
  email: varchar("email", { length: 254 }).notNull(),
  industry: varchar("industry", { length: 100 }).notNull(),
  country: varchar("country", { length: 100 }).notNull(),
  companySize: varchar("companySize", { length: 50 }).notNull(),
  companyName: varchar("companyName", { length: 200 }),
  source: varchar("source", { length: 50 }).default("direct"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type ReportUser = typeof reportUsers.$inferSelect;
export type InsertReportUser = typeof reportUsers.$inferInsert;

// Reports
export const reports = mysqlTable("reports", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull(),
  reportType: mysqlEnum("reportType", ["free", "full"]).notNull(),
  content: text("content").notNull(),
  promptVersion: varchar("promptVersion", { length: 20 }).default("v1"),
  generationTimeMs: int("generationTimeMs"),
  industry: varchar("industry", { length: 100 }).notNull(),
  country: varchar("country", { length: 100 }).notNull(),
  companySize: varchar("companySize", { length: 50 }).notNull(),
  riskLevel: varchar("riskLevel", { length: 20 }),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type Report = typeof reports.$inferSelect;
export type InsertReport = typeof reports.$inferInsert;

// Payments
export const payments = mysqlTable("payments", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull(),
  stripeSessionId: varchar("stripeSessionId", { length: 255 }),
  stripePaymentIntent: varchar("stripePaymentIntent", { length: 255 }),
  amountCents: int("amountCents").notNull(),
  currency: varchar("currency", { length: 3 }).default("usd"),
  status: mysqlEnum("status", ["pending", "completed", "failed", "refunded"]).default("pending").notNull(),
  product: mysqlEnum("product", ["full_report", "subscription"]).notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type Payment = typeof payments.$inferSelect;
export type InsertPayment = typeof payments.$inferInsert;

// Subscriptions
export const subscriptions = mysqlTable("subscriptions", {
  id: int("id").autoincrement().primaryKey(),
  userId: int("userId").notNull(),
  stripeSubscriptionId: varchar("stripeSubscriptionId", { length: 255 }),
  stripeCustomerId: varchar("stripeCustomerId", { length: 255 }),
  status: mysqlEnum("subscriptionStatus", ["active", "cancelled", "past_due"]).default("active").notNull(),
  currentPeriodEnd: timestamp("currentPeriodEnd"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type Subscription = typeof subscriptions.$inferSelect;
export type InsertSubscription = typeof subscriptions.$inferInsert;

// Crisis Data (key-value store for admin-updatable data)
export const crisisData = mysqlTable("crisis_data", {
  id: int("id").autoincrement().primaryKey(),
  dataKey: varchar("dataKey", { length: 100 }).notNull().unique(),
  dataValue: text("dataValue").notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  updatedBy: varchar("updatedBy", { length: 100 }).default("system"),
});

export type CrisisData = typeof crisisData.$inferSelect;
export type InsertCrisisData = typeof crisisData.$inferInsert;

// Report cache for deduplication
export const reportCache = mysqlTable("report_cache", {
  id: int("id").autoincrement().primaryKey(),
  cacheKey: varchar("cacheKey", { length: 64 }).notNull().unique(),
  content: text("content").notNull(),
  riskLevel: varchar("riskLevel", { length: 20 }),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});  

export type ReportCache = typeof reportCache.$inferSelect;
export type InsertReportCache = typeof reportCache.$inferInsert;