module.exports = {
    apps: [{
      name: "twitch-bot",
      script: "bot.py",
      interpreter: process.platform === "win32" ? "python" : "/home/actionsrunner/revbot/venv/bin/python",
      watch: true,
      ignore_watch: ["node_modules", "logs"],
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "development",
        PYTHONUNBUFFERED: "1"
      },
      env_production: {
        NODE_ENV: "production",
        PYTHONUNBUFFERED: "1"
      }
    }]
  }