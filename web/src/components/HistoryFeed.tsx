import { motion, AnimatePresence } from "framer-motion";
import { Check, Clock, ExternalLink, X, AlertCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { HistoryEntry } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

interface Props {
  history: HistoryEntry[];
}

export function HistoryFeed({ history }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="size-4" /> Storia recente
        </CardTitle>
        <CardDescription>
          Ultimi 50 movimenti — pubblicati, scartati, errori.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
            Niente da mostrare ancora.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            <AnimatePresence initial={false}>
              {history.map((h) => (
                <motion.li
                  key={h.id}
                  layout
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-3 py-3"
                >
                  <ActionIcon action={h.action} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">
                      <span className="font-mono text-muted-foreground">@{h.target}/{h.code}</span>{" "}
                      <ActionWord action={h.action} />
                    </p>
                    {h.error && <p className="text-xs text-destructive truncate">{h.error}</p>}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {formatRelative(h.ts)}
                  </span>
                  {h.action === "published" && (
                    <a
                      className="text-muted-foreground hover:text-primary"
                      href={`https://www.instagram.com/p/${h.code}/`}
                      target="_blank"
                      rel="noreferrer"
                      aria-label="Originale"
                    >
                      <ExternalLink className="size-3.5" />
                    </a>
                  )}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function ActionIcon({ action }: { action: HistoryEntry["action"] }) {
  if (action === "published") return <Badge>✓</Badge>;
  if (action === "approved") return <Check className="size-4 text-primary" />;
  if (action === "rejected") return <X className="size-4 text-muted-foreground" />;
  if (action === "failed") return <AlertCircle className="size-4 text-destructive" />;
  return null;
}

function ActionWord({ action }: { action: HistoryEntry["action"] }) {
  if (action === "published") return <span className="text-primary">pubblicato</span>;
  if (action === "approved") return <span>approvato (in coda)</span>;
  if (action === "rejected") return <span className="text-muted-foreground">scartato</span>;
  if (action === "failed") return <span className="text-destructive">fallito</span>;
  return null;
}
