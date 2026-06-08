"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LayoutDashboard,
  FileText,
  MessageSquare,
  History,
  User,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Bot,
  Sparkles,
  BookOpen,
  GraduationCap,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthContext } from "@/contexts/AuthContext";
import toast from "react-hot-toast";
import { useRouter } from "next/navigation";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Documents", href: "/documents", icon: FileText },
  { label: "Chat", href: "/chat", icon: MessageSquare },
  { label: "Summary", href: "/summary", icon: BookOpen },
  { label: "Quiz", href: "/quiz", icon: GraduationCap },
  { label: "Flashcards", href: "/flashcards", icon: Layers },
  { label: "History", href: "/history", icon: History },
  { label: "Profile", href: "/profile", icon: User },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthContext();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = async () => {
    try {
      await logout();
      router.push("/login");
    } catch {
      toast.error("Logout failed");
    }
  };

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r border-sidebar-border bg-sidebar transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between border-b border-sidebar-border px-4">
        {!collapsed && (
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <Bot className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-sidebar-foreground text-lg tracking-tight">
              IntelliDocs
            </span>
          </Link>
        )}
        {collapsed && (
          <Link href="/dashboard" className="mx-auto">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <Bot className="h-5 w-5 text-white" />
            </div>
          </Link>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "rounded-md p-1.5 text-sidebar-foreground/60 hover:bg-white/5 hover:text-sidebar-foreground transition-colors",
            collapsed && "mx-auto"
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Nav items */}
      <nav className="flex-1 space-y-1 p-3 overflow-y-auto">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-primary/15 text-primary"
                  : "text-sidebar-foreground/70 hover:bg-white/5 hover:text-sidebar-foreground",
                collapsed && "justify-center px-2"
              )}
              title={collapsed ? item.label : undefined}
            >
              <item.icon
                className={cn("h-5 w-5 flex-shrink-0", isActive && "text-primary")}
              />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* User section */}
      <div className="border-t border-sidebar-border p-3">
        {!collapsed && user && (
          <div className="mb-2 flex items-center gap-3 rounded-lg px-3 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary font-semibold text-sm flex-shrink-0">
              {(user.full_name ?? user.email)[0].toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-sidebar-foreground truncate">
                {user.full_name ?? "User"}
              </p>
              <p className="text-xs text-sidebar-foreground/50 truncate">
                {user.plan_tier} plan
              </p>
            </div>
            <Sparkles className="h-3.5 w-3.5 text-primary/60 flex-shrink-0" />
          </div>
        )}

        <button
          onClick={handleLogout}
          className={cn(
            "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-red-500/10 hover:text-red-400",
            collapsed && "justify-center px-2"
          )}
          title={collapsed ? "Sign out" : undefined}
        >
          <LogOut className="h-5 w-5 flex-shrink-0" />
          {!collapsed && <span>Sign out</span>}
        </button>
      </div>
    </aside>
  );
}
