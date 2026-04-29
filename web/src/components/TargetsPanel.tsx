import { useState, type FormEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ExternalLink, Plus, Target as TargetIcon, Trash2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api, type Target } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

interface Props {
  targets: Target[];
  onChange: () => void;
}

export function TargetsPanel({ targets, onChange }: Props) {
  const [adding, setAdding] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    const u = value.trim().replace(/^@/, "");
    if (!u) return;
    setAdding(true);
    setError(null);
    try {
      await api.addTarget(u);
      setValue("");
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore");
    } finally {
      setAdding(false);
    }
  }

  async function remove(username: string) {
    if (!confirm(`Rimuovere @${username} dai target monitorati?`)) return;
    await api.removeTarget(username);
    onChange();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TargetIcon className="size-4" /> Pagine monitorate
        </CardTitle>
        <CardDescription>
          Le pagine Instagram da cui prendere i post da ripubblicare.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <form onSubmit={add} className="flex gap-2">
          <div className="relative flex-1">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">@</span>
            <Input
              className="pl-7"
              placeholder="username"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={adding}
            />
          </div>
          <Button type="submit" disabled={adding || !value.trim()}>
            <Plus /> Aggiungi
          </Button>
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}

        <ul className="divide-y divide-border rounded-md border border-border">
          <AnimatePresence initial={false}>
            {targets.length === 0 ? (
              <li className="px-4 py-6 text-center text-sm text-muted-foreground">
                Nessuna pagina monitorata.
              </li>
            ) : (
              targets.map((t) => (
                <motion.li
                  key={t.username}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-3 px-4 py-3"
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary text-xs font-semibold uppercase">
                    {t.username[0]}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <a
                        href={`https://www.instagram.com/${t.username}/`}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate font-mono text-sm hover:text-primary"
                      >
                        @{t.username}
                      </a>
                      <ExternalLink className="size-3 text-muted-foreground" />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t.last_seen_at
                        ? `ultimo post visto ${formatRelative(t.last_seen_at)}`
                        : "in attesa del primo poll"}
                    </p>
                  </div>
                  {t.pending_count > 0 && (
                    <Badge>{t.pending_count} pending</Badge>
                  )}
                  <Button variant="ghost" size="icon" onClick={() => remove(t.username)} aria-label="Rimuovi">
                    <Trash2 className="text-muted-foreground" />
                  </Button>
                </motion.li>
              ))
            )}
          </AnimatePresence>
        </ul>
      </CardContent>
    </Card>
  );
}
