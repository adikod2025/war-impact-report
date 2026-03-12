/**
 * Email Integration Module
 * 
 * Uses Resend for transactional emails. Requires RESEND_API_KEY env var.
 * Falls back to console logging when not configured.
 */

const RESEND_API_KEY = process.env.RESEND_API_KEY;
const FROM_EMAIL = process.env.FROM_EMAIL || "War Impact Report <noreply@warimpactreport.com>";

interface EmailParams {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

export function isEmailConfigured(): boolean {
  return !!RESEND_API_KEY;
}

async function sendEmail(params: EmailParams): Promise<boolean> {
  if (!RESEND_API_KEY) {
    console.log("[Email] Resend not configured. Would send:", {
      to: params.to,
      subject: params.subject,
    });
    return true; // Don't block the flow
  }

  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM_EMAIL,
        to: params.to,
        subject: params.subject,
        html: params.html,
        text: params.text,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error("[Email] Send failed:", error);
      return false;
    }

    console.log("[Email] Sent successfully to:", params.to);
    return true;
  } catch (err) {
    console.error("[Email] Error:", err);
    return false;
  }
}

export async function sendFreeReportEmail(
  email: string,
  industry: string,
  country: string,
  riskLevel: string,
  reportContent: string
): Promise<boolean> {
  const riskColor = riskLevel === "CRITICAL" ? "#EF4444" : riskLevel === "HIGH" ? "#F59E0B" : riskLevel === "MODERATE" ? "#3B82F6" : "#10B981";

  return sendEmail({
    to: email,
    subject: `Your War Impact Report: ${industry} in ${country} — Risk Level: ${riskLevel}`,
    html: `
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0A0E17;color:#F9FAFB;font-family:Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 24px;">
    <div style="text-align:center;margin-bottom:24px;">
      <h1 style="color:#EF4444;font-size:24px;margin:0;">WAR IMPACT REPORT</h1>
      <p style="color:#9CA3AF;font-size:14px;margin:4px 0 0;">Iran War Business Impact Assessment</p>
    </div>
    <div style="background:#111827;border:1px solid #1F2937;border-radius:8px;padding:24px;margin-bottom:24px;">
      <div style="display:inline-block;background:${riskColor}22;color:${riskColor};padding:4px 12px;border-radius:4px;font-weight:bold;font-size:14px;margin-bottom:16px;">
        ${riskLevel} RISK
      </div>
      <h2 style="color:#F9FAFB;font-size:18px;margin:12px 0 8px;">${industry} — ${country}</h2>
      <div style="color:#D1D5DB;font-size:14px;line-height:1.6;">
        ${reportContent.replace(/\n/g, "<br>")}
      </div>
    </div>
    <div style="text-align:center;margin-bottom:24px;">
      <a href="https://warimpactreport.com/report" style="display:inline-block;background:#EF4444;color:white;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
        Get Your Full Intelligence Report — $49
      </a>
      <p style="color:#9CA3AF;font-size:12px;margin-top:8px;">8 detailed sections with alternative suppliers and action plans</p>
    </div>
    <div style="border-top:1px solid #1F2937;padding-top:16px;text-align:center;color:#6B7280;font-size:12px;">
      <p>War Impact Report | Powered by AI Intelligence</p>
      <p><a href="https://warimpactreport.com/privacy" style="color:#6B7280;">Privacy</a> · <a href="https://warimpactreport.com/terms" style="color:#6B7280;">Terms</a></p>
    </div>
  </div>
</body>
</html>`,
    text: `War Impact Report: ${industry} in ${country}\nRisk Level: ${riskLevel}\n\n${reportContent}\n\nGet your full report at https://warimpactreport.com/report`,
  });
}

