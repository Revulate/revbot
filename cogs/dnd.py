# cogs/dnd.py

import random
import json
import asyncio
import logging
import sqlite3
from typing import Optional

from twitchio import PartialChatter  # Correctly import PartialChatter
from twitchio.ext import commands


logger = logging.getLogger('twitch_bot.cogs.dnd')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


class DnD(commands.Cog):
    """Cog for handling Dungeons & Dragons game features."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = 'twitch_bot.db'
        self._setup_database()
        self.user_states = {}  # Dictionary to track user states
        logger.info("DnD cog initialized.")

    def get_db_connection(self):
        """Establish a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def _setup_database(self):
        """Set up necessary tables in the SQLite database."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        # Create game_users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                race TEXT,
                character_class TEXT,
                background TEXT,
                level INTEGER DEFAULT 1,
                experience INTEGER DEFAULT 0,
                strength INTEGER DEFAULT 10,
                intelligence INTEGER DEFAULT 10,
                dexterity INTEGER DEFAULT 10,
                constitution INTEGER DEFAULT 10,
                wisdom INTEGER DEFAULT 10,
                charisma INTEGER DEFAULT 10,
                skills TEXT,  -- JSON array
                gear TEXT     -- JSON array
            )
        ''')
        # Create quests table (if needed)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quests (
                quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                rewards TEXT,
                requirements TEXT
            )
        ''')
        # Create parties table (if needed)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parties (
                party_id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_ids TEXT NOT NULL,  -- JSON array of user_ids
                status TEXT DEFAULT 'active'
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("DnD database setup completed.")

    def randomize_stats(self, character_class: str) -> dict:
        """Randomize stats based on character class."""
        if character_class.lower() == 'mage':
            return {
                'strength': random.randint(6, 12),
                'intelligence': random.randint(12, 18),
                'dexterity': random.randint(8, 14),
                'constitution': random.randint(8, 14),
                'wisdom': random.randint(10, 16),
                'charisma': random.randint(8, 14),
            }
        elif character_class.lower() == 'warrior':
            return {
                'strength': random.randint(12, 18),
                'intelligence': random.randint(6, 12),
                'dexterity': random.randint(10, 16),
                'constitution': random.randint(12, 18),
                'wisdom': random.randint(8, 14),
                'charisma': random.randint(8, 14),
            }
        elif character_class.lower() == 'rogue':
            return {
                'strength': random.randint(8, 14),
                'intelligence': random.randint(10, 16),
                'dexterity': random.randint(12, 18),
                'constitution': random.randint(8, 14),
                'wisdom': random.randint(8, 14),
                'charisma': random.randint(10, 16),
            }
        else:
            # Default stats if class is unrecognized
            return {
                'strength': random.randint(8, 16),
                'intelligence': random.randint(8, 16),
                'dexterity': random.randint(8, 16),
                'constitution': random.randint(8, 16),
                'wisdom': random.randint(8, 16),
                'charisma': random.randint(8, 16),
            }

    def create_character_entry(self, user_id: str, username: str, race: str, character_class: str, background: str, stats: dict):
        """Create a new character entry in the database."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO game_users (
                user_id, username, race, character_class, background,
                strength, intelligence, dexterity, constitution, wisdom, charisma,
                skills, gear
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            username,
            race,
            character_class,
            background,
            stats['strength'],
            stats['intelligence'],
            stats['dexterity'],
            stats['constitution'],
            stats['wisdom'],
            stats['charisma'],
            json.dumps([]),  # skills
            json.dumps([])   # gear
        ))
        conn.commit()
        conn.close()
        logger.info(f"Character created for user {username} (ID: {user_id}).")

    def get_user_character(self, user_id: str) -> Optional[dict]:
        """Retrieve a user's character from the database."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM game_users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))
        return None

    def is_user_in_party(self, user_id: str) -> bool:
        """Check if a user is already in a party."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM parties WHERE member_ids LIKE ?', (f'%"{user_id}"%',))
        row = cursor.fetchone()
        conn.close()
        return bool(row)

    def get_user_party(self, user_id: str) -> Optional[dict]:
        """Retrieve the party a user is in."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM parties WHERE member_ids LIKE ?', (f'%"{user_id}"%',))
        row = cursor.fetchone()
        conn.close()
        if row:
            columns = [column[0] for column in cursor.description]
            party = dict(zip(columns, row))
            party['member_ids'] = json.loads(party['member_ids'])
            return party
        return None

    async def get_usernames(self, user_ids: list) -> list:
        """Retrieve usernames for a list of user IDs."""
        usernames = []
        for uid in user_ids:
            try:
                user = await self.bot.fetch_users(ids=[int(uid)])
                if user:
                    usernames.append(user[0].name)
                else:
                    usernames.append("Unknown")
            except Exception as e:
                logger.error(f"Error fetching user ID '{uid}': {e}", exc_info=True)
                usernames.append("Unknown")
        return usernames

    # --- Commands ---

    @commands.command(name='create')
    async def create(self, ctx: commands.Context):
        """Initiate the character creation process."""
        user_id = str(ctx.author.id)
        username = ctx.author.name

        # Check if user already has a character
        if self.get_user_character(user_id):
            await ctx.send(f"@{username}, you already have a character. Use `#stats` to view your character.")
            return

        # Check if user is already in the process of creating a character
        if user_id in self.user_states:
            await ctx.send(f"@{username}, you're already in the process of creating a character. Please complete the current process before starting a new one.")
            return

        # Initialize user state
        self.user_states[user_id] = {'step': 'race'}
        await ctx.send(f"@{username}, welcome to character creation! Please choose your race using `#create_race <Race>`. Available races: Human, Elf, Dwarf, Orc.")

    @commands.command(name='create_race')
    async def create_race(self, ctx: commands.Context, race: str = None):
        """Choose race for character."""
        user_id = str(ctx.author.id)
        username = ctx.author.name

        # Check if user is in the creation process
        if user_id not in self.user_states or self.user_states[user_id].get('step') != 'race':
            await ctx.send(f"@{username}, to start creating a character, use `#create`.")
            return

        races = ['Human', 'Elf', 'Dwarf', 'Orc']
        if not race:
            await ctx.send(f"@{username}, please specify a race. Usage: `#create_race <Race>`. Available races: Human, Elf, Dwarf, Orc.")
            return

        if race.capitalize() not in races:
            await ctx.send(f"@{username}, invalid race. Available races: Human, Elf, Dwarf, Orc.")
            return

        # Update state
        self.user_states[user_id]['race'] = race.capitalize()
        self.user_states[user_id]['step'] = 'class'
        await ctx.send(f"@{username}, you chose **{race.capitalize()}**. Now, choose your class using `#create_class <Class>`. Available classes: Mage, Warrior, Rogue.")

    @commands.command(name='create_class')
    async def create_class(self, ctx: commands.Context, character_class: str = None):
        """Choose class for character."""
        user_id = str(ctx.author.id)
        username = ctx.author.name

        # Check if user is in the creation process
        if user_id not in self.user_states or self.user_states[user_id].get('step') != 'class':
            await ctx.send(f"@{username}, to create a class, use `#create` first.")
            return

        classes = ['Mage', 'Warrior', 'Rogue']
        if not character_class:
            await ctx.send(f"@{username}, please specify a class. Usage: `#create_class <Class>`. Available classes: Mage, Warrior, Rogue.")
            return

        if character_class.capitalize() not in classes:
            await ctx.send(f"@{username}, invalid class. Available classes: Mage, Warrior, Rogue.")
            return

        # Update state
        self.user_states[user_id]['class'] = character_class.capitalize()
        self.user_states[user_id]['step'] = 'background'
        await ctx.send(f"@{username}, you chose **{character_class.capitalize()}**. Now, choose your background using `#create_background <Background>`. Available backgrounds: Noble, Outlander, Scholar.")

    @commands.command(name='create_background')
    async def create_background(self, ctx: commands.Context, background: str = None):
        """Choose background for character."""
        user_id = str(ctx.author.id)
        username = ctx.author.name

        # Check if user is in the creation process
        if user_id not in self.user_states or self.user_states[user_id].get('step') != 'background':
            await ctx.send(f"@{username}, to create a background, use `#create` first.")
            return

        backgrounds = ['Noble', 'Outlander', 'Scholar']
        if not background:
            await ctx.send(f"@{username}, please specify a background. Usage: `#create_background <Background>`. Available backgrounds: Noble, Outlander, Scholar.")
            return

        if background.capitalize() not in backgrounds:
            await ctx.send(f"@{username}, invalid background. Available backgrounds: Noble, Outlander, Scholar.")
            return

        # Update state
        self.user_states[user_id]['background'] = background.capitalize()
        self.user_states[user_id]['step'] = 'finalize'

        # Finalize Character Creation
        race = self.user_states[user_id]['race']
        character_class = self.user_states[user_id]['class']
        background = self.user_states[user_id]['background']
        stats = self.randomize_stats(character_class)

        # Create and save the new character
        self.create_character_entry(user_id, username, race, character_class, background, stats)

        # Remove user from state tracker
        del self.user_states[user_id]

        # Confirm creation
        stats_display = (
            f"**Race:** {race} | **Class:** {character_class} | **Background:** {background} | "
            f"**Stats:** STR {stats['strength']}, INT {stats['intelligence']}, DEX {stats['dexterity']}, "
            f"CON {stats['constitution']}, WIS {stats['wisdom']}, CHA {stats['charisma']} 🎉"
        )
        await ctx.send(f"{username} has created a character! {stats_display}")

    @commands.command(name='stats', aliases=['profile'])
    async def view_stats(self, ctx: commands.Context):
        """View your current character's stats."""
        user_id = str(ctx.author.id)
        username = ctx.author.name
        character = self.get_user_character(user_id)

        if not character:
            await ctx.send(f"@{username}, you don't have a character yet. Use `#create` to create one.")
            return

        stats_display = (
            f"**Race:** {character['race']} | **Class:** {character['character_class']} | **Background:** {character['background']} | "
            f"**Level:** {character['level']} | **XP:** {character['experience']} \n"
            f"**Stats:** STR {character['strength']}, INT {character['intelligence']}, DEX {character['dexterity']}, "
            f"CON {character['constitution']}, WIS {character['wisdom']}, CHA {character['charisma']} \n"
            f"**Skills:** {', '.join(json.loads(character['skills'])) if character['skills'] else 'None'} \n"
            f"**Gear:** {', '.join(json.loads(character['gear'])) if character['gear'] else 'None'}"
        )
        await ctx.send(f"{username}'s Character Stats:\n{stats_display}")

    @commands.command(name='levelup')
    async def level_up(self, ctx: commands.Context, points: int = 1):
        """Allocate stat points upon leveling up."""
        user_id = str(ctx.author.id)
        username = ctx.author.name
        character = self.get_user_character(user_id)

        if not character:
            await ctx.send(f"@{username}, you don't have a character yet. Use `#create` to create one.")
            return

        required_xp = character['level'] * 100  # Example XP requirement
        if character['experience'] < required_xp:
            await ctx.send(f"@{username}, you need {required_xp - character['experience']} more XP to level up.")
            return

        if points < 1:
            await ctx.send(f"@{username}, you must allocate at least 1 point.")
            return

        # Deduct XP
        new_xp = character['experience'] - required_xp
        new_level = character['level'] + 1

        # Allocate points (for simplicity, randomly assign to stats)
        stats = {
            'strength': character['strength'],
            'intelligence': character['intelligence'],
            'dexterity': character['dexterity'],
            'constitution': character['constitution'],
            'wisdom': character['wisdom'],
            'charisma': character['charisma'],
        }

        for _ in range(points):
            stat_choice = random.choice(list(stats.keys()))
            stats[stat_choice] += 1

        # Update the character in the database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE game_users
            SET level = ?, experience = ?, strength = ?, intelligence = ?, dexterity = ?, constitution = ?, wisdom = ?, charisma = ?
            WHERE user_id = ?
        ''', (
            new_level,
            new_xp,
            stats['strength'],
            stats['intelligence'],
            stats['dexterity'],
            stats['constitution'],
            stats['wisdom'],
            stats['charisma'],
            user_id
        ))
        conn.commit()
        conn.close()

        await ctx.send(f"@{username} has leveled up to **Level {new_level}**! Your new stats are:\n"
                       f"STR {stats['strength']}, INT {stats['intelligence']}, DEX {stats['dexterity']}, "
                       f"CON {stats['constitution']}, WIS {stats['wisdom']}, CHA {stats['charisma']} 🎉")

    @commands.command(name='skillcheck')
    async def skill_check(self, ctx: commands.Context, skill: str = None, difficulty: int = None):
        """Perform a skill check."""
        if not skill or difficulty is None:
            await ctx.send(f"@{ctx.author.name}, please provide both a skill and a difficulty. Usage: `#skillcheck <skill> <difficulty>`.")
            return

        user_id = str(ctx.author.id)
        username = ctx.author.name
        character = self.get_user_character(user_id)

        if not character:
            await ctx.send(f"@{username}, you don't have a character yet. Use `#create` to create one.")
            return

        # Define skill to stat mapping
        skill_stat_map = {
            'arcana': 'intelligence',
            'stealth': 'dexterity',
            'athletics': 'strength',
            'perception': 'wisdom',
            'charisma': 'charisma',
            # Add more skills as needed
        }

        if skill.lower() not in skill_stat_map:
            await ctx.send(f"@{username}, the skill '{skill}' is not recognized.")
            return

        relevant_stat = skill_stat_map[skill.lower()]
        stat_value = character[relevant_stat]

        # Roll a d20
        roll = random.randint(1, 20)
        total = roll + (stat_value // 2)  # Example modifier

        success = total >= difficulty
        result = "succeeded" if success else "failed"

        emoji = "🎉" if success else "😞"

        await ctx.send(f"@{username} performed a **{skill}** check! (Roll: {roll} + {relevant_stat.upper()}: {stat_value // 2} = {total} vs {difficulty}) - **{result.upper()}** {emoji}")

    @commands.command(name='quest')
    async def start_quest(self, ctx: commands.Context):
        """Start a new quest."""
        user_id = str(ctx.author.id)
        username = ctx.author.name
        character = self.get_user_character(user_id)

        if not character:
            await ctx.send(f"@{username}, you don't have a character yet. Use `#create` to create one.")
            return

        # Generate a quest based on character level
        level = character['level']
        quest = self.generate_quest(level)

        # Save the quest to the database (optional for tracking)
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO quests (description, difficulty, rewards, requirements)
            VALUES (?, ?, ?, ?)
        ''', (
            quest['description'],
            quest['difficulty'],
            json.dumps(quest['rewards']),
            json.dumps(quest.get('requirements', {}))
        ))
        quest_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await ctx.send(f"@{username}, your quest: **{quest['description']}**")
        await ctx.send(f"Use `#skillcheck {quest['required_skill']} {quest['difficulty']}` to attempt the quest.")

    def generate_quest(self, level: int) -> dict:
        """Generate a procedurally generated quest based on player level."""
        # Define quest templates
        quest_templates = [
            {
                'description': 'Retrieve the ancient tome from the haunted library.',
                'difficulty': 15,
                'required_skill': 'arcana',
                'rewards': {'experience': 150, 'items': ['Ancient Tome']}
            },
            {
                'description': 'Defeat the shadow beast terrorizing the village.',
                'difficulty': 18,
                'required_skill': 'athletics',
                'rewards': {'experience': 200, 'items': ['Shadow Dagger']}
            },
            {
                'description': 'Explore the forgotten depths of the dark dungeon.',
                'difficulty': 25,
                'required_skill': 'perception',
                'rewards': {'experience': 300, 'items': ['Enchanted Armor']}
            },
            {
                'description': 'Secure the borders against the invading orc horde.',
                'difficulty': 12,
                'required_skill': 'stealth',
                'rewards': {'experience': 100, 'items': ['Stealth Cloak']}
            },
            # Add more templates as needed
        ]

        # Select a quest based on level
        if level < 5:
            available_quests = [q for q in quest_templates if q['difficulty'] <= 15]
        elif level < 10:
            available_quests = [q for q in quest_templates if 15 < q['difficulty'] <= 20]
        else:
            available_quests = [q for q in quest_templates if q['difficulty'] > 20]

        if not available_quests:
            available_quests = quest_templates  # Fallback

        quest = random.choice(available_quests)
        return quest

    @commands.command(name='attack')
    async def attack_enemy(self, ctx: commands.Context, enemy: str = None):
        """Attack an enemy."""
        if not enemy:
            await ctx.send(f"@{ctx.author.name}, please specify an enemy to attack. Usage: `#attack <enemy>`.")
            return

        user_id = str(ctx.author.id)
        username = ctx.author.name
        character = self.get_user_character(user_id)

        if not character:
            await ctx.send(f"@{username}, you don't have a character yet. Use `#create` to create one.")
            return

        # Simplified enemy stats (could be expanded or fetched from a database)
        enemies = {
            'goblin': {'strength': 8, 'health': 20},
            'troll': {'strength': 15, 'health': 50},
            'dragon': {'strength': 25, 'health': 200},
        }

        enemy_key = enemy.lower()
        if enemy_key not in enemies:
            await ctx.send(f"@{username}, enemy '{enemy}' not found. Available enemies: Goblin, Troll, Dragon.")
            return

        enemy_stats = enemies[enemy_key]
        enemy_health = enemy_stats['health']

        # Player attacks enemy
        player_roll = random.randint(1, 20) + (character['strength'] // 2)
        enemy_roll = random.randint(1, 20) + (enemy_stats['strength'] // 2)

        if player_roll > enemy_roll:
            damage = character['strength'] // 2
            enemy_health -= damage
            enemies[enemy_key]['health'] = enemy_health  # Update for this session
            if enemy_health > 0:
                await ctx.send(f"@{username} attacks {enemy} for {damage} damage! {enemy.capitalize()}'s health is now {enemy_health}. 🗡️")
            else:
                await ctx.send(f"@{username} has defeated {enemy}! 🎉 You gain 100 XP and find a **{random.choice(['Gold Coin', 'Healing Potion'])}**.")
                # Grant XP and items
                self.update_user_after_combat(user_id, xp=100, item=random.choice(['Gold Coin', 'Healing Potion']))
        else:
            await ctx.send(f"@{username}'s attack missed {enemy}! 😞")

    def update_user_after_combat(self, user_id: str, xp: int = 0, item: Optional[str] = None):
        """Update user's XP and add item to gear."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        # Update XP
        cursor.execute('''
            UPDATE game_users
            SET experience = experience + ?
            WHERE user_id = ?
        ''', (xp, user_id))

        # Add item to gear if provided
        if item:
            cursor.execute('SELECT gear FROM game_users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                gear = json.loads(row[0]) if row[0] else []
                gear.append(item)
                cursor.execute('''
                    UPDATE game_users
                    SET gear = ?
                    WHERE user_id = ?
                ''', (json.dumps(gear), user_id))

        conn.commit()
        conn.close()
        logger.info(f"User ID {user_id} gained {xp} XP and obtained item: {item}.")

    @commands.command(name='duel')
    async def duel_opponent(self, ctx: commands.Context, opponent: str = None):
        """Challenge another player to a duel."""
        if not opponent:
            await ctx.send(f"@{ctx.author.name}, please specify an opponent to duel. Usage: `#duel @opponent`.")
            return

        challenger_id = str(ctx.author.id)
        challenger_name = ctx.author.name

        # Fetch opponent user
        opponent_user = await self.fetch_user(ctx, opponent)
        if not opponent_user:
            await ctx.send(f"@{challenger_name}, opponent '{opponent}' not found.")
            return

        opponent_id = str(opponent_user.id)
        opponent_name = opponent_user.name

        # Check if opponent has a character
        if not self.get_user_character(opponent_id):
            await ctx.send(f"@{challenger_name}, opponent '{opponent_name}' does not have a character.")
            return

        # Check if challenger is already in a duel
        if self.is_user_in_duel(challenger_id):
            await ctx.send(f"@{challenger_name}, you're already in a duel.")
            return

        # Check if opponent is already in a duel
        if self.is_user_in_duel(opponent_id):
            await ctx.send(f"@{challenger_name}, opponent '{opponent_name}' is already in a duel.")
            return

        # Initiate duel
        await ctx.send(f"@{challenger_name} has challenged @{opponent_name} to a duel! @{opponent_name}, respond with `#acceptduel` to accept.")

        # Track the duel request
        self.duel_requests[(challenger_id, opponent_id)] = True

    @commands.command(name='acceptduel')
    async def accept_duel(self, ctx: commands.Context):
        """Accept a duel challenge."""
        user_id = str(ctx.author.id)
        username = ctx.author.name

        # Find if there's a duel request for this user
        duel_pair = None
        for (challenger_id, opponent_id), status in self.duel_requests.items():
            if opponent_id == user_id and status:
                duel_pair = (challenger_id, opponent_id)
                break

        if not duel_pair:
            await ctx.send(f"@{username}, you have no duel challenges to accept.")
            return

        challenger_id, opponent_id = duel_pair
        challenger_name = await self.get_username(challenger_id)
        opponent_name = username

        # Remove the duel request
        del self.duel_requests[duel_pair]

        # Simulate duel outcome
        challenger_character = self.get_user_character(challenger_id)
        opponent_character = self.get_user_character(opponent_id)

        challenger_roll = random.randint(1, 20) + (challenger_character['strength'] // 2)
        opponent_roll = random.randint(1, 20) + (opponent_character['strength'] // 2)

        if challenger_roll > opponent_roll:
            await ctx.send(f"@{challenger_name} has won the duel against @{opponent_name}! 🎉")
            # Grant rewards to challenger
            self.update_user_after_combat(challenger_id, xp=150, item="Duelist's Medal")
        elif challenger_roll < opponent_roll:
            await ctx.send(f"@{opponent_name} has won the duel against @{challenger_name}! 🎉")
            # Grant rewards to opponent
            self.update_user_after_combat(opponent_id, xp=150, item="Duelist's Medal")
        else:
            await ctx.send(f"The duel between @{challenger_name} and @{opponent_name} ended in a tie! 🤝")

    @commands.command(name='party')
    async def manage_party(self, ctx: commands.Context, action: str = None, user: str = None):
        """Manage parties: create, invite, status."""
        user_id = str(ctx.author.id)
        username = ctx.author.name

        if not action:
            await ctx.send(f"@{username}, please specify an action: create, invite, status.")
            return

        if action.lower() == 'create':
            # Check if user is already in a party
            if self.is_user_in_party(user_id):
                await ctx.send(f"@{username}, you are already in a party.")
                return

            # Create a new party with the user as the first member
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO parties (member_ids, status)
                VALUES (?, ?)
            ''', (json.dumps([user_id]), 'active'))
            party_id = cursor.lastrowid
            conn.commit()
            conn.close()

            await ctx.send(f"@{username} has created a new party! 🎉 Use `#party invite @user` to invite others.")

        elif action.lower() == 'invite':
            if not user:
                await ctx.send(f"@{username}, please specify a user to invite. Usage: `#party invite @user`")
                return

            # Check if inviter is in a party
            party = self.get_user_party(user_id)
            if not party:
                await ctx.send(f"@{username}, you are not in a party. Use `#party create` to create one.")
                return

            # Fetch the user to invite
            invitee = await self.fetch_user(ctx, user)
            if not invitee:
                await ctx.send(f"@{username}, user '{user}' not found.")
                return

            invitee_id = str(invitee.id)
            invitee_name = invitee.name

            # Check if invitee is already in a party
            if self.is_user_in_party(invitee_id):
                await ctx.send(f"@{username}, @{invitee_name} is already in a party.")
                return

            # Add invitee to the party
            party['member_ids'].append(invitee_id)
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE parties
                SET member_ids = ?
                WHERE party_id = ?
            ''', (json.dumps(party['member_ids']), party['party_id']))
            conn.commit()
            conn.close()

            await ctx.send(f"@{username} has invited @{invitee_name} to the party! 🎉")

        elif action.lower() == 'status':
            party = self.get_user_party(user_id)
            if not party:
                await ctx.send(f"@{username}, you are not in a party.")
                return

            member_ids = party['member_ids']
            member_names = await self.get_usernames(member_ids)
            members_display = ', '.join(member_names)
            await ctx.send(f"@{username}, your party members: {members_display}")

        else:
            await ctx.send(f"@{username}, unknown party action '{action}'. Available actions: create, invite, status.")

    @commands.command(name='inventory')
    async def view_inventory(self, ctx: commands.Context):
        """View your inventory of items."""
        user_id = str(ctx.author.id)
        username = ctx.author.name
        character = self.get_user_character(user_id)

        if not character:
            await ctx.send(f"@{username}, you don't have a character yet. Use `#create` to create one.")
            return

        gear = json.loads(character['gear']) if character['gear'] else []
        if gear:
            gear_display = ', '.join(gear)
        else:
            gear_display = 'None'

        await ctx.send(f"@{username}'s Inventory:\n**Gear:** {gear_display}")

    # --- Combat System (Advanced) ---

    # Implement more detailed combat mechanics if needed

    # --- Utility Functions ---

    async def fetch_user(self, ctx: commands.Context, user_identifier: str) -> Optional[PartialChatter]:
        """
        Fetch a user by name or ID.

        :param ctx: The context of the command.
        :param user_identifier: The username or user ID.
        :return: The PartialChatter object or None.
        """
        try:
            if user_identifier.startswith('@'):
                user_identifier = user_identifier[1:]
            users = await self.bot.fetch_users(names=[user_identifier])
            if users:
                return users[0]
            else:
                return None
        except Exception as e:
            logger.error(f"Error fetching user '{user_identifier}': {e}", exc_info=True)
            return None

    async def get_username(self, user_id: str) -> str:
        """Retrieve the username for a given user ID."""
        try:
            users = await self.bot.fetch_users(ids=[int(user_id)])
            if users:
                return users[0].name
            else:
                return "Unknown"
        except Exception as e:
            logger.error(f"Error fetching username for user ID '{user_id}': {e}", exc_info=True)
            return "Unknown"

    def is_user_in_duel(self, user_id: str) -> bool:
        """Check if a user is currently in a duel."""
        # Implement duel state tracking if needed
        return False  # Placeholder

    # Initialize duel tracking dictionaries
    duel_requests = {}
    current_duels = []


def prepare(bot: commands.Bot):
    bot.add_cog(DnD(bot))
