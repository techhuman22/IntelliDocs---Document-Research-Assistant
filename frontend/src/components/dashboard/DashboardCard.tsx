import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface DashboardCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  iconColor?: string;
  trend?: { value: string; positive: boolean };
  className?: string;
}

export function DashboardCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColor = "text-primary",
  trend,
  className,
}: DashboardCardProps) {
  return (
    <div className={cn("card-base flex flex-col gap-4", className)}>
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <p className="text-3xl font-bold tracking-tight">{value}</p>
          {subtitle && (
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10",
            iconColor.replace("text-", "bg-").replace("500", "500/10")
          )}
        >
          <Icon className={cn("h-5 w-5", iconColor)} />
        </div>
      </div>

      {trend && (
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium",
              trend.positive
                ? "bg-emerald-500/10 text-emerald-500"
                : "bg-red-500/10 text-red-500"
            )}
          >
            {trend.positive ? "↑" : "↓"} {trend.value}
          </span>
          <span className="text-xs text-muted-foreground">this week</span>
        </div>
      )}
    </div>
  );
}
