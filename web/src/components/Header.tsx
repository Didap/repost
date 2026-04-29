import { Activity, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Status } from "@/lib/api";
import { api } from "@/lib/api";

interface Props {
  status: Status | null;
  userEmail: string;
  onLogout: () => void;
}

export function Header({ status, userEmail, onLogout }: Props) {
  const ig = status?.ig;
  const igBadge = (() => {
    if (!ig) return <Badge variant="secondary">…</Badge>;
    if (ig.state === "authed")
      return <Badge>✓ @{ig.username}</Badge>;
    if (ig.state === "pending")
      return <Badge variant="warn">⏳ retry sessione</Badge>;
    return <Badge variant="destructive">✕ non autenticato</Badge>;
  })();

  async function logout() {
    try { await api.logout(); } catch { /* ignore */ }
    onLogout();
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border glass">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-6">
        <div className="flex items-center gap-2">
          <div className="blob h-6 w-6" aria-hidden />
          <span className="text-lg font-semibold tracking-tight">Repost</span>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {igBadge}
          {status && (
            <span className="hidden text-xs text-muted-foreground sm:flex sm:items-center sm:gap-1">
              <Activity className="size-3" />
              {status.target_count} target · {status.pending_count} pending · poll {status.polling_interval}s
            </span>
          )}
          <span className="hidden text-xs text-muted-foreground md:inline">{userEmail}</span>
          <Button variant="ghost" size="icon" onClick={logout} aria-label="Esci">
            <LogOut />
          </Button>
        </div>
      </div>
    </header>
  );
}
