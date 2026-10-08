# GuidanceCast Trend Bot

A Telegram bot that finds what's trending in the Western Muslim world and suggests episode ideas for the GuidanceCast Podcast.

It's **free to run**:
- **Trends** come from public RSS feeds: Google News (UK, USA, Canada, Australia), 5Pillars, MuslimMatters, Hyphen, The Muslim Vibe, CAIR and Muslim subreddits. None of them need a key.
- **Analysis** uses Google's Gemini API on its free tier. You don't need a credit card.

## Commands

| Command | What it does |
|---|---|
| `/trends` | Hottest topics right now, with heat ratings and sources |
| `/ideas` | 5 episode ideas from what's trending |
| `/ideas marriage` | Episode ideas on a topic you choose |
| `/brief` | Full briefing: trends, pitches, upcoming dates |
| `/daily_on` / `/daily_off` | Get the briefing every morning |
| `/myid` | Shows your Telegram user ID |

## Setup (about 10 minutes)

1. **Create the bot.** In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token it gives you.
2. **Get a free Gemini key.** Go to <https://aistudio.google.com/apikey>, sign in with a Google account and create a key.
3. **Configure.** Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`.
4. **Install and run:**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python bot.py
   ```
5. **Lock it to you.** Send `/myid` to your bot. Put that number in `ALLOWED_USER_IDS` in `.env`, then restart. Add teammates' IDs separated by commas.

The bot only works while `python bot.py` is running. To keep it on all the time, run it on a computer that stays on, or a free always-on host such as an Oracle Cloud free VM.

## Run it 24/7 on a free server

1. Sign up for [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/). A card is needed to verify your identity, but Always Free resources are never charged.
2. Create a Compute instance: choose **Ubuntu** as the image and an **Always Free eligible** shape (Ampere A1 or VM.Standard.E2.1.Micro). Download the SSH key it offers.
3. Connect to the server from PowerShell: `ssh -i path\to\key ubuntu@<server-ip>`
4. On the server, run:
   ```
   git clone https://github.com/Saeed-Ahmad-20/Podcast-Bot.git
   cd Podcast-Bot
   bash deploy/setup.sh      # first run creates .env
   nano .env                 # paste your keys (Ctrl+O to save, Ctrl+X to exit)
   bash deploy/setup.sh      # second run starts the bot
   ```
5. Stop the copy on your own PC. Only one copy of the bot can run at a time.

The bot now starts automatically whenever the server boots, and restarts itself if it crashes. To install an update, run `git pull` and then `sudo systemctl restart guidancecast`.

## Good to know

- **Free-tier limits:** Gemini's free tier has daily request limits, which are plenty for a few briefings a day. If you hit one, the bot says so and you can try again later.
- **Privacy:** On the free tier, Google may use what you send to improve its products. The bot only sends public headlines and your requests, so nothing private goes to Google.
- **Reddit** sometimes rate-limits requests. When that happens, the bot skips those subreddits and uses the other sources.
- **Choosing sources:** Edit the feed and subreddit lists at the top of `sources.py`.
