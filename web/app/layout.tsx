import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import OnboardingModal from "@/components/onboarding-modal";
import { AuthInterstitial } from "@/components/auth-interstitial";
import { Navbar } from "@/components/navbar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
    title: {
        default: "Pundit Ledger — Hold Sports Pundits Accountable",
        template: "%s | Pundit Ledger",
    },
    description:
        "Every sports prediction tracked, scored, and cryptographically sealed. See which pundits are actually right.",
    metadataBase: new URL("https://cap-alpha.co"),
    openGraph: {
        siteName: "Pundit Ledger",
        type: "website",
        locale: "en_US",
    },
    twitter: {
        card: "summary_large_image",
        site: "@punditled",
    },
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="dark">
            <body className={`${inter.className} min-h-screen flex flex-col bg-background text-foreground`}>
                <Providers>
                    <OnboardingModal />
                    <AuthInterstitial />
                    <Navbar />
                    <main className="flex-grow">
                        {children}
                    </main>
                </Providers>
            </body>
        </html>
    );
}
