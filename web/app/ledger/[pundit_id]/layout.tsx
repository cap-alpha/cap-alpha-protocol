export default function PunditDetailLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    // generateMetadata is exported from page.tsx (server component) with real
    // pundit name and accuracy stats fetched from the API. No slug-based
    // fallback needed here.
    return <>{children}</>;
}
