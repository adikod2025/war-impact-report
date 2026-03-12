import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Link } from "wouter";
import { XCircle, ArrowRight, RefreshCw } from "lucide-react";

export default function PaymentFailedPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <div className="max-w-md mx-auto px-4 py-24 text-center">
        <div className="w-16 h-16 rounded-full bg-crisis-red/10 flex items-center justify-center mx-auto mb-6">
          <XCircle className="w-10 h-10 text-crisis-red" />
        </div>
        <h1 className="text-2xl font-bold mb-3">Payment Failed</h1>
        <p className="text-muted-foreground mb-8">
          Your payment could not be processed. This could be due to insufficient funds, an expired card, or a temporary issue with your payment provider.
        </p>
        <div className="flex flex-col gap-3">
          <Link
            href="/report"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-crisis-red text-white font-semibold rounded-lg hover:bg-crisis-red/90 transition-all"
          >
            <RefreshCw className="w-4 h-4" />
            Try Again
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-secondary text-secondary-foreground font-semibold rounded-lg hover:bg-secondary/80 transition-all"
          >
            Return Home
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
      <Footer />
    </div>
  );
}
