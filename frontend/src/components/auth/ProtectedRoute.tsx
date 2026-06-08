"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthContext } from "@/contexts/AuthContext";
import { PageLoader } from "@/components/common/LoadingSpinner";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

/**
 * Wraps dashboard pages. If the user is not authenticated after the auth
 * bootstrap completes, redirects to /login.
 *
 * Shows a full-page loader while the auth state is being restored from
 * localStorage (the isLoading=true window on first mount).
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuthContext();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return <PageLoader label="Loading IntelliDocs..." />;
  }

  if (!isAuthenticated) {
    return null; // redirect in progress
  }

  return <>{children}</>;
}
