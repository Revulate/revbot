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
    },
    env_file: "/home/actionsrunner/revbot/.env",
    error_file: "/home/actionsrunner/revbot/logs/err.log",
    out_file: "/home/actionsrunner/revbot/logs/out.log",
    log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    restart_delay: 5000, // 5 seconds
    autorestart: true,
    instance_var: 'INSTANCE_ID',
    merge_logs: true,
    monitoring: true,
  }]
}