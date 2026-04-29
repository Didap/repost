import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ExternalLink, Inbox, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, type PendingPost } from "@/lib/api";

interface Props {
  pending: PendingPost[];
  onChange: () => void;
}

const VIDEO = 2;
const ALBUM = 8;

export function PendingFeed({ pending, onChange }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Inbox className="size-4" /> In attesa di approvazione
          {pending.length > 0 && <Badge>{pending.length}</Badge>}
        </CardTitle>
        <CardDescription>
          I post nuovi delle pagine monitorate compaiono qui.
        </CardDescription>
      </CardHeader>

      <CardContent>
        {pending.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-4 py-12 text-center text-sm text-muted-foreground">
            Tutto vuoto. Quando le pagine monitorate posteranno, vedrai le card qui.
          </div>
        ) : (
          <motion.ul
            className="space-y-4"
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.04 } } }}
          >
            <AnimatePresence initial={false}>
              {pending.map((p) => (
                <PendingCard key={p.pk} post={p} onChange={onChange} />
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
      </CardContent>
    </Card>
  );
}

function PendingCard({ post, onChange }: { post: PendingPost; onChange: () => void }) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);

  async function approve() {
    setBusy("approve");
    try {
      await api.approve(post.pk);
      onChange();
    } finally {
      setBusy(null);
    }
  }

  async function reject() {
    setBusy("reject");
    try {
      await api.reject(post.pk);
      onChange();
    } finally {
      setBusy(null);
    }
  }

  const typeLabel = post.media_type === ALBUM ? "carosello" : post.media_type === VIDEO
    ? (post.product_type === "clips" ? "reel" : "video")
    : "foto";

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.18 } }}
      variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
      className="overflow-hidden rounded-lg border border-border bg-secondary/40"
    >
      <div className="flex flex-col md:flex-row">
        <div className="bg-black md:w-72 md:flex-shrink-0">
          <MediaPreview post={post} />
        </div>
        <div className="flex flex-1 flex-col p-4">
          <div className="flex items-center justify-between gap-2">
            <a
              href={`https://www.instagram.com/${post.target}/`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-sm font-mono hover:text-primary"
            >
              @{post.target}
            </a>
            <Badge variant="outline">{typeLabel}</Badge>
          </div>

          <p className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap text-sm text-muted-foreground">
            {post.caption || <i>(nessuna caption)</i>}
          </p>

          <div className="mt-auto flex items-center gap-2 pt-4">
            <Button onClick={approve} disabled={busy !== null} className="flex-1">
              <Check />
              {busy === "approve" ? "Pubblico…" : "Pubblica"}
            </Button>
            <Button onClick={reject} disabled={busy !== null} variant="outline" className="flex-1">
              <X />
              {busy === "reject" ? "Scarto…" : "Scarta"}
            </Button>
            <Button asChild variant="ghost" size="icon">
              <a href={post.instagram_url} target="_blank" rel="noreferrer" aria-label="Vedi originale">
                <ExternalLink />
              </a>
            </Button>
          </div>
        </div>
      </div>
    </motion.li>
  );
}

function MediaPreview({ post }: { post: PendingPost }) {
  const url = post.media_urls[0];
  if (!url) return <div className="aspect-square bg-secondary" />;

  if (post.media_type === VIDEO) {
    return (
      <video
        src={url}
        className="aspect-square h-full w-full object-cover"
        muted
        loop
        playsInline
        controls
      />
    );
  }
  return (
    <div className="relative">
      <img src={url} alt="" className="aspect-square h-full w-full object-cover" />
      {post.media_type === ALBUM && post.media_urls.length > 1 && (
        <div className="absolute right-2 top-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs text-white">
          1 / {post.media_urls.length}
        </div>
      )}
    </div>
  );
}
