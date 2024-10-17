module.exports = {
  apps: [{
    name: "twitch-bot",
    script: "bot.py",
    interpreter: process.platform === "win32" ? "python" : "/home/actionsrunner/revbot/venv/bin/python",
    interpreter_args: "-u",  // Use unbuffered mode
    watch: false,  // Disable watch mode
    instances: 1,  // Explicitly set to 1 instance
    exec_mode: "fork",
    max_memory_restart: "1G",
    env: {
      NODE_ENV: "development",
      PYTHONUNBUFFERED: "1",
      PYTHONPATH: process.platform === "win32" ? "./env/Lib/site-packages" : "/home/actionsrunner/revbot/venv/lib/python3.11/site-packages"
    },
    env_production: {
      NODE_ENV: "production",
      PYTHONUNBUFFERED: "1",
      PYTHONPATH: process.platform === "win32" ? "./env/Lib/site-packages" : "/home/actionsrunner/revbot/venv/lib/python3.11/site-packages"
    },
    env_file: process.platform === "win32" ? ".env" : "/home/actionsrunner/revbot/.env",
    error_file: process.platform === "win32" ? "./logs/err.log" : "/home/actionsrunner/revbot/logs/err.log",
    out_file: process.platform === "win32" ? "./logs/out.log" : "/home/actionsrunner/revbot/logs/out.log",
    log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    restart_delay: 5000,
    autorestart: true,
    instance_var: 'INSTANCE_ID',
    merge_logs: true,
    max_restarts: 10,
    min_uptime: "1m",
    listen_timeout: 8000,
  }]
}