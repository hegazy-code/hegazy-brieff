# Hegazy Brief

A daily world-intelligence website in a “night to morning” design: the night opens with the market closings in Cairo time and your promise (“I don’t guess what the world is doing. I know.”), a dusk band shows how the night reaches Egyptians’ pockets, and a calm morning section holds every story by sector, with a region filter, a “Top stories only” switch, charts, the markets board, a risk radar, the coming week and terms to learn. English, Arabic or both, at the press of a button. It rebuilds itself every morning before 8 AM Cairo time and costs nothing to run.

Made by Youssef Hegazy.

## How it works

1. **Checklist research.** `config.yaml` holds 35 checklist lines (A1 to A16, with all 15 politics categories). Every line runs its own news searches (English and Arabic) and RSS feeds every day.
2. **Market data.** About 70 symbols from Yahoo Finance: world indices, the 11 US sectors, your watchlist, bond yields, currencies, commodities and crypto. Every number on the site comes from here, never from the AI.
3. **Writing and ranking.** Gemini (free tier) writes the stories and ranks them HIGH, MEDIUM or LOW using fixed rules. It can only cite headlines the site collected, by id; links and photos are attached by code, so it can't invent a source. Stories without a valid source are dropped.
4. **Caps enforced by code.** Maximum 8 HIGH stories per edition (extra ones become MEDIUM) and 8 one-line radar items per sector.
5. **Private coverage report.** Every checklist line is marked COVERED, NOT PUBLISHED (found but low impact) or NOT FOUND. It is emailed only to you and never appears on the website or in the repository.
7. **Big numbers are verified.** A card only shows its big number if those digits appear in the cited headlines or in Yahoo Finance data; otherwise the number is hidden.
6. **Photos** come only from the photo fields that news feeds publish for syndication, each credited and linked to its source.

## Made for beginners and experts

- **Tap-to-explain words.** `glossary.yaml` holds about 55 terms (Brent, bond yield, IPO, current account, remittances…) with simple English and Arabic explanations. Each term is underlined once per story; one tap explains it without leaving the page. Every morning the AI also suggests new terms from that day's stories, and they're added for that edition. Add permanent terms to `glossary.yaml` any time.
- **“New to markets?” guide** at the top of the morning section: how to read the numbers, colors and stories.
- **Ask Hegazy Brief.** A chat assistant that answers any question about the day's news in simple English or Arabic, using that day's stories first. It never gives buy or sell advice.

## Sources

- **Official sources first.** Direct feeds from the US Federal Reserve, the European Central Bank, the Bank of England, the US SEC, the US Bureau of Labor Statistics, the US Energy Information Administration and the United Nations, plus searches restricted to the Central Bank of Egypt, the EGX, Egypt's Financial Regulatory Authority, the Cabinet, the Ministry of Finance, the Suez Canal Authority, CAPMAS, the IMF, the World Bank, OPEC, the IEA, the WTO and other central banks. Headlines from these are marked official, the AI must prefer them, and they are labelled "(official)" on the site.
- **Egyptian outlets in Arabic and English** (Al Mal, Al Borsa, Amwal Al Ghad, Youm7) for Egypt's markets, companies and economy.
- **International media** (BBC, CNBC, Al Jazeera and Google News searches, including Wall Street Journal headlines).
- **Free data:** Yahoo Finance (about 70 market symbols), ECB reference exchange rates through Frankfurter, CoinGecko for the total crypto market, and FRED (St. Louis Fed) for US Treasury yields, the Fed's target rate and unemployment.

About 190 searches and feeds run every morning across the 35 checklist lines.

Some official sites (like the Central Bank of Egypt) don't publish feeds, so they are reached through search; if they come up empty in the coverage report, that is the reason.

## Setup (about 20 minutes)

1. Create a free GitHub account and a new repository called `hegazy-brief`. Upload every file from this folder, including the hidden `.github` folder.
2. Get a free API key at aistudio.google.com. Check the free-tier limits and model names there; Google changes them.
3. Repository Settings, then Secrets and variables, then Actions: add a secret `GEMINI_API_KEY`. If the default model name stops working, add a variable `GEMINI_MODEL` with a current model name.
4. Settings, then Pages: source "Deploy from a branch", branch `main`, folder `/docs`.
5. US data from FRED (free): create an account at fred.stlouisfed.org, request an API key, and add it as the secret `FRED_API_KEY`. Without it, those rows show “no data.”
6. Private coverage email (optional but recommended): in your Google account, turn on 2-step verification and create an App Password (search "Google App Passwords"). Add three more secrets: `SMTP_USER` (your Gmail address), `SMTP_PASS` (the 16-character app password, not your normal password) and `NOTIFY_TO` (where to send the report).
7. Actions tab, "Build Hegazy Brief", "Run workflow". Your site appears at `https://YOUR-USERNAME.github.io/hegazy-brief/`.

## Turning on the assistant (optional, about 15 minutes)

The assistant needs a small server so your Gemini key stays hidden (a key inside a public website would be stolen). Cloudflare Workers run it free for normal traffic.

1. Create a free account at cloudflare.com, open Workers & Pages, and create a Worker.
2. Replace its code with everything in `worker/chat-worker.js`, then deploy.
3. In the Worker's Settings, add a secret `GEMINI_API_KEY` (your Gemini key) and a variable `ALLOWED_ORIGIN` (your site's address, for example `https://your-username.github.io`).
4. Copy the Worker's address (it ends in `.workers.dev`) into `chat_endpoint` in `config.yaml` and save. From the next edition, the “Ask Hegazy Brief” button appears.

The server limits each visitor to 8 questions a minute. Free AI tiers have daily limits; if many people use the assistant, you'll need a paid plan. Answers are AI-generated and can be wrong, which the chat window says.

## Test locally

```
pip install -r requirements.txt
python build.py --mock    # design preview with sample data, no internet
python build.py           # live edition
```

## Maintenance

- **Clock change:** update the cron line in `.github/workflows/daily.yml` when Egypt changes its clocks.
- **"No data" on the board:** look the symbol up on finance.yahoo.com and fix it in `config.yaml`. New listings (like HALN) can take days to appear.
- **A checklist line keeps showing NOT FOUND:** improve its search words in `config.yaml`.
- **Gulf indices:** only Saudi TASI is on the board because Yahoo symbols for Abu Dhabi, Dubai, Qatar and Kuwait are unreliable. Their news is still covered by checklist line A2.4.
- **Free-tier limits:** each edition makes 8 Gemini calls. If you hit rate limits, the code waits and retries; if it still fails, that sector falls back to one-line headlines.
- Free GitHub Pages sites are public. To keep it private, host the `docs` folder on Cloudflare Pages with Cloudflare Access.
