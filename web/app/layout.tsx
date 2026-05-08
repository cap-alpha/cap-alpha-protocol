import type { Metadata } from "next";
import { Inter, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import OnboardingModal from "@/components/onboarding-modal";
import { AuthInterstitial } from "@/components/auth-interstitial";
import { Navbar } from "@/components/navbar";
import Footer from "@/components/footer";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-sans",
});

const instrumentSerif = Instrument_Serif({
    subsets: ["latin"],
    weight: ["400"],
    style: ["normal", "italic"],
    variable: "--font-serif",
});

const jetbrainsMono = JetBrains_Mono({
    subsets: ["latin"],
    variable: "--font-mono",
});

export const metadata: Metadata = {
    title: {
        default: "Pundit Ledger — Sports Media Intelligence & Accountability",
        template: "%s | Pundit Ledger",
    },
    description:
        "Independent accuracy audit of sports media pundits. Every public prediction verified, scored, and permanently on record — so no one can rewrite history.",
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
            <body className={`${inter.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable} font-sans min-h-screen flex flex-col bg-background text-foreground`}>
                <Providers>
                    <OnboardingModal />
                    <AuthInterstitial />
                    <Navbar />
                    <main className="flex-grow">
                        {children}
                    </main>
                    <Footer />
                </Providers>
            </body>
        </html>
    );
}
