# Repost

Monitora una pagina Instagram e ti chiede su Telegram, post per post, se ripubblicarla sul tuo account. Premi **✅ Pubblica** o **❌ Scarta** e il bot fa il resto.

> **Nota**: produce un **post nuovo** sul tuo profilo (con foto/video/caption identici), NON un "repost" con overlay di attribuzione.

## Come funziona l'autenticazione

Il bot **non conosce mai la tua password**. Si autentica usando il `sessionid` cookie del tuo browser quando fai login a `instagram.com`. Questo perché:

- **Funziona** anche da server (Coolify, VPS) senza far scattare i challenge anti-bot di Instagram
- **Sicuro**: la password resta nel browser, non passa né dal codice né da Coolify
- **Refresh facile**: quando IG fa scadere la sessione, mandi un comando Telegram con un nuovo sessionid e riparte

## Come prendere il sessionid (~30 sec)

1. Vai su [instagram.com](https://www.instagram.com) e fai login con l'account su cui vuoi pubblicare
2. Apri DevTools (F12), tab **Application** (Chrome) o **Storage** (Firefox)
3. **Cookies → instagram.com** → cerca la riga `sessionid` → copia il **Value**
4. Su Telegram, manda al bot: `/auth INCOLLA_QUI_IL_SESSIONID`

Il bot ti risponde `✅ Autenticato come @tuo_username` e parte.

## Setup locale (sviluppo)

```bash
brew install python@3.12 ffmpeg
cd /Users/w/Repost
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # poi compila i 3 valori principali
python -m src.main
```

Il bot Telegram parte subito e ti chiede `/auth <sessionid>`. Da quel momento è operativo.

## Setup su Coolify (produzione)

### Prerequisiti
- Repository Git (GitHub/GitLab/Gitea) con il codice
- Coolify v4

### Steps

1. **Push il codice su un repo git** (privato consigliato)

2. In Coolify: **+ New → Resource → Public/Private Repository**

3. **Build pack**: scegli `Docker Compose`. Coolify rileva il `docker-compose.yml`.

4. **Environment variables** (sezione Configuration):
   - `IG_TARGET_USERNAME` = `politichegiovanili_puglia`
   - `TELEGRAM_BOT_TOKEN` = `123456:ABC...`
   - `TELEGRAM_CHAT_ID` = `123456789`
   - `POLL_INTERVAL_SECONDS` = `600` *(opzionale)*
   - `SKIP_INITIAL` = `true` *(opzionale)*

   **Non** mettere `IG_SESSIONID` — userai `/auth` da Telegram.

5. **Persistent storage**: il `docker-compose.yml` definisce un volume `repost_data` per `/app/data`. Coolify lo gestisce automaticamente. Verifica che sia presente sotto *Storage*. Questo volume conserva la sessione IG, lo storico dei post visti e i pending — sopravvive ai redeploy.

6. **Deploy**.

7. Su Telegram, manda al bot `/start`. Ti chiederà il sessionid. Mandagli `/auth <sessionid>` (vedi sopra come ricavarlo) e via.

### Cosa aspettarsi nei logs

```
INFO src.telegram_bot: Telegram bot started
INFO src.main: Trying bootstrap sessionid from env  (solo se hai settato IG_SESSIONID)
INFO src.orchestrator: Orchestrator paused: waiting for /auth
... [tu mandi /auth da Telegram] ...
INFO src.instagram_client: Authenticated via sessionid as @galattica_nododibrindisi
INFO src.orchestrator: Orchestrator resumed: auth ready
INFO src.orchestrator: Polling @politichegiovanili_puglia …
```

## Comandi del bot Telegram

| Comando | Cosa fa |
|---|---|
| `/start` | info / istruzioni auth se non sei autenticato |
| `/status` | stato attuale (autenticato? quanti pending?) |
| `/auth <sessionid>` | login / refresh sessione |
| `/pending` | rimanda i post in attesa (utile dopo riavvio o se hai perso un messaggio) |

## Quando la sessione scade

Tipicamente dopo settimane/mesi, oppure se logghi su un altro device dal browser. Sintomi:
- Il bot ti scrive: `⚠️ La sessione Instagram non è più valida. Manda /auth <nuovo_sessionid>`
- Il polling si ferma automaticamente

Cosa fare:
1. Vai su [instagram.com](https://www.instagram.com), recupera un nuovo `sessionid`
2. Mandalo al bot: `/auth <nuovo_sessionid>`
3. Riparte da solo

## Caveat IP

Coolify gira su Hetzner = IP datacenter tedesco. Instagram lo riconosce come "non residenziale" e ogni tanto invalida la sessione più aggressivamente (giorni invece di mesi). È normale. Tu rifai `/auth` quando capita.

Se vuoi minimizzare i refresh:
- Quando prendi il sessionid, fallo dallo **stesso IP/rete** in cui usi normalmente IG (residenziale italiano)
- Evita di fare logout/login da altri device contemporaneamente

## Layout del codice

```
src/
├── config.py            # carica .env
├── state.py             # JSON state: post visti + approvazioni in sospeso
├── instagram_client.py  # wrapper instagrapi (login_by_sessionid, fetch, download, upload)
├── telegram_bot.py      # bot, gestisce ✅/❌ e /auth
├── orchestrator.py      # loop di polling, gestisce auth invalida
└── main.py              # entrypoint async
Dockerfile               # python:3.12-slim + ffmpeg
docker-compose.yml       # volume persistente per /app/data
```

## Sviluppo locale con Docker

```bash
docker compose up --build
```

Volume `repost_data` montato su `./data` (visibile sul tuo filesystem in `data/`).
