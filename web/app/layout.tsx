import type { Metadata } from "next";
import { Playfair_Display, Source_Sans_3, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import OnboardingModal from "@/components/onboarding-modal";
import { AuthInterstitial } from "@/components/auth-interstitial";
import { Navbar } from "@/components/navbar";
import Footer from "@/components/footer";

const playfairDisplay = Playfair_Display({
    subsets: ["latin"],
    weight: ["400", "700", "900"],
    style: ["normal", "italic"],
    variable: "--font-display",
});

const sourceSans3 = Source_Sans_3({
    subsets: ["latin"],
    weight: ["300", "400", "600", "700"],
    variable: "--font-body",
});

const jetbrainsMono = JetBrains_Mono({
    subsets: ["latin"],
    variable: "--font-mono",
});

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
            <body className={`${playfairDisplay.variable} ${sourceSans3.variable} ${jetbrainsMono.variable} font-body min-h-screen flex flex-col bg-background text-foreground`}>
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
