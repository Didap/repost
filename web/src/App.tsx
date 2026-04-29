import { useEffect, useState } from "react";
import { LoginPage } from "@/pages/Login";
import { Dashboard } from "@/pages/Dashboard";
import { api } from "@/lib/api";

type AppState =
  | { kind: "loading" }
  | { kind: "login" }
  | { kind: "dashboard"; email: string };

export default function App() {
  const [state, setState] = useState<AppState>({ kind: "loading" });

  useEffect(() => {
    api.session()
      .then((s) => {
        if (s.authed && s.user) setState({ kind: "dashboard", email: s.user.email });
        else setState({ kind: "login" });
      })
      .catch(() => setState({ kind: "login" }));
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="blob h-10 w-10" aria-hidden />
      </div>
    );
  }

  if (state.kind === "login") {
    return <LoginPage onAuthed={(email) => setState({ kind: "dashboard", email })} />;
  }

  return <Dashboard userEmail={state.email} onLogout={() => setState({ kind: "login" })} />;
}
