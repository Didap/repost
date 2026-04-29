import { useState, type FormEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { UserPlus, Users as UsersIcon, Trash2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api, type User } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

interface Props {
  users: User[];
  meEmail: string;
  onChange: () => void;
}

export function UsersPanel({ users, meEmail, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.createUser(email, password);
      setEmail("");
      setPassword("");
      setOpen(false);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore");
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(u: User) {
    if (u.email === meEmail) return;
    if (!confirm(`Rimuovere l'utente ${u.email}?`)) return;
    try {
      await api.deleteUser(u.id);
      onChange();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Errore");
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <UsersIcon className="size-4" /> Utenti dashboard
          </CardTitle>
          <CardDescription>
            Chi può accedere a questa dashboard. Tutti gli utenti hanno gli stessi permessi.
          </CardDescription>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <UserPlus /> Nuovo
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Crea nuovo utente</DialogTitle>
              <DialogDescription>
                Comunica tu la password al destinatario (al primo accesso può cambiarla — soon).
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="new-email">Email</Label>
                <Input id="new-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-password">Password (min 8)</Label>
                <Input id="new-password" type="text" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={submitting} className="w-full">
                {submitting ? "Creo…" : "Crea utente"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border rounded-md border border-border">
          <AnimatePresence initial={false}>
            {users.map((u) => (
              <motion.li
                key={u.id}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-center gap-3 px-4 py-3"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary text-xs font-semibold uppercase">
                  {u.email[0]}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">
                    {u.email}
                    {u.email === meEmail && (
                      <span className="ml-2 text-xs text-muted-foreground">(tu)</span>
                    )}
                  </p>
                  {u.created_at && (
                    <p className="text-xs text-muted-foreground">creato {formatRelative(u.created_at)}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(u)}
                  disabled={u.email === meEmail}
                  aria-label="Rimuovi"
                >
                  <Trash2 className="text-muted-foreground" />
                </Button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      </CardContent>
    </Card>
  );
}
