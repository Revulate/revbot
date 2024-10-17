import asyncio
from bot import TwitchBot
from utils import setup_database


async def run_manual_tests():
    # Set up the database
    setup_database()
    log_info("Database setup complete.")

    bot = TwitchBot()

    # Test bot initialization
    log_info(f"Bot initialized with nick: {bot.nick}")
    log_info(f"Bot prefix: {bot._prefix}")

    # Test loading cogs
    log_info("Loading cogs...")
    bot.load_modules()
    log_info("Cogs loaded.")

    # Test TwitchAPI initialization
    log_info(f"TwitchAPI initialized with client_id: {bot.twitch_api.client_id}")

    # Test token refresh
    log_info("Testing token refresh...")
    try:
        await asyncio.wait_for(bot.ensure_valid_token(), timeout=10)
        log_info("Token refresh complete.")
    except asyncio.TimeoutError:
        log_info("Token refresh timed out.")
    except Exception as e:
        log_info(f"Error during token refresh: {e}")

    # Give some time for cogs to initialize
    await asyncio.sleep(2)

    # Cleanup
    try:
        await bot.close()
        log_info("Bot closed successfully.")
    except Exception as e:
        log_info(f"Error during bot closure: {e}")

    # Ensure all tasks are completed
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Close the event loop
    loop = asyncio.get_event_loop()
    loop.stop()
    loop.close()


if __name__ == "__main__":
    asyncio.run(run_manual_tests())
