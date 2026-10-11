import { cn } from "@/lib/utils";

const STROKE = 12;

type RadialGaugeProps = {
  value: number;
  label?: string;
  size?: number;
  className?: string;
};

function toneFor(pct: number): string {
  if (pct < 50) return "stroke-destructive";
  if (pct < 80) return "stroke-warning";
  return "stroke-success";
}

export function RadialGauge({ value, label = "Health", size = 160, className }: RadialGaugeProps) {
  const pct = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const center = size / 2;
  const radius = (size - STROKE) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (pct / 100) * circumference;

  return (
    <div
      role="img"
      aria-label={`${label} ${pct} out of 100`}
      className={cn("relative shrink-0", className)}
      style={{ width: size, height: size }}
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true" className="-rotate-90">
        <circle cx={center} cy={center} r={radius} fill="none" strokeWidth={STROKE} className="stroke-muted" />
        {dash > 0 ? (
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
            className={toneFor(pct)}
          />
        ) : null}
      </svg>
      <div aria-hidden="true" className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-semibold leading-none tracking-tight text-foreground tabular-nums"
          style={{ fontSize: size * 0.26 }}
        >
          {pct}
        </span>
        <span className="mt-1 text-xs font-medium text-muted-foreground">
          {label}
        </span>
      </div>
    </div>
  );
}
