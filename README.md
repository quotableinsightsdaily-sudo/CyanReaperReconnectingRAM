# ☠ CyanReaper's RAM

A Roblox account manager for Windows. Run several accounts at once, rejoin any that drop, auto-click a button after reconnecting, and keep them from being kicked for idling.

## Features

- **Multiple accounts at once** – runs more than one Roblox window at the same time
- **Easy login** – log in through a fresh Chrome/Edge window, or paste a cookie
- **Auto reconnect** – checks if each account is still in the game and relaunches the ones that dropped
- **Auto-click** – after a reconnect, clicks a button you picked (3 clicks, one account at a time)
- **Anti-AFK** – taps space in every Roblox window so Roblox doesn't kick idle players
- **Tile** – arranges all Roblox windows in a grid
- **Themes** – several styles (glass, glossy, cartoon, retro, neon, clean) with colour choices

## Requirements

- Windows 10 or 11
- Roblox installed
- Chrome or Edge (only needed for the **+ Account** login button)

## Download

1. Go to the **Releases** page of this repo and download `CyanReapersRAM.zip`.
2. Right-click the zip → **Extract All...** and put the folder somewhere permanent, e.g. `Documents\CyanReapersRAM`. Don't run it from inside the zip.
3. If Windows blocks it: right-click `CyanReapersRAM.exe` → **Properties** → tick **Unblock** → **OK**.

> The exe is unsigned, so Windows SmartScreen or your antivirus may warn about it. Only download it from this repo's Releases page. If SmartScreen appears, click **More info → Run anyway**.

## How to use

**Before you start:** close every Roblox window completely, then open CyanReaper's RAM. It has to start first so it can allow multiple Roblox windows. If Roblox was already open, the top of the app tells you to close it and restart.

### 1. Add accounts
- Click **+ Account**, log in to Roblox in the window that opens, and the app adds the account and closes that window by itself.
- Or click **Paste cookie**, enter a name and the `.ROBLOSECURITY` cookie, then **Add**.
- Logging in again with an existing account just refreshes its cookie.

### 2. Choose the game
In the **Game** card click **Change** and enter the game's **Place ID** (numbers only).

### 3. Join and leave
- **Join / Leave** on an account starts or closes that account's Roblox window.
- **♥ Join** launches all accounts (about 8 seconds apart). **Leave all** closes them all.
- **Tile** arranges the Roblox windows on your screen.

### 4. Per-account switches
- **Rejoin** – let Auto reconnect bring this account back if it drops.
- **Event** – click your saved button after this account reconnects.
- ✎ edits the name or cookie, 🗑 removes the account.

### 5. Auto reconnect
Turn on **Rejoin accounts that drop** and set **Check every** (seconds). Dropped accounts are closed and relaunched. After repeated failures the app waits longer before trying again.

### 6. Auto-click after reconnecting
1. Turn on **Event** for the accounts that should click.
2. Click **Pick button**, then hover over the button in a Roblox window during the 5-second countdown.
3. Set **Wait ... s after reconnecting** so the game has time to load.
4. Click **Test** to try it on running Event accounts.

Keep other windows from covering the button while it runs.

### 7. Anti-AFK
Turn on **Anti-AFK** and set **Nudge every** to a number under 20 minutes. The app briefly focuses each Roblox window and taps space.

## ⚠ Keep your accounts file private

Accounts are saved next to the exe in `cyanreaper_ram.json`, and **cookies are stored in plain text**. Anyone with that file can log in as your accounts. Never share it or upload it to GitHub. If you fork this repo, add this to your `.gitignore`:

```
cyanreaper_ram.json
cyanreaper_ram.json.tmp
```

## Troubleshooting

| Problem | Fix |
|---|---|
| "Roblox already running" at the top | Close Roblox fully (check Task Manager), then restart the app |
| Account shows an expired cookie | Log in again with **+ Account** |
| "Chrome or Edge wasn't found" | Install one, or use **Paste cookie** |
| Auto-click doesn't hit the button | Re-do **Pick button**, and make sure nothing covers the button |
| App won't open | Install the Microsoft Visual C++ Redistributable (x64), or run the exe from Command Prompt to see the error |
| Exe disappears after building | Windows Defender removed it. Restore it in Windows Security → Protection history |

The **Activity** box in the app shows what it is doing and why something was skipped.

## Build from source

Requires Python 3 on Windows.

1. Put `cyanreaper_ram.py`, `requirements.txt` and `build.bat` in one folder. (Optional: add an `icon.ico` to use as the app icon.)
2. Double-click `build.bat`.
3. Your app is created at `dist\CyanReapersRAM.exe`.

To run without building:

```
pip install -r requirements.txt
python cyanreaper_ram.py
```

Dependencies: `pywebview`, `requests`, `psutil`, `websocket-client`.

## Disclaimer

This tool is not made by or affiliated with Roblox. Use it at your own risk and follow Roblox's Terms of Use. Only use accounts you own.
