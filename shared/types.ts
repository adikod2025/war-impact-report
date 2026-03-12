/**
 * Unified type exports
 * Import shared types from this single entry point.
 */

export type * from "../drizzle/schema";
export * from "./_core/errors";

export interface CrisisDataMap {
  war_day_count: string;
  hormuz_status: string;
  brent_crude_price: string;
  brent_crude_change: string;
  jet_fuel_price: string;
  jet_fuel_change: string;
  gcc_gdp_original: string;
  gcc_gdp_revised: string;
  gcc_gdp_change: string;
  hormuz_traffic_change: string;
  war_start_date: string;
  oil_futures_november: string;
  gcc_production_down: string;
  sulfur_gulf_share: string;
  helium_qatar_share: string;
  lng_hormuz_share: string;
  fertilizer_hormuz_share: string;
  shipping_status: string;
  aviation_status: string;
  gcc_tourism_losses: string;
  iran_missiles_fired: string;
  iran_drones_fired: string;
  gcc_states_struck: string;
}

export interface ReportFormData {
  industry: string;
  country: string;
  companySize: string;
  email: string;
  companyName?: string;
  honeypot?: string;
  source?: string;
}

export interface FreeReportResponse {
  content: string;
  riskLevel: string;
  reportId: number;
  userId: number;
  generationTimeMs: number;
  cached: boolean;
}

export interface FullReportResponse {
  content: string;
  riskLevel: string;
  reportId: number;
  generationTimeMs: number;
}

export const INDUSTRIES = [
  "Manufacturing",
  "Agriculture & Fertilizers",
  "Aviation & Aerospace",
  "Oil & Gas",
  "Petrochemicals & Plastics",
  "Semiconductors & Electronics",
  "Logistics & Shipping",
  "Tourism & Hospitality",
  "Construction & Real Estate",
  "Financial Services",
  "Healthcare & Pharmaceuticals",
  "Retail & E-Commerce",
  "Automotive",
  "Energy & Utilities",
  "Telecommunications",
  "Food & Beverage",
  "Mining & Metals",
  "Defense & Security",
  "Education",
  "Technology & SaaS",
  "Other",
] as const;

export const COUNTRIES = [
  "United States",
  "United Kingdom",
  "Germany",
  "France",
  "China",
  "Japan",
  "India",
  "Saudi Arabia",
  "United Arab Emirates",
  "Qatar",
  "Kuwait",
  "Bahrain",
  "Oman",
  "Turkey",
  "South Korea",
  "Australia",
  "Canada",
  "Brazil",
  "South Africa",
  "Nigeria",
  "Egypt",
  "Singapore",
  "Netherlands",
  "Italy",
  "Spain",
  "Poland",
  "Mexico",
  "Indonesia",
  "Thailand",
  "Pakistan",
  "Other",
] as const;

export const COMPANY_SIZES = [
  "Solo / Freelancer (1 person)",
  "Small Business (2-50 employees)",
  "Mid-Market (51-500 employees)",
  "Enterprise (501-5,000 employees)",
  "Large Enterprise (5,000+ employees)",
] as const;

export const DEFAULT_CRISIS_DATA: Record<string, string> = {
  war_day_count: "13",
  hormuz_status: "Closed since March 2, 2026. IRGC officially confirmed closure. Tanker traffic at near zero. War-risk insurance pulled March 5.",
  brent_crude_price: "$110+/barrel",
  brent_crude_change: "+37%",
  jet_fuel_price: "$4.12/gallon",
  jet_fuel_change: "+68%",
  gcc_gdp_original: "4.4%",
  gcc_gdp_revised: "2.6%",
  gcc_gdp_change: "-1.8pts",
  hormuz_traffic_change: "-100%",
  war_start_date: "2026-03-02",
  oil_futures_november: "~$80",
  gcc_production_down: "6.7M bbl/day",
  sulfur_gulf_share: "45%",
  helium_qatar_share: "40%",
  lng_hormuz_share: "20%",
  fertilizer_hormuz_share: "16%",
  shipping_status: "Maersk, CMA CGM, Hapag-Lloyd suspended Hormuz AND Red Sea transits. Rerouting via Cape of Good Hope adds 2-4 weeks.",
  aviation_status: "Middle East airspace largely closed. Dubai Airport struck. Emirates partially resumed. Flight rerouting adds 2+ hours and five-figure fuel costs.",
  gcc_tourism_losses: "$40B",
  iran_missiles_fired: "500+",
  iran_drones_fired: "2,000+",
  gcc_states_struck: "6",
};

export const DISPOSABLE_EMAIL_DOMAINS = [
  "tempmail.com", "guerrillamail.com", "mailinator.com", "throwaway.email",
  "yopmail.com", "10minutemail.com", "trashmail.com", "fakeinbox.com",
  "sharklasers.com", "guerrillamailblock.com", "grr.la", "dispostable.com",
  "mailnesia.com", "maildrop.cc", "discard.email", "temp-mail.org",
  "getnada.com", "emailondeck.com", "mohmal.com", "tempail.com",
  "burnermail.io", "guerrillamail.info", "guerrillamail.net", "guerrillamail.org",
  "guerrillamail.de", "spam4.me", "trash-mail.com", "mytemp.email",
];
