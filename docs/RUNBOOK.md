# Emergency runbook

Keep this somewhere you can reach from your phone. Work from the top; don't skip ahead.

## A. The bot is doing something wrong (odd trades, too many trades, big loss)

1. **Kill switch.** GitHub → Actions → **paper** → Run workflow → type a reason in `kill_reason` → Run. From a computer with the repo: `python -m trader.runner --kill "reason"`. The bot will then refuse every buy; it can still sell.
2. Once live trading exists: log in to the broker / exchange and cancel open orders and close positions by hand if you want out.
3. Tell Claude what you saw. Don't clear the kill switch until the cause is understood.
4. To clear it: delete the file `KILL` on the `paper-state` branch (or in the server's `state/` folder).

## B. You think an account or API key is compromised

Do these in order, as fast as you can:

1. **Broker / exchange: delete all API keys.** This cuts the bot and any thief off instantly.
2. **Broker / exchange: freeze withdrawals** if there's a button for it, and check the withdrawal allow-list for addresses you didn't add.
3. **Email: change the password** and sign out all other sessions. Email first, because it can reset everything else.
4. **Broker / exchange: change the password**, sign out other sessions, and re-check two-factor settings for devices you don't recognise.
5. **GitHub: change the password**, review Settings → Sessions and Settings → Applications, and remove anything unfamiliar.
6. **Call the broker / exchange** on the number from their official website and report it.
7. If money has gone: report to your bank immediately, to ReportCyber (cyber.gov.au/report) and to Scamwatch. For identity theft, IDCARE (1800 595 160) helps for free.

## C. You lost your phone or two-factor device

1. Use the recovery codes saved in your password manager to log in.
2. Remove the lost device from two-factor on email, broker, exchange and GitHub, then add the new one.
3. Call your carrier to block the SIM.

## D. A key was committed to the repository by mistake

1. Treat it as stolen, even though the repo is private: delete that key at the broker / exchange now and make a new one.
2. Tell Claude so the secret can be removed from the history.