export async function sendFullReportEmail(
  email: string,
  industry: string,
  country: string,
  riskLevel: string,
  pdfUrl?: string
): Promise<boolean> {
  return sendEmail({
    to: email,
    subject: `Your Full Intelligence Report: ${industry} in ${country}`,
    html: `
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0A0E17;color:#F9FAFB;font-family:Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 24px;">
    <div style="text-align:center;margin-bottom:24px;">
      <h1 style="color:#EF4444;font-size:24px;margin:0;">WAR IMPACT REPORT</h1>
      <p style="color:#9CA3AF;font-size:14px;margin:4px 0 0;">Full Intelligence Report Delivered</p>
    </div>
    <div style="background:#111827;border:1px solid #1F2937;border-radius:8px;padding:24px;margin-bottom:24px;">
      <h2 style="color:#F9FAFB;font-size:18px;margin:0 0 8px;">Your report is ready</h2>
      <p style="color:#D1D5DB;font-size:14px;line-height:1.6;">
        Your comprehensive 8-section intelligence report for <strong>${industry}</strong> in <strong>${country}</strong> has been generated.
      </p>
      ${pdfUrl ? `<p style="margin-top:16px;"><a href="${pdfUrl}" style="display:inline-block;background:#3B82F6;color:white;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">Download PDF Report</a></p>` : ""}
    </div>
    <div style="text-align:center;margin-bottom:24px;">
      <a href="https://warimpactreport.com/report/full" style="display:inline-block;background:#EF4444;color:white;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
        View Report Online
      </a>
    </div>
    <div style="background:#111827;border:1px solid #374151;border-radius:8px;padding:16px;margin-bottom:24px;">
      <p style="color:#F59E0B;font-weight:bold;margin:0 0 4px;">Stay Updated — $19/month</p>
      <p style="color:#9CA3AF;font-size:13px;margin:0;">Get weekly AI-updated reports as the crisis evolves.</p>
    </div>
    <div style="border-top:1px solid #1F2937;padding-top:16px;text-align:center;color:#6B7280;font-size:12px;">
      <p>War Impact Report | Powered by AI Intelligence</p>
    </div>
  </div>
</body>
</html>`,
    text: `Your Full Intelligence Report for ${industry} in ${country} is ready.\n\nView online: https://warimpactreport.com/report/full\n${pdfUrl ? `Download PDF: ${pdfUrl}` : ""}`,
  });
}

export async function sendSubscriptionConfirmationEmail(
  email: string,
  industry: string,
  country: string
): Promise<boolean> {
  return sendEmail({
    to: email,
    subject: "Subscription Confirmed — Weekly War Impact Updates",
    html: `
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0A0E17;color:#F9FAFB;font-family:Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 24px;">
    <div style="text-align:center;margin-bottom:24px;">
      <h1 style="color:#EF4444;font-size:24px;margin:0;">WAR IMPACT REPORT</h1>
      <p style="color:#10B981;font-size:14px;margin:4px 0 0;">Subscription Active</p>
    </div>
    <div style="background:#111827;border:1px solid #1F2937;border-radius:8px;padding:24px;">
      <h2 style="color:#F9FAFB;font-size:18px;margin:0 0 12px;">You're subscribed to weekly updates</h2>
      <p style="color:#D1D5DB;font-size:14px;line-height:1.6;">
        Every week, you'll receive an AI-updated impact report for <strong>${industry}</strong> in <strong>${country}</strong> as the Iran War crisis evolves.
      </p>
      <p style="color:#9CA3AF;font-size:13px;margin-top:16px;">
        Your first weekly update will arrive within 7 days. You can manage your subscription at any time.
      </p>
    </div>
    <div style="border-top:1px solid #1F2937;padding-top:16px;margin-top:24px;text-align:center;color:#6B7280;font-size:12px;">
      <p>War Impact Report | $19/month — Cancel anytime</p>
    </div>
  </div>
</body>
</html>`,
    text: `Subscription confirmed! You'll receive weekly war impact updates for ${industry} in ${country}. First update within 7 days.`,
  });
}
