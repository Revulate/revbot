module.exports = {
  apps: [{
    name: "twitch-bot",
    script: "bot.py",
    interpreter: process.platform === "win32" ? "python" : "/home/actionsrunner/revbot/venv/bin/python",
    watch: true,
    ignore_watch: ["node_modules", "logs", "*.log", "*.db"],
    max_memory_restart: "1G",
    env: {
      NODE_ENV: "development",
      PYTHONUNBUFFERED: "1"
    },
    env_production: {
      NODE_ENV: "production",
      PYTHONUNBUFFERED: "1"
    },
    env_file: process.platform === "win32" ? ".env" : "/home/actionsrunner/revbot/.env",
    error_file: process.platform === "win32" ? "./logs/err.log" : "/home/actionsrunner/revbot/logs/err.log",
    out_file: process.platform === "win32" ? "./logs/out.log" : "/home/actionsrunner/revbot/logs/out.log",
    log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    restart_delay: 5000, // 5 seconds
    autorestart: true,
    instance_var: 'INSTANCE_ID',
    merge_logs: true,
    monitoring: true,
    max_restarts: 10,
    min_uptime: "1m",
    listen_timeout: 8000,
  }]
}