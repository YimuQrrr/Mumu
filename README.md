# 🦊 Mumu Discord Bot

Mumu is a fox-themed Discord bot with chat, memory, image understanding, random heartbeats, sleep behavior, and voice-channel helpers.

## ✨ Features

- 💬 Chat with Mumu through mentions or `/ask`
- 🧠 Keep short-term chat history and persistent memory
- 🖼️ Read image attachments with a separate image-to-text API key
- 💓 Send occasional heartbeat messages based on activity level
- 💤 Enter sleep mode and react differently while sleeping
- 🔊 Join and leave voice channels
- 🍓 Track Mumu's berry count and mood-related state
- 🎨 Reply with configured custom emoji reactions

## ⚙️ Configuration

Copy `.env.example`, remove the `.example` suffix so the file name becomes `.env`, then fill in these values:

```env
OPENROUTER_API_KEY=your_chat_api_key_here
OPENROUTER_IMAGE_API_KEY=your_image_to_text_api_key_here
DISCORD_TOKEN=your_discord_bot_token_here
```

- `OPENROUTER_API_KEY` is used for normal chat and memory requests.
- `OPENROUTER_IMAGE_API_KEY` is used for image-to-text requests.
- `DISCORD_TOKEN` is used to start the Discord bot.

## 🚀 Run

Install the required Python packages, then start the bot:

```powershell
python bot.py
```

## 🧾 Slash Commands

| Command | Description |
| --- | --- |
| `/help` | Show available commands |
| `/ask` | Ask Mumu a private question |
| `/uptime` | Show how long Mumu has been running |
| `/sese` | Send a random image from the configured image source |
| `/sleep` | Show Mumu's sleep status |
| `/del` | Clear Mumu's chat memory |
| `/hb` | Set heartbeat activity from `0` to `100` |
| `/hbinfo` | Show current heartbeat activity |
| `/eat` | Show Mumu's berry count |
| `/join` | Make Mumu join your voice channel |
| `/leave` | Make Mumu leave the voice channel |
| `/dev` | Toggle developer/debug mode |

## 📁 Local Runtime Files

Mumu creates several local files while running:

- `messages.txt` for recent direct chat history
- `group_chat.txt` for recent group chat records
- `mumu_memory.txt` for persistent memory
- `heartbeat_active.txt` for saved heartbeat activity

These files are local runtime data and are not required for a fresh setup.
