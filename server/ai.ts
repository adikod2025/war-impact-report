import { invokeLLM } from "./_core/llm";
import { DEFAULT_CRISIS_DATA } from "../shared/types";
import { getCrisisDataMap } from "./db";
import crypto from "crypto";

// Build crisis context block from DB or defaults
async function getCrisisContext(): Promise<string> {
  let data: Record<string, string>;
  try {
    const dbData = await getCrisisDataMap();
    data = Object.keys(dbData).length > 0 ? { ...DEFAULT_CRISIS_DATA, ...dbData } : DEFAULT_CRISIS_DATA;
  } catch {
    data = DEFAULT_CRISIS_DATA;
  }

  return `CURRENT CRISIS DATA (as of March 2026):
- War Day: Day ${data.war_day_count} of the Iran War (started ${data.war_start_date})
- Strait of Hormuz: ${data.hormuz_status}
- Brent Crude: ${data.brent_crude_price} (${data.brent_crude_change} since pre-war)
- Jet Fuel: ${data.jet_fuel_price} (${data.jet_fuel_change})
- GCC GDP Forecast: Revised from ${data.gcc_gdp_original} to ${data.gcc_gdp_revised} (${data.gcc_gdp_change})
- GCC Production Down: ${data.gcc_production_down}
- Oil Futures (Nov 2026): ${data.oil_futures_november}
- Sulfur (Gulf share): ${data.sulfur_gulf_share}
- Helium (Qatar share): ${data.helium_qatar_share}
- LNG (Hormuz share): ${data.lng_hormuz_share}
- Fertilizer (Hormuz share): ${data.fertilizer_hormuz_share}
- Shipping: ${data.shipping_status}
- Aviation: ${data.aviation_status}
- GCC Tourism Losses: ${data.gcc_tourism_losses}
- Iran Missiles Fired: ${data.iran_missiles_fired}
- Iran Drones Fired: ${data.iran_drones_fired}
- GCC States Struck: ${data.gcc_states_struck}`;
}

const SYSTEM_PROMPT = `You are a senior geopolitical risk analyst at a top-tier consulting firm. Your tone is authoritative, data-driven, and actionable — like a Goldman Sachs research note crossed with a McKinsey crisis briefing.

You write for business owners and C-suite executives who need to understand how the 2026 Iran War and Strait of Hormuz closure affects their specific business. Every statement should be backed by data or clearly labeled as an estimate. Use specific numbers, percentages, and timeframes.

Rules:
- Never use filler phrases like "it's important to note" or "in conclusion"
- Never say "I" or refer to yourself
- Use active voice
- Quantify everything possible
- Be direct and specific to their industry and country
- Include specific company names, trade routes, and data points where relevant
- Format with markdown: use **bold** for emphasis, bullet points for lists
- Risk levels: CRITICAL (direct existential threat), HIGH (significant operational impact), MODERATE (manageable with action), LOW (minimal direct impact)`;

export async function generateFreeReport(
  industry: string,
  country: string,
  companySize: string
): Promise<{ content: string; riskLevel: string }> {
  const crisisContext = await getCrisisContext();

  const userPrompt = `${crisisContext}

BUSINESS PROFILE:
- Industry: ${industry}
- Country: ${country}
- Company Size: ${companySize}

Generate a FREE SUMMARY REPORT (8-10 sentences) that includes:
1. A clear risk level assessment (CRITICAL, HIGH, MODERATE, or LOW) — state this first
2. The 2-3 most significant impacts on this specific industry in this specific country
3. Quantified cost/revenue impacts where possible (percentages, dollar amounts)
4. One specific, actionable recommendation they can implement this week
5. A brief 90-day outlook

Start your response with exactly one of these on its own line: RISK_LEVEL: CRITICAL or RISK_LEVEL: HIGH or RISK_LEVEL: MODERATE or RISK_LEVEL: LOW

Then provide the summary report. Be specific to their industry and country — do not give generic advice.`;

  const result = await invokeLLM({
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userPrompt },
    ],
  });

  const rawContent = typeof result.choices[0].message.content === "string"
    ? result.choices[0].message.content
    : "";

  // Extract risk level from response
  const riskMatch = rawContent.match(/RISK_LEVEL:\s*(CRITICAL|HIGH|MODERATE|LOW)/i);
  const riskLevel = riskMatch ? riskMatch[1].toUpperCase() : "HIGH";

  // Remove the RISK_LEVEL line from content
  const content = rawContent.replace(/RISK_LEVEL:\s*(CRITICAL|HIGH|MODERATE|LOW)\s*/i, "").trim();

  return { content, riskLevel };
}

