import time

class Watch:
    @staticmethod
    def format_duration(seconds):
        """Formats the duration from seconds to days, hours, minutes, and seconds."""
        weeks, remainder = divmod(seconds, 604800)  # 604800 seconds in a week
        days, remainder = divmod(remainder, 86400)  # 86400 seconds in a day
        hours, remainder = divmod(remainder, 3600)  # 3600 seconds in an hour
        minutes, seconds = divmod(remainder, 60)  # 60 seconds in a minute
        return int(weeks), int(days), int(hours), int(minutes), int(seconds)

    @staticmethod
    def get_afk_duration(start_time):
        """Calculates the AFK duration in seconds."""
        current_time = time.time()
        return current_time - start_time
