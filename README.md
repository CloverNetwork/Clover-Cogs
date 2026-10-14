# Clover-Cogs

A collection of cogs for [Red Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot).

## Installation

```
[p]repo add clover-cogs https://github.com/CloverNetwork/Clover-Cogs
[p]cog install clover-cogs giveaway
[p]load giveaway
```

Replace `[p]` with your bot's prefix.

## Cogs

### Giveaway

Run giveaways with entry reactions, automatic winner selection, rerolls, and embeds.

| Command | Description |
|---|---|
| `[p]giveaway start <duration> <winners> <prize>` | Start a giveaway. Duration accepts a combination like `1d2h30m`, `45m`, or `30s`. |
| `[p]giveaway end <message_id>` | End a giveaway early and pick winners. |
| `[p]giveaway reroll <message_id> [winners]` | Pick new winner(s) from an ended giveaway's entrants. |
| `[p]giveaway list` | List all active giveaways in the server. |

Users enter by reacting to the giveaway embed with 🎉. Starting and ending giveaways requires Manage Server permission (or bot admin).

**Example**

```
[p]giveaway start 1h30m 2 Nitro Classic
```

Starts a giveaway for 2 winners of "Nitro Classic" that ends in 1 hour and 30 minutes.

### Minecraft Status

Tracks a Minecraft Java server and posts a live-updating status embed with a colored MOTD, server icon, player count/sample, version, and latency.

| Command | Description |
|---|---|
| `[p]mcserver address <ip[:port]>` | Set the Minecraft server address to track. |
| `[p]mcserver channel [#channel]` | Set the channel for the live status embed (defaults to current channel) and posts it immediately. |
| `[p]mcserver interval <seconds>` | Set how often the embed auto-refreshes (minimum 60s, default 300s). |
| `[p]mcserver refresh` | Force an immediate refresh of the live embed. |
| `[p]mcserver stop` | Disable automatic updates. |
| `[p]mcserver status [ip[:port]]` | One-off status check, sent as a new message. Uses the configured address if none is given. |

Setting and managing the tracked server requires Manage Server permission (or bot admin). The embed shows offline servers in red and online servers in green, and requires the `mcstatus` package (installed automatically by the Downloader).

**Example**

```
[p]mcserver address play.example.com
[p]mcserver channel #server-status
```

## Requirements

- Red-DiscordBot 3.5.0+
- Python 3.8+

## License

No license specified.
