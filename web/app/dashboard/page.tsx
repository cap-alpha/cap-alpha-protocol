import { Suspense } from 'react';
import { redirect } from 'next/navigation';
import { CheckoutSuccessHandler } from '@/components/checkout-success-handler';

interface DashboardRootProps {
    searchParams?: { checkout?: string };
}

export default function DashboardRoot({ searchParams }: DashboardRootProps) {
    // After Stripe/LemonSqueezy checkout, the user lands here with
    // ?checkout=success. The CheckoutSuccessHandler forces a Clerk session
    // refresh so publicMetadata.tier is up-to-date before the redirect lands.
    // Issue: #771 Phase 1
    if (searchParams?.checkout === 'success') {
        return (
            <Suspense fallback={null}>
                <CheckoutSuccessHandler />
            </Suspense>
        );
    }

    redirect('/dashboard/gm');
}
