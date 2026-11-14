# Security checklist (things only you can do)

Nothing can guarantee you'll never be hacked. These steps make sure a break-in or a bug can only do limited damage and that you hear about it fast. Tick them off in order; the first section is worth doing today, even before any broker account exists.

## 1. Lock down the accounts you already have (30 minutes)

- [ ] Install a password manager (1Password or Bitwarden) and give every account below its own long, random password.
- [ ] Install an authenticator app (Aegis, 2FAS or Google Authenticator), or buy two hardware keys (YubiKey) and keep one as a spare.
- [ ] **GitHub**: Settings → Password and authentication → turn on two-factor with the app or key. Save the recovery codes in the password manager.
- [ ] **Email**: create a new address used only for broker, exchange and GitHub. Turn on two-factor with the app or key, not SMS.
- [ ] **Mobile carrier**: ask for a port-out lock / PIN on your number, so nobody can move your number to their SIM.
- [ ] **This repository**: Settings → Code security → turn on Dependabot alerts, Secret scanning and Push protection.

## 2. When you open the broker and exchange accounts

- [ ] Stocks: Interactive Brokers Australia (ASIC regulated). Bitcoin: an AUSTRAC-registered exchange such as Kraken, Independent Reserve or BTC Markets. Sign up by typing the address yourself, never from a link in an email, ad or DM.
- [ ] Register with the dedicated email, a unique password and app or hardware-key two-factor.
- [ ] Turn on every alert offered: logins, new devices, API key changes, withdrawals.
- [ ] Exchange: turn on the **withdrawal address allow-list** and add only your own bank account and wallet. Turn on the waiting period for new addresses if offered.
- [ ] Start with the paper / demo account. Deposit nothing until Phase 3.

## 3. API keys (when we reach Phase 3)

- [ ] Create a key with **trading permission only. Withdrawals and transfers OFF.**
- [ ] Restrict the key to the server's IP address.
- [ ] Paste the key only into the server's secret store. Never into chat, email, a screenshot, or this repository.
- [ ] Separate keys for paper and live. Rotate every 3 months, or immediately if anything looks odd.

## 4. Money rules

- [ ] Only money the bot is allowed to trade sits in the trading accounts. Savings stay in your bank.
- [ ] Bitcoin you aren't actively trading goes to a hardware wallet (Ledger, Trezor) bought from the manufacturer. The recovery phrase is written on paper, never typed into a computer or photographed.
- [ ] Decide the most you're prepared to lose, write it down, and never top up after a loss.

## 5. Scams to expect

- Nobody from a broker, exchange, GitHub or "support" will ever ask for your password, two-factor code, recovery phrase or API secret. Anyone who does is a scammer.
- "Comment for access", paid signal groups, bots for sale and guaranteed returns are how most new traders lose money. Bring anything like that here to be checked first.
- Never install software or browser extensions recommended in a trading video or DM.

## 6. Every week (5 minutes)

- [ ] Trade log matches the broker's and exchange's own history.
- [ ] No API keys, devices or logins you don't recognise.
- [ ] Balances are what you expect.
