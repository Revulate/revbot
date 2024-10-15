# TwitchIO Chatbot

## Overview

The TwitchIO Chatbot is an advanced, AI-powered bot designed to enhance interactivity and engagement within Twitch streams. It provides a suite of automated commands and features directly in Twitch chat, including image generation, image analysis, and intelligent responses to user queries through OpenAI's ChatGPT and DALL-E 3 integration. This bot helps streamers deliver engaging content, answer viewer questions, and provide real-time image generation based on viewer prompts.

## Key Features

- **Dynamic Command Handling:** Utilize TwitchIO's command system to manage, create, and execute custom commands in chat effortlessly.
- **Modular Architecture with Cogs:** Organize bot functionalities into separate modules (cogs) for maintainability, scalability, and cleaner code.
- **`#ask` Command with OpenAI Integration:**
  - **ChatGPT Responses:** Provide context-aware, intelligent responses to viewer questions using OpenAI's ChatGPT.
  - **Image Generation:** Generate images on the fly via DALL-E 3 based on user prompts that start with `Create`.
  - **Image Analysis:** Analyze images via OpenAI Vision and return descriptive feedback on the content of the image.
- **Image Hosting Integration:** Automatically uploads generated images to a custom image hosting service (Nuuls) and returns shortened URLs, ensuring clean and manageable links in chat.
- **Rate Limiting and Caching:** Efficiently manage API calls and improve performance through rate limiting and response caching mechanisms.
- **Robust Error Handling:** Ensure smooth operation with detailed error logging and user-friendly error messages.
- **Comprehensive Logging:** Maintain detailed logs for debugging and monitoring bot activities to ensure reliability and responsiveness.
- **Security Features:** Limit certain commands to authorized users (e.g., streamers, moderators) to prevent misuse.
- **Personalized System Prompts:** Tailor the bot's personality to match the desired tone and behavior for your stream, such as friendly anime-inspired interactions.
- **Continuous Integration/Continuous Deployment (CI/CD):** Automated deployment pipeline using GitHub Actions for seamless updates and maintenance.

## Prerequisites

- Python 3.11 or higher
- Twitch Account with developer access to create and manage bots
- OpenAI Account with API access for both ChatGPT and DALL-E 3
- Nuuls API Key for uploading and sharing image URLs
- PM2 for process management (for production deployment)

## Installation

1. Clone the repository:
git clone https://github.com/Revulate/revbot.git
cd revbot
2. Create a virtual environment:
python -m venv venv
source venv/bin/activate  # On Windows, use venv\Scripts\activate
3. Install dependencies:
pip install -r requirements.txt
4. Set up environment variables:
Create a `.env` file in the root directory and add your API keys and other configuration. See the Configuration section for details.

5. Run the bot:
python bot.py
Copy
## Configuration

The bot is configured using environment variables. Create a `.env` file in the root directory with the following variables:
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
ACCESS_TOKEN=your_twitch_access_token
REFRESH_TOKEN=your_twitch_refresh_token
BOT_NICK=your_bot_nickname
TWITCH_CHANNELS=channel1,channel2
COMMAND_PREFIX=#
ADMIN_USERS=admin1,admin2
BOT_USER_ID=your_bot_user_id
BROADCASTER_USER_ID=broadcaster_user_id
LOG_LEVEL=INFO
LOG_FILE=bot.log
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=3
API_STEAM_KEY=your_steam_api_key
LOGDNA_INGESTION_KEY=your_logdna_key
OPENAI_API_KEY=your_openai_api_key
WEATHER_API_KEY=your_weather_api_key
NUULS_API_KEY=your_nuuls_api_key
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_CREDENTIALS_FILE=path_to_credentials.json
Copy
## Usage

- **Basic ChatGPT Query:**  
  `#ask <question>`  
  Example: `#ask What's the weather like in Tokyo?`

- **Image Generation:**  
  `#ask Create <prompt>`  
  Example: `#ask Create a fantasy landscape with a purple sky and two moons.`

- **Image Analysis:**  
  `#ask <question> <image_url>`  
  Example: `#ask Who is this? https://i.nuuls.com/abcd.png`

## Deployment

The bot is set up to be deployed using PM2 on a Raspberry Pi. The deployment process is automated using GitHub Actions.

1. Ensure PM2 is installed globally:
npm install -g pm2
Copy
2. Use the provided `ecosystem.config.js` file to manage the bot with PM2:
pm2 start ecosystem.config.js
Copy
3. To ensure the bot starts on system reboot:
pm2 startup
pm2 save
Copy
## CI/CD Pipeline

The project includes a GitHub Actions workflow for Continuous Integration and Deployment. The workflow:

1. Runs on push to the main branch or via manual trigger.
2. Builds the project and runs tests.
3. Deploys the bot to a Raspberry Pi.
4. Sets up the environment and starts the bot using PM2.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Acknowledgements

- [TwitchIO](https://github.com/TwitchIO/TwitchIO)
- [OpenAI](https://openai.com/)
- [PM2](https://pm2.keymetrics.io/)