export async function generateFullReport(
  industry: string,
  country: string,
  companySize: string
): Promise<{ content: string; riskLevel: string }> {
  const crisisContext = await getCrisisContext();

  const userPrompt = `${crisisContext}

BUSINESS PROFILE:
- Industry: ${industry}
- Country: ${country}
- Company Size: ${companySize}

Generate a COMPREHENSIVE FULL REPORT with exactly these 8 sections. Each section should be thorough and specific to this business profile.

Start your response with exactly one of these on its own line: RISK_LEVEL: CRITICAL or RISK_LEVEL: HIGH or RISK_LEVEL: MODERATE or RISK_LEVEL: LOW

Then provide the full report with these sections:

## 1. Risk Assessment
Overall risk rating with justification. Compare to pre-war baseline. Include sector-specific vulnerability score.

## 2. Direct Impacts
How the war directly affects this industry in this country. Include specific supply routes, trade partners, and commodity dependencies. Quantify revenue/cost impacts.

## 3. Supply Chain Vulnerability
Map the specific supply chain risks. Which inputs come through or near the conflict zone? Which suppliers are affected? Include tier-1 and tier-2 supplier risks.

## 4. Alternative Suppliers
Provide specific alternative suppliers, trade routes, and sourcing options. Include company names, countries, and estimated switching costs/timelines.

## 5. 90-Day Cost Projection
Project cost increases across major expense categories (energy, raw materials, shipping, insurance, labor). Provide percentage ranges and dollar estimates where possible.

## 6. Action Plan: This Week
5-7 specific, immediately actionable steps the business should take in the next 7 days. Be concrete — name specific actions, not vague advice.

## 7. Action Plan: Next 30 Days
Strategic actions for the next 30 days. Include contract renegotiations, supplier diversification, inventory strategies, and financial hedging options.

## 8. Opportunity Identification
Identify 3-5 specific opportunities that this crisis creates for businesses in this industry and country. Include potential new markets, competitive advantages, and strategic moves.

Be extremely specific to their industry and country. Use real company names, trade routes, and data points. Every recommendation should be actionable.`;

  const result = await invokeLLM({
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userPrompt },
    ],
    maxTokens: 32768,
  });

  const rawContent = typeof result.choices[0].message.content === "string"
    ? result.choices[0].message.content
    : "";

  const riskMatch = rawContent.match(/RISK_LEVEL:\s*(CRITICAL|HIGH|MODERATE|LOW)/i);
  const riskLevel = riskMatch ? riskMatch[1].toUpperCase() : "HIGH";
  const content = rawContent.replace(/RISK_LEVEL:\s*(CRITICAL|HIGH|MODERATE|LOW)\s*/i, "").trim();

  return { content, riskLevel };
}

// Generate cache key from inputs
export function generateCacheKey(industry: string, country: string, companySize: string, reportType: string): string {
  const raw = `${industry}|${country}|${companySize}|${reportType}`.toLowerCase();
  return crypto.createHash("sha256").update(raw).digest("hex").substring(0, 64);
}

// Input sanitization for prompt injection prevention
export function sanitizeInput(input: string): string {
  // Remove potential prompt injection patterns
  return input
    .replace(/[\x00-\x1F\x7F]/g, "") // Remove control characters
    .replace(/```/g, "") // Remove code blocks
    .replace(/\bignore\b.*\binstructions?\b/gi, "") // Remove "ignore instructions"
    .replace(/\bsystem\b.*\bprompt\b/gi, "") // Remove "system prompt"
    .replace(/\bforget\b.*\brules?\b/gi, "") // Remove "forget rules"
    .trim()
    .substring(0, 200); // Max length
}
