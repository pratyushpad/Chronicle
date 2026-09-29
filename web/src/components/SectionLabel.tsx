import { cn } from "@/lib/utils";

interface SectionLabelProps {
  children: React.ReactNode;
  className?: string;
}

export function SectionLabel({ children, className }: SectionLabelProps) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <span className="h-px flex-1 bg-border-light" />
      <span className="font-sans text-xs font-medium uppercase tracking-[0.2em] text-foreground">
        {children}
      </span>
      <span className="h-px flex-1 bg-border-light" />
    </div>
  );
}
