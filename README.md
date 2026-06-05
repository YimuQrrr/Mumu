# Mumu

Discord bot for Mumu.

## Configuration

Create a `.env` file in the project root and fill in these values:

```env
OPENROUTER_API_KEY=your_chat_api_key_here
OPENROUTER_IMAGE_API_KEY=your_image_to_text_api_key_here
DISCORD_TOKEN=your_discord_bot_token_here
```

- `OPENROUTER_API_KEY` is used for normal chat requests.
- `OPENROUTER_IMAGE_API_KEY` is used for image-to-text requests.
- `DISCORD_TOKEN` is used to start the Discord bot.

The `.env` file is ignored by Git and should not be pushed to GitHub.
