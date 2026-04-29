import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { AtSign, KeyRound, ShieldAlert, X } from "lucide-react";
import { api, type IGAuthState } from "@/lib/api";

interface Props {
  state: IGAuthState | null;
  onChange: () => void;
}

export function IGAuthPanel({ state, onChange }: Props) {
  const [sessionid, setSessionid] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setFeedback(null);
    try {
      const r = await api.igLogin(sessionid);
      if (r.state === "authed") {
        setFeedback(`✓ Autenticato come @${r.username}`);
        setSessionid("");
        setTimeout(() => setOpen(false), 800);
      } else {
        setFeedback(
          `Salvato. IG sta facendo lo schizzinoso: ${r.last_attempt_error ?? "challenge"}. ` +
            `Riprovo in background con backoff dolce.`,
        );
      }
      onChange();
    } catch (e) {
      setFeedback(e instanceof Error ? e.message : "Errore");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelPending() {
    await api.igClearPending();
    onChange();
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <AtSign className="size-4" /> Account AtSign
          </CardTitle>
          <CardDescription>
            Da dove pubblicheremo i post approvati.
          </CardDescription>
        </div>
        <StateBadge state={state} />
      </CardHeader>

      <CardContent className="space-y-4">
        {state?.state === "authed" ? (
          <p className="text-sm">
            Connesso come <span className="font-mono font-semibold text-primary">@{state.username}</span>.
          </p>
        ) : state?.state === "pending" ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Sessionid in attesa di validazione. Sto riprovando in automatico
              (10/20/40/60 min, poi ogni ora). Quando va, parto.
            </p>
            <div className="flex gap-2">
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" variant="outline">Cambia sessionid</Button>
                </DialogTrigger>
                <SessionidDialog
                  sessionid={sessionid}
                  setSessionid={setSessionid}
                  submitting={submitting}
                  feedback={feedback}
                  submit={submit}
                />
              </Dialog>
              <Button size="sm" variant="ghost" onClick={cancelPending}>
                <X className="size-4" /> Annulla
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Non sei ancora connesso. Incolla il sessionid del tuo browser per autorizzare il bot.
            </p>
            <div className="flex flex-wrap gap-2">
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <KeyRound /> Aggiungi sessionid
                  </Button>
                </DialogTrigger>
                <SessionidDialog
                  sessionid={sessionid}
                  setSessionid={setSessionid}
                  submitting={submitting}
                  feedback={feedback}
                  submit={submit}
                />
              </Dialog>
              <Button variant="outline" disabled title="Disponibile in v2 dopo App Review Meta">
                <AtSign /> Login con AtSign (presto)
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StateBadge({ state }: { state: IGAuthState | null }) {
  if (!state) return null;
  if (state.state === "authed") return <Badge>Connesso</Badge>;
  if (state.state === "pending") return <Badge variant="warn">In retry</Badge>;
  return <Badge variant="destructive">Da configurare</Badge>;
}

interface SDProps {
  sessionid: string;
  setSessionid: (s: string) => void;
  submitting: boolean;
  feedback: string | null;
  submit: () => void;
}

function SessionidDialog({ sessionid, setSessionid, submitting, feedback, submit }: SDProps) {
  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <KeyRound className="size-4" /> Sessionid AtSign
        </DialogTitle>
        <DialogDescription>
          Lo prendi dai cookie del browser. Non ti serve la password, e non la salviamo.
        </DialogDescription>
      </DialogHeader>

      <ol className="space-y-2 text-sm text-muted-foreground">
        <li>
          1. Vai su{" "}
          <a className="text-primary underline-offset-2 hover:underline" href="https://www.instagram.com" target="_blank" rel="noreferrer">
            instagram.com
          </a>{" "}
          e fai login.
        </li>
        <li>2. Apri DevTools (<kbd>F12</kbd>) → tab <b>Application</b> (Chrome) o <b>Storage</b> (Firefox).</li>
        <li>3. <b>Cookies → instagram.com</b> → riga <code className="font-mono">sessionid</code> → copia il <b>Value</b>.</li>
        <li>4. Incolla qui sotto. Lascia la stringa così com'è (con i <code className="font-mono">%3A</code>).</li>
      </ol>

      <Input
        type="password"
        autoFocus
        placeholder="63872159526%3AMGIctF9A9e3wjb%3A2%3A…"
        value={sessionid}
        onChange={(e) => setSessionid(e.target.value)}
      />

      {feedback && (
        <div className="flex items-start gap-2 rounded-md border border-border bg-secondary px-3 py-2 text-sm">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>{feedback}</span>
        </div>
      )}

      <Button onClick={submit} disabled={!sessionid.trim() || submitting} className="w-full">
        {submitting ? "Verifico…" : "Salva e prova"}
      </Button>
    </DialogContent>
  );
}
