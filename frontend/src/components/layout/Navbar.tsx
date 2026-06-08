"use client";

import Link from "next/link";
import { useTheme } from "next-themes";
import { Sun, Moon, Bot, Menu, X } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const navLinks = [
  { label: "Features", href: "#features" },
  { label: "Docs", href: "#" },
];

export function Navbar() {
  const { theme, setTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold tracking-tight">IntelliDocs</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-6">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              {link.label}
            </a>
          ))}
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </button>
          <div className="hidden md:flex items-center gap-2">
            <Link
              href="/login"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-3 py-2"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
            >
              Get started
            </Link>
          </div>
          {/* Mobile menu button */}
          <button
            className="md:hidden rounded-md p-2 text-muted-foreground hover:bg-accent"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-border bg-background px-4 py-4 space-y-3 animate-fade-in">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="block text-sm font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setMobileOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="flex flex-col gap-2 pt-2 border-t border-border">
            <Link href="/login" className="text-sm font-medium py-2 text-center border border-border rounded-lg">
              Sign in
            </Link>
            <Link href="/register" className="text-sm font-semibold py-2 text-center bg-primary rounded-lg text-white">
              Get started
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
