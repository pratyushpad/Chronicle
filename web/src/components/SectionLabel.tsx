import { cn } from "@/lib/utils";

interface SectionLabelProps {
  children: React.ReactNode;
  className?: string;
}

export function SectionLabel({ children, className }: SectionLabelProps) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <span className="h-px flex-1 bg-foreground" />
      <span className="font-mono text-xs font-medium uppercase tracking-[0.2em] text-foreground">
        {children}
      </span>
      <span className="h-px flex-1 bg-foreground" />
    </div>
  );
}
