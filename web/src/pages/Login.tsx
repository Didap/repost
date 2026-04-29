import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

interface Props {
  onAuthed: (email: string) => void;
}

export function LoginPage({ onAuthed }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const r = await api.login(email, password);
      onAuthed(r.user.email);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Email o password sbagliata" : "Errore di connessione");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="mb-8 flex flex-col items-center gap-4">
          <div className="blob h-16 w-16" aria-hidden />
          <div className="text-center">
            <h1 className="text-3xl font-semibold tracking-tight">
              <span className="text-gradient">Repost</span>
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Monitora pagine Instagram e ripubblica con un click
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded-lg border border-border bg-card p-6">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoFocus
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="tu@example.com"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={loading || !email || !password}>
            {loading ? "Verifico…" : "Entra"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          Solo gli admin possono creare nuovi account dalla dashboard.
        </p>
      </motion.div>
    </div>
  );
}
