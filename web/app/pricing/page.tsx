import { PricingClient } from "./pricing-client";

export const metadata = {
    title: "Pricing | Pundit Ledger",
    description: "Choose the plan that fits how deeply you want to hold pundits accountable.",
};

export default function PricingPage() {
    return (
        <main className="bg-black text-white min-h-[100dvh] px-6 py-20">
            <div className="max-w-5xl mx-auto space-y-12">
                <div className="text-center space-y-3">
                    <h1 className="text-4xl font-black tracking-tight">Pricing</h1>
                    <p className="text-zinc-400 max-w-xl mx-auto">
                        Choose how deeply you want to hold pundits accountable. All plans include the
                        cryptographically verified ledger.
                    </p>
                </div>

                <PricingClient />

                <p className="text-center text-xs text-zinc-600">
                    Enterprise pricing available for teams and media organizations.{" "}
                    <a href="mailto:hello@cap-alpha.co" className="underline hover:text-zinc-400">
                        Contact us.
                    </a>
                </p>
            </div>
        </main>
    );
}
