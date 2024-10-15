import asyncio
from bot import TwitchBot
from utils import setup_database


async def run_manual_tests():
    # Set up the database
    setup_database()
    print("Database setup complete.")

    bot = TwitchBot()

    # Test bot initialization
    print(f"Bot initialized with nick: {bot.nick}")
    print(f"Bot prefix: {bot._prefix}")

    # Test loading cogs
    print("Loading cogs...")
    bot.load_modules()
    print("Cogs loaded.")

    # Test TwitchAPI initialization
    print(f"TwitchAPI initialized with client_id: {bot.twitch_api.client_id}")

    # Test token refresh
    print("Testing token refresh...")
    try:
        await asyncio.wait_for(bot.ensure_valid_token(), timeout=10)
        print("Token refresh complete.")
    except asyncio.TimeoutError:
        print("Token refresh timed out.")
    except Exception as e:
        print(f"Error during token refresh: {e}")

    # Give some time for cogs to initialize
    await asyncio.sleep(2)

    # Cleanup
    try:
        await bot.close()
        print("Bot closed successfully.")
    except Exception as e:
        print(f"Error during bot closure: {e}")

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
