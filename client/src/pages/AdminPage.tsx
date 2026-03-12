import Navbar from "@/components/Navbar";
import { useAuth } from "@/_core/hooks/useAuth";
import { trpc } from "@/lib/trpc";
import { useState } from "react";
import { Shield, Users, FileText, DollarSign, Database, Download, RefreshCw, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { getLoginUrl } from "@/const";

export default function AdminPage() {
  const { user, loading, isAuthenticated } = useAuth();
  const [activeTab, setActiveTab] = useState<"metrics" | "crisis" | "emails" | "reports" | "payments">("metrics");

  // Admin data queries — only enabled when authenticated as admin
  const isAdmin = isAuthenticated && user?.role === "admin";
  const { data: stats } = trpc.admin.stats.useQuery(undefined, { enabled: isAdmin });
  const { data: emailList } = trpc.admin.emailList.useQuery(undefined, { enabled: isAdmin && activeTab === "emails" });
  const { data: recentReports } = trpc.admin.recentReports.useQuery(undefined, { enabled: isAdmin && activeTab === "reports" });
  const { data: recentPayments } = trpc.admin.recentPayments.useQuery(undefined, { enabled: isAdmin && activeTab === "payments" });

  // Crisis data update mutation
  const updateCrisis = trpc.admin.updateCrisisData.useMutation({
    onSuccess: () => toast.success("Crisis data updated"),
    onError: (err) => toast.error("Update failed: " + err.message),
  });

  const [crisisForm, setCrisisForm] = useState<Record<string, string>>({});

  if (loading) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <div className="max-w-md mx-auto px-4 py-24 text-center">
          <Shield className="w-16 h-16 text-muted-foreground mx-auto mb-6" />
          <h1 className="text-2xl font-bold mb-3">Admin Access Required</h1>
          <p className="text-muted-foreground mb-6">Please sign in with an admin account to access the dashboard.</p>
          <a
            href={getLoginUrl()}
            className="inline-flex items-center gap-2 px-6 py-3 bg-crisis-blue text-white font-semibold rounded-lg hover:bg-crisis-blue/90 transition-all"
          >
            Sign In
          </a>
        </div>
      </div>
    );
  }

  if (user?.role !== "admin") {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <div className="max-w-md mx-auto px-4 py-24 text-center">
          <Shield className="w-16 h-16 text-crisis-red mx-auto mb-6" />
          <h1 className="text-2xl font-bold mb-3">Access Denied</h1>
          <p className="text-muted-foreground mb-6">You do not have admin privileges.</p>
        </div>
      </div>
    );
  }

  const conversionRate = stats && stats.totalUsers > 0
    ? ((stats.totalRevenue > 0 ? 1 : 0) / stats.totalUsers * 100).toFixed(1) + "%"
    : "0%";

  const tabs = [
    { id: "metrics" as const, label: "Metrics", icon: TrendingUp },
    { id: "crisis" as const, label: "Crisis Data", icon: Database },
    { id: "emails" as const, label: "Email List", icon: Users },
    { id: "reports" as const, label: "Reports", icon: FileText },
    { id: "payments" as const, label: "Payments", icon: DollarSign },
  ];

  const crisisFields = [
    { key: "war_day_count", label: "War Day Count" },
    { key: "brent_crude_price", label: "Brent Crude Price" },
    { key: "brent_crude_change", label: "Brent Crude Change" },
    { key: "jet_fuel_price", label: "Jet Fuel Price" },
    { key: "jet_fuel_change", label: "Jet Fuel Change" },
    { key: "hormuz_status", label: "Hormuz Status" },
    { key: "gcc_gdp_revised", label: "GCC GDP Revised" },
    { key: "gcc_gdp_change", label: "GCC GDP Change" },
    { key: "shipping_status", label: "Shipping Status" },
    { key: "aviation_status", label: "Aviation Status" },
  ];

  const handleCrisisUpdate = (key: string) => {
    const value = crisisForm[key];
    if (!value) {
      toast.error("Please enter a value");
      return;
    }
    updateCrisis.mutate({ key, value });
  };

  const handleExportCSV = () => {
    if (!emailList || emailList.length === 0) {
      toast.error("No emails to export");
      return;
    }
    const headers = "Email,Industry,Country,Company Size,Company Name,Date\n";
    const rows = emailList.map((u: any) =>
      `"${u.email}","${u.industry}","${u.country}","${u.companySize}","${u.companyName || ""}","${new Date(u.createdAt).toISOString()}"`
    ).join("\n");
    const blob = new Blob([headers + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `war-impact-emails-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV exported");
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center gap-3 mb-8">
          <Shield className="w-6 h-6 text-crisis-red" />
          <h1 className="text-2xl font-bold">Admin Dashboard</h1>
          <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase ml-auto">
            CLASSIFIED // ADMIN ONLY
          </span>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-8 overflow-x-auto border-b border-border/30 pb-px">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? "bg-card border border-border/50 border-b-transparent text-foreground -mb-px"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Metrics Tab */}
        {activeTab === "metrics" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-card border border-border/50 rounded-lg p-5">
                <div className="flex items-center justify-between mb-3">
                  <FileText className="w-5 h-5 text-crisis-blue" />
                </div>
                <p className="font-mono text-2xl font-bold">{stats?.totalReports ?? "—"}</p>
                <p className="text-xs text-muted-foreground">Total Reports Generated</p>
              </div>
              <div className="bg-card border border-border/50 rounded-lg p-5">
                <div className="flex items-center justify-between mb-3">
                  <Users className="w-5 h-5 text-crisis-green" />
                </div>
                <p className="font-mono text-2xl font-bold">{stats?.totalUsers ?? "—"}</p>
                <p className="text-xs text-muted-foreground">Email Signups</p>
              </div>
              <div className="bg-card border border-border/50 rounded-lg p-5">
                <div className="flex items-center justify-between mb-3">
                  <DollarSign className="w-5 h-5 text-crisis-gold" />
                </div>
                <p className="font-mono text-2xl font-bold">${stats?.totalRevenue?.toFixed(2) ?? "0.00"}</p>
                <p className="text-xs text-muted-foreground">Total Revenue</p>
              </div>
              <div className="bg-card border border-border/50 rounded-lg p-5">
                <div className="flex items-center justify-between mb-3">
                  <TrendingUp className="w-5 h-5 text-crisis-red" />
                </div>
                <p className="font-mono text-2xl font-bold">{conversionRate}</p>
                <p className="text-xs text-muted-foreground">Conversion Rate</p>
              </div>
            </div>
          </div>
        )}

        {/* Crisis Data Tab */}
        {activeTab === "crisis" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <h3 className="font-mono text-sm font-semibold tracking-wider uppercase mb-4">
              Crisis Data Configuration
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              Update the crisis data values used in the live crisis bar, dashboard, and AI report generation prompts.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {crisisFields.map((field) => (
                <div key={field.key}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-1.5">
                    {field.label}
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder={field.key}
                      value={crisisForm[field.key] || ""}
                      onChange={(e) => setCrisisForm((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="flex-1 bg-background border border-border/50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-crisis-blue transition-colors"
                    />
                    <button
                      onClick={() => handleCrisisUpdate(field.key)}
                      disabled={updateCrisis.isPending}
                      className="px-3 py-2 bg-crisis-blue text-white text-xs font-semibold rounded-lg hover:bg-crisis-blue/90 transition-colors disabled:opacity-50"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Email List Tab */}
        {activeTab === "emails" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-mono text-sm font-semibold tracking-wider uppercase">
                Email List ({emailList?.length ?? 0})
              </h3>
              <button
                onClick={handleExportCSV}
                className="flex items-center gap-2 px-3 py-1.5 bg-secondary text-sm rounded-lg hover:bg-secondary/80 transition-colors"
              >
                <Download className="w-4 h-4" /> Export CSV
              </button>
            </div>
            {emailList && emailList.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/30">
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Email</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Industry</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Country</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Size</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {emailList.map((u: any, i: number) => (
                      <tr key={i} className="border-b border-border/20 hover:bg-secondary/30">
                        <td className="py-2 px-3">{u.email}</td>
                        <td className="py-2 px-3 text-muted-foreground">{u.industry}</td>
                        <td className="py-2 px-3 text-muted-foreground">{u.country}</td>
                        <td className="py-2 px-3 text-muted-foreground">{u.companySize}</td>
                        <td className="py-2 px-3 text-muted-foreground font-mono text-xs">
                          {new Date(u.createdAt).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Email signups will appear here as users generate reports.
              </p>
            )}
          </div>
        )}

        {/* Reports Tab */}
        {activeTab === "reports" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <h3 className="font-mono text-sm font-semibold tracking-wider uppercase mb-4">
              Recent Reports ({recentReports?.length ?? 0})
            </h3>
            {recentReports && recentReports.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/30">
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">ID</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Type</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Industry</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Country</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Risk</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentReports.map((r: any) => (
                      <tr key={r.id} className="border-b border-border/20 hover:bg-secondary/30">
                        <td className="py-2 px-3 font-mono text-xs">#{r.id}</td>
                        <td className="py-2 px-3">
                          <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded ${
                            r.reportType === "full" ? "bg-crisis-gold/20 text-crisis-gold" : "bg-crisis-blue/20 text-crisis-blue"
                          }`}>
                            {r.reportType?.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-muted-foreground">{r.industry}</td>
                        <td className="py-2 px-3 text-muted-foreground">{r.country}</td>
                        <td className="py-2 px-3">
                          <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded ${
                            r.riskLevel === "CRITICAL" ? "bg-crisis-red/20 text-crisis-red" :
                            r.riskLevel === "HIGH" ? "bg-crisis-gold/20 text-crisis-gold" :
                            r.riskLevel === "MODERATE" ? "bg-crisis-blue/20 text-crisis-blue" :
                            "bg-crisis-green/20 text-crisis-green"
                          }`}>
                            {r.riskLevel}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-muted-foreground font-mono text-xs">
                          {new Date(r.createdAt).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Generated reports will appear here with industry, country, risk level, and timestamp.
              </p>
            )}
          </div>
        )}

        {/* Payments Tab */}
        {activeTab === "payments" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <h3 className="font-mono text-sm font-semibold tracking-wider uppercase mb-4">
              Recent Payments ({recentPayments?.length ?? 0})
            </h3>
            {recentPayments && recentPayments.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/30">
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">ID</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Product</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Amount</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Status</th>
                      <th className="text-left py-2 px-3 font-mono text-xs text-muted-foreground tracking-wider uppercase">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentPayments.map((p: any) => (
                      <tr key={p.id} className="border-b border-border/20 hover:bg-secondary/30">
                        <td className="py-2 px-3 font-mono text-xs">#{p.id}</td>
                        <td className="py-2 px-3">{p.product}</td>
                        <td className="py-2 px-3 font-mono">${(p.amountCents / 100).toFixed(2)}</td>
                        <td className="py-2 px-3">
                          <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded ${
                            p.status === "completed" ? "bg-crisis-green/20 text-crisis-green" :
                            p.status === "failed" ? "bg-crisis-red/20 text-crisis-red" :
                            "bg-crisis-gold/20 text-crisis-gold"
                          }`}>
                            {p.status?.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-muted-foreground font-mono text-xs">
                          {new Date(p.createdAt).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Stripe payment records will appear here once payment integration is active.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
