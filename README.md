# TwitchIO Chatbot

## Overview

The TwitchIO Chatbot is designed to enhance interactivity and engagement within Twitch streams by providing a suite of automated commands and features directly in Twitch chat. The bot supports generating images, analyzing images, and responding to various user queries through OpenAI's ChatGPT and DALL-E 3. This integration helps streamers deliver engaging content, answer viewer questions, and even provide real-time image generation based on viewer prompts.

## Key Features

- **Dynamic Command Handling:** Utilize TwitchIO’s command system to manage, create, and execute custom commands in chat effortlessly.
- **Modular Architecture with Cogs:** Organize bot functionalities into separate modules (cogs) for maintainability, scalability, and cleaner code.
- **`#ask` Command with OpenAI Integration:**
  - **ChatGPT Responses:** Provide context-aware, intelligent responses to viewer questions using OpenAI's ChatGPT.
  - **Image Generation:** Generate images on the fly via DALL-E 3 based on user prompts that start with `Create`.
  - **Image Analysis:** Analyze images via OpenAI Vision and return descriptive feedback on the content of the image.
- **Image Hosting Integration:** Automatically uploads generated images to a custom image hosting service (Nuuls) and returns shortened URLs, ensuring clean and manageable links in chat.
- **Rate Limiting and Caching:** Efficiently manage API calls and improve performance through rate limiting and response caching mechanisms.
- **Robust Error Handling:** Ensure smooth operation with detailed error logging and user-friendly error messages.
- **Logging:** Maintain comprehensive logs for debugging and monitoring bot activities to ensure reliability and responsiveness.
- **Security Features:** Limit certain commands to authorized users (e.g., streamers, moderators) to prevent misuse.
- **Personalized System Prompts:** Tailor the bot's personality to match the desired tone and behavior for your stream, such as friendly anime-inspired interactions.

## Prerequisites

- **Python 3.8 or higher**
- **Twitch Account** with developer access to create and manage bots.
- **OpenAI Account** with API access for both ChatGPT and DALL-E 3.
- **Nuuls API Key** for uploading and sharing image URLs.

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