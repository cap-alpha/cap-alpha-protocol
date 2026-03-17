import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Footer from "@/components/footer";
import { Providers } from "@/components/providers";
import OnboardingModal from "@/components/onboarding-modal";
import { AuthInterstitial } from "@/components/auth-interstitial";
import { Navbar } from "@/components/navbar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
    title: "Cap Alpha Protocol",
    description: "Advanced Roster Management System",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <body className={`${inter.className} min-h-screen flex flex-col`}>
                <Providers>
                    <OnboardingModal />
                    <AuthInterstitial />
                    <Navbar />
                    <main className="flex-grow">
                        {children}
                    </main>
                </Providers>
                <Footer />
            </body>
        </html>
    );
}
