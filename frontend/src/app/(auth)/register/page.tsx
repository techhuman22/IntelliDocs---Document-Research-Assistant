"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bot, Eye, EyeOff, Loader2, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useAuthContext } from "@/contexts/AuthContext";

const registerSchema = z
  .object({
    full_name: z.string().min(2, "Name must be at least 2 characters").optional(),
    email: z.string().email("Enter a valid email"),
    password: z
      .string()
      .min(8, "At least 8 characters")
      .regex(/[A-Z]/, "One uppercase letter")
      .regex(/[0-9]/, "One number"),
    confirmPassword: z.string(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

type RegisterForm = z.infer<typeof registerSchema>;

const passwordRules = [
  { label: "At least 8 characters", test: (v: string) => v.length >= 8 },
  { label: "One uppercase letter", test: (v: string) => /[A-Z]/.test(v) },
  { label: "One number", test: (v: string) => /[0-9]/.test(v) },
];

export default function RegisterPage() {
  const { register: authRegister } = useAuthContext();
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>({ resolver: zodResolver(registerSchema) });

  const passwordValue = watch("password", "");

  const onSubmit = async (data: RegisterForm) => {
    try {
      await authRegister({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
      });
      toast.success("Account created! Welcome to IntelliDocs.");
      router.replace("/dashboard");
    } catch (err: unknown) {
      const errData = (err as { response?: { data?: { detail?: string; error?: { message?: string } } } })?.response?.data;
      const message =
        errData?.detail ??
        errData?.error?.message ??
        "Registration failed. Please try again.";
      toast.error(message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-[500px] w-[700px] rounded-full bg-primary/8 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary shadow-lg shadow-primary/30">
            <Bot className="h-7 w-7 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold">Create your account</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Free forever. No credit card required.
            </p>
          </div>
        </div>

        <div className="card-base">
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
            {/* Name */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="full_name" className="text-sm font-medium">
                Full name <span className="text-muted-foreground">(optional)</span>
              </label>
              <input
                id="full_name"
                type="text"
                autoComplete="name"
                {...register("full_name")}
                className="rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                placeholder="Jane Smith"
              />
            </div>

            {/* Email */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                {...register("email")}
                className="rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                placeholder="you@company.com"
              />
              {errors.email && (
                <p className="text-xs text-red-500">{errors.email.message}</p>
              )}
            </div>

            {/* Password */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  {...register("password")}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {/* Strength indicators */}
              {passwordValue && (
                <ul className="mt-1 flex flex-col gap-1">
                  {passwordRules.map((rule) => (
                    <li
                      key={rule.label}
                      className={`flex items-center gap-1.5 text-xs ${
                        rule.test(passwordValue) ? "text-emerald-500" : "text-muted-foreground"
                      }`}
                    >
                      <CheckCircle2 className="h-3 w-3 flex-shrink-0" />
                      {rule.label}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Confirm password */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="confirmPassword" className="text-sm font-medium">
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                {...register("confirmPassword")}
                className="rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
                placeholder="••••••••"
              />
              {errors.confirmPassword && (
                <p className="text-xs text-red-500">
                  {errors.confirmPassword.message}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-2 flex items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-70 shadow-lg shadow-primary/25"
            >
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              Create account
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
