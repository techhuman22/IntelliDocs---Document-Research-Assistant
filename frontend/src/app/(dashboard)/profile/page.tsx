"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { User, Lock, Trash2, Eye, EyeOff, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import { useAuthContext } from "@/contexts/AuthContext";
import { authApi } from "@/lib/api/auth";

// ── Schemas ──────────────────────────────────────────────────────────────────

const profileSchema = z.object({
  full_name: z.string().min(2, "At least 2 characters").optional().or(z.literal("")),
});

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Required"),
    new_password: z
      .string()
      .min(8, "At least 8 characters")
      .regex(/[A-Z]/, "One uppercase letter")
      .regex(/[0-9]/, "One number"),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "Passwords don't match",
    path: ["confirm_password"],
  });

type ProfileForm = z.infer<typeof profileSchema>;
type PasswordForm = z.infer<typeof passwordSchema>;

// ── Component ─────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const { user, refreshUser, logout } = useAuthContext();
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  // Profile form
  const {
    register: regProfile,
    handleSubmit: handleProfile,
    formState: { errors: profileErrors, isSubmitting: profileSubmitting },
  } = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: user?.full_name ?? "" },
  });

  // Password form
  const {
    register: regPassword,
    handleSubmit: handlePassword,
    reset: resetPassword,
    formState: { errors: passwordErrors, isSubmitting: passwordSubmitting },
  } = useForm<PasswordForm>({ resolver: zodResolver(passwordSchema) });

  // Mutations
  const updateProfileMutation = useMutation({
    mutationFn: (data: ProfileForm) => authApi.updateProfile({ full_name: data.full_name || undefined }),
    onSuccess: async () => {
      await refreshUser();
      toast.success("Profile updated");
    },
    onError: () => toast.error("Failed to update profile"),
  });

  const changePasswordMutation = useMutation({
    mutationFn: (data: PasswordForm) =>
      authApi.changePassword({
        current_password: data.current_password,
        new_password: data.new_password,
      }),
    onSuccess: () => {
      resetPassword();
      toast.success("Password changed");
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to change password";
      toast.error(msg);
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: authApi.deleteAccount,
    onSuccess: () => {
      toast.success("Account deleted");
      logout();
    },
    onError: () => toast.error("Failed to delete account"),
  });

  return (
    <div className="flex flex-col gap-8 p-6 lg:p-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Manage your account settings
        </p>
      </div>

      {/* ── Profile info ── */}
      <section className="card-base flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
            <User className="h-4.5 w-4.5 text-primary" />
          </div>
          <h2 className="font-semibold">Personal information</h2>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold text-primary uppercase">
            {(user?.full_name?.[0] ?? user?.email?.[0] ?? "?").toUpperCase()}
          </div>
          <div>
            <p className="font-medium">{user?.full_name ?? "—"}</p>
            <p className="text-sm text-muted-foreground">{user?.email}</p>
          </div>
        </div>

        <form
          onSubmit={handleProfile((d) => updateProfileMutation.mutate(d))}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Full name</label>
            <input
              {...regProfile("full_name")}
              type="text"
              placeholder="Jane Smith"
              className="rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
            />
            {profileErrors.full_name && (
              <p className="text-xs text-red-500">{profileErrors.full_name.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Email</label>
            <input
              value={user?.email ?? ""}
              disabled
              className="rounded-lg border border-input bg-muted/30 px-3 py-2.5 text-sm text-muted-foreground cursor-not-allowed"
            />
            <p className="text-xs text-muted-foreground">Email cannot be changed</p>
          </div>

          <button
            type="submit"
            disabled={profileSubmitting || updateProfileMutation.isPending}
            className="self-start flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-70"
          >
            {(profileSubmitting || updateProfileMutation.isPending) && (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            Save changes
          </button>
        </form>
      </section>

      {/* ── Change password ── */}
      <section className="card-base flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10">
            <Lock className="h-4.5 w-4.5 text-amber-500" />
          </div>
          <h2 className="font-semibold">Change password</h2>
        </div>

        <form
          onSubmit={handlePassword((d) => changePasswordMutation.mutate(d))}
          className="flex flex-col gap-4"
        >
          {/* Current password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Current password</label>
            <div className="relative">
              <input
                {...regPassword("current_password")}
                type={showCurrent ? "text" : "password"}
                placeholder="••••••••"
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowCurrent((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              >
                {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {passwordErrors.current_password && (
              <p className="text-xs text-red-500">{passwordErrors.current_password.message}</p>
            )}
          </div>

          {/* New password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">New password</label>
            <div className="relative">
              <input
                {...regPassword("new_password")}
                type={showNew ? "text" : "password"}
                placeholder="••••••••"
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowNew((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              >
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {passwordErrors.new_password && (
              <p className="text-xs text-red-500">{passwordErrors.new_password.message}</p>
            )}
          </div>

          {/* Confirm */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Confirm new password</label>
            <input
              {...regPassword("confirm_password")}
              type="password"
              placeholder="••••••••"
              className="rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
            />
            {passwordErrors.confirm_password && (
              <p className="text-xs text-red-500">{passwordErrors.confirm_password.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={passwordSubmitting || changePasswordMutation.isPending}
            className="self-start flex items-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-600 transition-colors disabled:opacity-70"
          >
            {(passwordSubmitting || changePasswordMutation.isPending) && (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            Update password
          </button>
        </form>
      </section>

      {/* ── Danger zone ── */}
      <section className="card-base flex flex-col gap-4 border-red-500/20">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-500/10">
            <Trash2 className="h-4.5 w-4.5 text-red-500" />
          </div>
          <h2 className="font-semibold text-red-500">Danger zone</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Permanently delete your account and all associated data. This action
          cannot be undone.
        </p>

        {!deleteConfirm ? (
          <button
            onClick={() => setDeleteConfirm(true)}
            className="self-start rounded-xl border border-red-500/40 px-4 py-2.5 text-sm font-semibold text-red-500 hover:bg-red-500/10 transition-colors"
          >
            Delete my account
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <button
              onClick={() => deleteAccountMutation.mutate()}
              disabled={deleteAccountMutation.isPending}
              className="flex items-center gap-2 rounded-xl bg-red-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-600 transition-colors disabled:opacity-70"
            >
              {deleteAccountMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              Yes, delete everything
            </button>
            <button
              onClick={() => setDeleteConfirm(false)}
              className="rounded-xl border border-border px-4 py-2.5 text-sm hover:bg-accent transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
