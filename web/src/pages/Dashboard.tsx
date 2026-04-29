import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { FlowDiagram } from "@/components/FlowDiagram";
import { IGAuthPanel } from "@/components/IGAuthPanel";
import { TargetsPanel } from "@/components/TargetsPanel";
import { PendingFeed } from "@/components/PendingFeed";
import { HistoryFeed } from "@/components/HistoryFeed";
import { UsersPanel } from "@/components/UsersPanel";
import { api, type HistoryEntry, type IGAuthState, type PendingPost, type Status, type Target, type User } from "@/lib/api";

interface Props {
  userEmail: string;
  onLogout: () => void;
}

export function Dashboard({ userEmail, onLogout }: Props) {
  const [status, setStatus] = useState<Status | null>(null);
  const [ig, setIg] = useState<IGAuthState | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [pending, setPending] = useState<PendingPost[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [users, setUsers] = useState<User[]>([]);

  const refreshAll = useCallback(async () => {
    try {
      const [s, a, t, p, h, u] = await Promise.all([
        api.status(),
        api.igAuth(),
        api.targets(),
        api.pending(),
        api.history(50),
        api.users(),
      ]);
      setStatus(s);
      setIg(a);
      setTargets(t);
      setPending(p);
      setHistory(h);
      setUsers(u);
    } catch {
      // 401 will redirect to login via api client
    }
  }, []);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  useEffect(() => {
    const id = window.setInterval(refreshAll, 8000);
    return () => window.clearInterval(id);
  }, [refreshAll]);

  return (
    <div className="min-h-screen">
      <Header status={status} userEmail={userEmail} onLogout={onLogout} />

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        <FlowDiagram targets={targets} ig={ig} />

        <div className="grid gap-6 lg:grid-cols-2">
          <IGAuthPanel state={ig} onChange={refreshAll} />
          <TargetsPanel targets={targets} onChange={refreshAll} />
        </div>

        <PendingFeed pending={pending} onChange={refreshAll} />

        <div className="grid gap-6 lg:grid-cols-2">
          <HistoryFeed history={history} />
          <UsersPanel users={users} meEmail={userEmail} onChange={refreshAll} />
        </div>

        <footer className="pt-8 text-center text-xs text-muted-foreground">
          Repost · self-hosted, multi-utente. Sessione IG memorizzata solo localmente.
        </footer>
      </main>
    </div>
  );
}
