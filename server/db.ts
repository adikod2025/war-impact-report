import { eq, desc, sql, and, gte } from "drizzle-orm";
import { drizzle } from "drizzle-orm/mysql2";
import { InsertUser, users, reportUsers, reports, payments, subscriptions, crisisData, reportCache } from "../drizzle/schema";
import type { InsertReportUser, InsertReport, InsertPayment, InsertSubscription, InsertCrisisData, InsertReportCache } from "../drizzle/schema";
import { ENV } from './_core/env';

let _db: ReturnType<typeof drizzle> | null = null;

// Lazily create the drizzle instance so local tooling can run without a DB.
export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try {
      _db = drizzle(process.env.DATABASE_URL);
    } catch (error) {
      console.warn("[Database] Failed to connect:", error);
      _db = null;
    }
  }
  return _db;
}

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.openId) {
    throw new Error("User openId is required for upsert");
  }

  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot upsert user: database not available");
    return;
  }

  try {
    const values: InsertUser = {
      openId: user.openId,
    };
    const updateSet: Record<string, unknown> = {};

    const textFields = ["name", "email", "loginMethod"] as const;
    type TextField = (typeof textFields)[number];

    const assignNullable = (field: TextField) => {
      const value = user[field];
      if (value === undefined) return;
      const normalized = value ?? null;
      values[field] = normalized;
      updateSet[field] = normalized;
    };

    textFields.forEach(assignNullable);

    if (user.lastSignedIn !== undefined) {
      values.lastSignedIn = user.lastSignedIn;
      updateSet.lastSignedIn = user.lastSignedIn;
    }
    if (user.role !== undefined) {
      values.role = user.role;
      updateSet.role = user.role;
    } else if (user.openId === ENV.ownerOpenId) {
      values.role = 'admin';
      updateSet.role = 'admin';
    }

    if (!values.lastSignedIn) {
      values.lastSignedIn = new Date();
    }

    if (Object.keys(updateSet).length === 0) {
      updateSet.lastSignedIn = new Date();
    }

    await db.insert(users).values(values).onDuplicateKeyUpdate({
      set: updateSet,
    });
  } catch (error) {
    console.error("[Database] Failed to upsert user:", error);
    throw error;
  }
}

export async function getUserByOpenId(openId: string) {
  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot get user: database not available");
    return undefined;
  }

  const result = await db.select().from(users).where(eq(users.openId, openId)).limit(1);

  return result.length > 0 ? result[0] : undefined;
}

// ============ REPORT USERS ============
export async function createReportUser(data: InsertReportUser) {
  const db = await getDb();
  if (!db) throw new Error("Database not available");
  const result = await db.insert(reportUsers).values(data);
  return result[0].insertId;
}

export async function getReportUserByEmail(email: string) {
  const db = await getDb();
  if (!db) return undefined;
  const result = await db.select().from(reportUsers).where(eq(reportUsers.email, email)).limit(1);
  return result[0];
}

export async function getAllReportUsers() {
  const db = await getDb();
  if (!db) return [];
  return db.select().from(reportUsers).orderBy(desc(reportUsers.createdAt));
}

// ============ REPORTS ============
export async function createReport(data: InsertReport) {
  const db = await getDb();
  if (!db) throw new Error("Database not available");
  const result = await db.insert(reports).values(data);
  return result[0].insertId;
}

export async function getReportById(id: number) {
  const db = await getDb();
  if (!db) return undefined;
  const result = await db.select().from(reports).where(eq(reports.id, id)).limit(1);
  return result[0];
}

export async function getRecentReports(limit = 50) {
  const db = await getDb();
  if (!db) return [];
  return db.select().from(reports).orderBy(desc(reports.createdAt)).limit(limit);
}

export async function getReportStats() {
  const db = await getDb();
  if (!db) return { totalReports: 0, freeReports: 0, fullReports: 0 };
  const result = await db.select({
    total: sql<number>`COUNT(*)`,
    free: sql<number>`SUM(CASE WHEN reportType = 'free' THEN 1 ELSE 0 END)`,
    full: sql<number>`SUM(CASE WHEN reportType = 'full' THEN 1 ELSE 0 END)`,
  }).from(reports);
  return {
    totalReports: result[0]?.total || 0,
    freeReports: result[0]?.free || 0,
    fullReports: result[0]?.full || 0,
  };
}

// ============ PAYMENTS ============
export async function createPayment(data: InsertPayment) {
  const db = await getDb();
  if (!db) throw new Error("Database not available");
  const result = await db.insert(payments).values(data);
  return result[0].insertId;
}

export async function updatePaymentStatus(sessionId: string, status: "completed" | "failed" | "refunded") {
  const db = await getDb();
  if (!db) return;
  await db.update(payments).set({ status }).where(eq(payments.stripeSessionId, sessionId));
}

export async function getRecentPayments(limit = 50) {
  const db = await getDb();
  if (!db) return [];
  return db.select().from(payments).orderBy(desc(payments.createdAt)).limit(limit);
}

// ============ SUBSCRIPTIONS ============
export async function createSubscription(data: InsertSubscription) {
  const db = await getDb();
  if (!db) throw new Error("Database not available");
  const result = await db.insert(subscriptions).values(data);
  return result[0].insertId;
}

// ============ CRISIS DATA ============
export async function getCrisisDataMap(): Promise<Record<string, string>> {
  const db = await getDb();
  if (!db) return {};
  const rows = await db.select().from(crisisData);
  const map: Record<string, string> = {};
  for (const row of rows) {
    map[row.dataKey] = row.dataValue;
  }
  return map;
}

export async function upsertCrisisData(key: string, value: string, updatedBy = "admin") {
  const db = await getDb();
  if (!db) throw new Error("Database not available");
  await db.insert(crisisData).values({ dataKey: key, dataValue: value, updatedBy })
    .onDuplicateKeyUpdate({ set: { dataValue: value, updatedBy } });
}

// ============ REPORT CACHE ============
export async function getCachedReport(cacheKey: string) {
  const db = await getDb();
  if (!db) return undefined;
  const twentyFourHoursAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const result = await db.select().from(reportCache)
    .where(and(eq(reportCache.cacheKey, cacheKey), gte(reportCache.createdAt, twentyFourHoursAgo)))
    .limit(1);
  return result[0];
}

export async function setCachedReport(data: InsertReportCache) {
  const db = await getDb();
  if (!db) return;
  await db.insert(reportCache).values(data)
    .onDuplicateKeyUpdate({ set: { content: data.content, riskLevel: data.riskLevel } });
}
