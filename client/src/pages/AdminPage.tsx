import Navbar from "@/components/Navbar";
import { useAuth } from "@/_core/hooks/useAuth";
import { trpc } from "@/lib/trpc";
import { useState } from "react";
import { Shield, Users, FileText, DollarSign, Database, Download, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { getLoginUrl } from "@/const";

export default function AdminPage() {
  const { user, loading, isAuthenticated } = useAuth();
  const [activeTab, setActiveTab] = useState<"metrics" | "crisis" | "emails" | "reports" | "payments">("metrics");

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

  const tabs = [
    { id: "metrics" as const, label: "Metrics", icon: FileText },
    { id: "crisis" as const, label: "Crisis Data", icon: Database },
    { id: "emails" as const, label: "Email List", icon: Users },
    { id: "reports" as const, label: "Reports", icon: FileText },
    { id: "payments" as const, label: "Payments", icon: DollarSign },
  ];

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
              {[
                { label: "Total Reports", value: "—", icon: FileText, color: "text-crisis-blue" },
                { label: "Email Signups", value: "—", icon: Users, color: "text-crisis-green" },
                { label: "Revenue", value: "—", icon: DollarSign, color: "text-crisis-gold" },
                { label: "Conversion Rate", value: "—", icon: RefreshCw, color: "text-crisis-red" },
              ].map((metric) => (
                <div key={metric.label} className="bg-card border border-border/50 rounded-lg p-5">
                  <div className="flex items-center justify-between mb-3">
                    <metric.icon className={`w-5 h-5 ${metric.color}`} />
                  </div>
                  <p className="font-mono text-2xl font-bold">{metric.value}</p>
                  <p className="text-xs text-muted-foreground">{metric.label}</p>
                </div>
              ))}
            </div>
            <p className="text-sm text-muted-foreground">
              Metrics will populate as reports are generated and payments are processed.
            </p>
          </div>
        )}

        {/* Crisis Data Tab */}
        {activeTab === "crisis" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <h3 className="font-mono text-sm font-semibold tracking-wider uppercase mb-4">
              Crisis Data Configuration
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Update the crisis data values that are used in the live crisis bar, dashboard, and AI report generation prompts.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { key: "war_day_count", label: "War Day Count" },
                { key: "brent_crude_price", label: "Brent Crude Price" },
                { key: "brent_crude_change", label: "Brent Crude Change" },
                { key: "jet_fuel_price", label: "Jet Fuel Price" },
                { key: "hormuz_status", label: "Hormuz Status" },
              ].map((field) => (
                <div key={field.key}>
                  <label className="block font-mono text-xs text-muted-foreground tracking-widest uppercase mb-1.5">
                    {field.label}
                  </label>
                  <input
                    type="text"
                    placeholder={field.key}
                    className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm"
                    disabled
                  />
                </div>
              ))}
            </div>
            <button
              onClick={() => toast("Feature coming soon", { description: "Crisis data updates will be available via the admin API." })}
              className="mt-4 px-4 py-2 bg-crisis-blue text-white text-sm font-semibold rounded-lg hover:bg-crisis-blue/90 transition-colors"
            >
              Update Crisis Data
            </button>
          </div>
        )}

        {/* Email List Tab */}
        {activeTab === "emails" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-mono text-sm font-semibold tracking-wider uppercase">Email List</h3>
              <button
                onClick={() => toast("Feature coming soon", { description: "CSV export will be available shortly." })}
                className="flex items-center gap-2 px-3 py-1.5 bg-secondary text-sm rounded-lg hover:bg-secondary/80 transition-colors"
              >
                <Download className="w-4 h-4" /> Export CSV
              </button>
            </div>
            <p className="text-sm text-muted-foreground">
              Email signups will appear here as users generate reports.
            </p>
          </div>
        )}

        {/* Reports Tab */}
        {activeTab === "reports" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <h3 className="font-mono text-sm font-semibold tracking-wider uppercase mb-4">Recent Reports</h3>
            <p className="text-sm text-muted-foreground">
              Generated reports will appear here with industry, country, risk level, and timestamp.
            </p>
          </div>
        )}

        {/* Payments Tab */}
        {activeTab === "payments" && (
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <h3 className="font-mono text-sm font-semibold tracking-wider uppercase mb-4">Recent Payments</h3>
            <p className="text-sm text-muted-foreground">
              Stripe payment records will appear here once payment integration is active.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
