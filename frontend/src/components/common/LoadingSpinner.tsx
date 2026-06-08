import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
}

const sizeMap = {
  sm: "h-4 w-4 border-2",
  md: "h-8 w-8 border-2",
  lg: "h-12 w-12 border-3",
};

export function LoadingSpinner({
  size = "md",
  className,
  label,
}: LoadingSpinnerProps) {
  return (
    <div className={cn("flex flex-col items-center gap-3", className)}>
      <div
        className={cn(
          "animate-spin rounded-full border-transparent border-t-primary",
          sizeMap[size],
          "border-solid"
        )}
        style={{ borderColor: "hsl(var(--muted)) hsl(var(--muted)) transparent hsl(var(--muted))", borderTopColor: "hsl(var(--primary))" }}
        role="status"
        aria-label={label ?? "Loading"}
      />
      {label && (
        <p className="text-sm text-muted-foreground animate-pulse">{label}</p>
      )}
    </div>
  );
}

export function PageLoader({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex h-full min-h-[400px] w-full items-center justify-center">
      <LoadingSpinner size="lg" label={label} />
    </div>
  );
}

// Three animated dots — used inside chat during agent processing
export function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 px-1 py-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-primary animate-pulse-dot"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </div>
  );
}
