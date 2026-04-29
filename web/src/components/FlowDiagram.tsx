import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import type { IGAuthState, Target } from "@/lib/api";

interface Props {
  targets: Target[];
  ig: IGAuthState | null;
}

/**
 * Visual: a column of source target chips on the left, a single account chip on
 * the right, SVG bezier curves connecting them, with animated dots flowing
 * along the curves whenever a target has pending posts.
 */
export function FlowDiagram({ targets, ig }: Props) {
  const accountUsername = ig?.username ?? null;
  const totalPending = targets.reduce((s, t) => s + t.pending_count, 0);

  return (
    <Card className="overflow-hidden">
      <div className="grid gap-6 px-6 py-8 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,260px)]">
        {/* left: targets stack */}
        <div className="flex flex-col items-stretch gap-3">
          <header className="text-xs uppercase tracking-wider text-muted-foreground">
            Pagine monitorate
          </header>
          {targets.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
              Aggiungi una pagina per iniziare
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {targets.map((t) => (
                <TargetChip key={t.username} target={t} />
              ))}
            </ul>
          )}
        </div>

        {/* center: arrows */}
        <div className="hidden md:flex md:items-center md:justify-center">
          <Arrows count={targets.length} active={totalPending > 0} />
        </div>

        {/* right: account */}
        <div className="flex flex-col items-stretch gap-3">
          <header className="text-xs uppercase tracking-wider text-muted-foreground md:text-right">
            Repost qui
          </header>
          <AccountChip username={accountUsername} state={ig?.state ?? "none"} />
          {totalPending > 0 && (
            <p className="text-xs text-muted-foreground md:text-right">
              {totalPending} {totalPending === 1 ? "post in coda" : "post in coda"} di approvazione
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

function TargetChip({ target }: { target: Target }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-secondary/40 px-3 py-2">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary text-sm font-semibold uppercase text-muted-foreground">
        {target.username[0]}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm">@{target.username}</p>
        <p className="text-xs text-muted-foreground">
          {target.pending_count > 0
            ? `${target.pending_count} pending`
            : "nessun pending"}
        </p>
      </div>
      {target.pending_count > 0 && (
        <span className="size-2 rounded-full bg-primary animate-pulse-glow" />
      )}
    </div>
  );
}

function AccountChip({ username, state }: { username: string | null; state: IGAuthState["state"] }) {
  const subtitle = state === "authed" ? "connesso"
    : state === "pending" ? "sessione in retry"
    : "non autenticato";
  return (
    <div className={`flex items-center gap-3 rounded-md border px-3 py-3 ${state === "authed" ? "border-primary/50 bg-primary/5" : "border-border bg-secondary/40"}`}>
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-primary to-accent text-sm font-semibold text-primary-foreground">
        {username ? username[0].toUpperCase() : "?"}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm">{username ? `@${username}` : "—"}</p>
        <p className={`text-xs ${state === "authed" ? "text-primary" : "text-muted-foreground"}`}>{subtitle}</p>
      </div>
    </div>
  );
}

/**
 * SVG arrows from N stacked points on the left edge to a single point on the
 * right edge. When `active`, dots travel along each path.
 */
function Arrows({ count, active }: { count: number; active: boolean }) {
  const W = 160;
  const H = Math.max(60, count * 56);
  const rightX = W - 4;
  const rightY = H / 2;
  if (count === 0) return <svg width={W} height={60} aria-hidden />;

  const paths: { d: string; key: string }[] = [];
  for (let i = 0; i < count; i++) {
    const y = (i + 0.5) * (H / count);
    const c1x = W * 0.45;
    const d = `M 4 ${y} C ${c1x} ${y}, ${c1x} ${rightY}, ${rightX} ${rightY}`;
    paths.push({ d, key: `p${i}` });
  }

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden className="overflow-visible">
      <defs>
        <linearGradient id="arrowGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="hsl(var(--border))" stopOpacity="0.4" />
          <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0.7" />
        </linearGradient>
      </defs>
      {paths.map((p) => (
        <g key={p.key}>
          <path d={p.d} fill="none" stroke="url(#arrowGradient)" strokeWidth={1.5} />
          {active && (
            <motion.circle
              r={3}
              fill="hsl(var(--primary))"
              initial={false}
            >
              <animateMotion dur="2.4s" repeatCount="indefinite" path={p.d} />
            </motion.circle>
          )}
        </g>
      ))}
      {/* arrow head at the right */}
      <polygon
        points={`${rightX - 6},${rightY - 4} ${rightX + 1},${rightY} ${rightX - 6},${rightY + 4}`}
        fill="hsl(var(--primary))"
      />
    </svg>
  );
}
