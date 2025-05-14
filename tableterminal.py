import discord
from discord.ext import commands
import os
from dotenv import load_dotenv, find_dotenv
import sqlite3
import asyncio
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "data.db")

# Load environment variables
env_path = find_dotenv() or str(Path(__file__).parent / "data" / ".env")
load_dotenv(env_path)

# Get the bot token from the .env file
TOKEN = os.getenv("TOKEN")

# Initialize the bot with a command prefix
intents = discord.Intents.all()

def get_prefix(bot, message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (str(message.guild.id),))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "t!"

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

# Remove the default help command to avoid conflicts
bot.remove_command("help")

# Event: Bot is ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

# Dynamically load all cogs from the assets/cogs folder
COGS_FOLDER = "assets.cogs"

async def load_cogs():
    for filename in os.listdir("./assets/cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f"{COGS_FOLDER}.{cog_name}")
                print(f"Loaded cog: {cog_name}")
            except Exception as e:
                print(f"Failed to load cog {cog_name}: {e}")

# Event: When the bot joins a new guild
@bot.event
async def on_guild_join(guild):
    print(f"Joined guild: {guild.name} ({guild.id})")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Add default data for the new guild
        cursor.execute("""
            INSERT OR IGNORE INTO welcome (guild_id, channel, message, autorole, image_url)
            VALUES (?, ?, ?, ?, ?)
        """, (str(guild.id), None, "Welcome to {server}, {user}!", None, None))

        cursor.execute("""
            INSERT OR IGNORE INTO prefixes (guild_id, prefix)
            VALUES (?, ?)
        """, (str(guild.id), "t!"))

        cursor.execute("""
            INSERT OR IGNORE INTO mutes (guild_id, mute_role)
            VALUES (?, ?)
        """, (str(guild.id), None))

        cursor.execute("""
            INSERT OR IGNORE INTO logs (guild_id, log_channel)
            VALUES (?, ?)
        """, (str(guild.id), None))

        cursor.execute("""
            INSERT OR IGNORE INTO announcements (guild_id, announcement_channel)
            VALUES (?, ?)
        """, (str(guild.id), None))

        cursor.execute("""
            INSERT OR IGNORE INTO modmail (guild_id, modmail_channel)
            VALUES (?, ?)
        """, (str(guild.id), None))

        # Default shop items with command names, types, and rarities
        default_items = [
            # (item_name, command_name, price, description, effect, rarity, item_type)
            ("Coin Booster", "coinboost", 500, "Doubles your coin gains from /daily and /work.", "boost", "rare", "boost"),
            ("VIP Role", "viprole", 1000, "Grants you a special VIP role (ask an admin to set up the role and update the effect).", None, "epic", "role"),
            ("Lucky Charm", "luckycharm", 300, "Slightly increases your chance of getting higher rarity items from /work.", "luck", "uncommon", "boost"),
            # --- Collectibles: Common ---
            ("Custom Token", "customtoken", 100, "A custom token for your next game night. Simple but fun.", "collectible:common", "common", "collectible"),
            ("Plastic Meeple", "plasticmeeple", 120, "A basic plastic meeple for your board game collection.", "collectible:common", "common", "collectible"),
            ("Wooden Cube", "woodencube", 110, "A classic wooden resource cube. Staple of eurogames!", "collectible:common", "common", "collectible"),
            ("Card Sleeve", "cardsleeve", 130, "A protective card sleeve. Not rare, but always useful.", "collectible:common", "common", "collectible"),
            ("Mini Dice Set", "minidiceset", 140, "A tiny set of polyhedral dice. Cute and common!", "collectible:common", "common", "collectible"),
            # --- Collectibles: Uncommon ---
            ("Tabletop Mug", "ttmug", 400, "A mug with dice and meeples. A fun collectible!", "collectible:uncommon", "uncommon", "collectible"),
            ("Metal Coin", "metalcoin", 350, "A shiny metal coin used in deluxe board games.", "collectible:uncommon", "uncommon", "collectible"),
            ("Acrylic Standee", "acrylicstandee", 375, "A colorful acrylic standee for your favorite character.", "collectible:uncommon", "uncommon", "collectible"),
            ("Dice Bag", "dicebag", 390, "A velvet dice bag to keep your dice safe.", "collectible:uncommon", "uncommon", "collectible"),
            ("Metallic Token", "metallictok", 410, "A metallic token for special occasions.", "collectible:uncommon", "uncommon", "collectible"),
            # --- Collectibles: Rare ---
            ("Miniature Dragon", "minidragon", 800, "A rare collectible dragon figurine for tabletop fans. Sell or show off!", "collectible:rare", "rare", "collectible"),
            ("Lootbox", "lootbox", 250, "Open for a chance at rare collectibles! Earnable from daily streaks or buy here.", None, "rare", "lootbox"),
            ("Enamel Pin", "enamelpin", 850, "A rare enamel pin featuring a d20.", "collectible:rare", "rare", "collectible"),
            ("Collector's Dice", "collectorsdice", 900, "A rare set of collector's dice.", "collectible:rare", "rare", "collectible"),
            ("Signed Card", "signedcard", 950, "A rare card signed by a famous designer.", "collectible:rare", "rare", "collectible"),
            # --- Collectibles: Epic ---
            ("Signed D20", "signedd20", 1500, "An epic signed D20 die. Only the luckiest own this!", "collectible:epic", "epic", "collectible"),
            ("Collector's Coin", "collectorscoin", 1600, "A limited edition collector's coin.", "collectible:epic", "epic", "collectible"),
            ("Crystal Dice", "crystaldice", 1700, "A set of dice made from crystal.", "collectible:epic", "epic", "collectible"),
            ("Art Print", "artprint", 1800, "A signed art print from a famous board game.", "collectible:epic", "epic", "collectible"),
            ("Gold Foil Card", "goldfoilcard", 1900, "A card with gold foil accents.", "collectible:epic", "epic", "collectible"),
            # --- Collectibles: Legendary ---
            ("Foil MTG Card", "foilmtg", 2500, "A legendary foil Magic: The Gathering card. Flex in your inventory!", "collectible:legendary", "legendary", "collectible"),
            ("Golden Meeple", "goldenmeeple", 3000, "A legendary golden meeple. The ultimate flex!", "collectible:legendary", "legendary", "collectible"),
            ("Diamond Dice", "diamonddice", 3500, "A set of dice encrusted with diamonds.", "collectible:legendary", "legendary", "collectible"),
            ("Signed Board Game", "signedgame", 4000, "A legendary board game signed by its creator.", "collectible:legendary", "legendary", "collectible"),
            ("Mythic Trophy", "mythictrophy", 5000, "A trophy awarded to only the greatest tabletop champions.", "collectible:legendary", "legendary", "collectible"),
            # --- Protection ---
            ("Anti-Theft Token", "antitheft", 1200, "Prevents you from being stolen from for 24 hours. Consumed on use.", "antitheft", "epic", "protection"),
        ]

        # Check for View Audit Log permission
        bot_member = guild.me
        has_audit_perm = bot_member.guild_permissions.view_audit_log

        # Try to DM the user who invited the bot
        try:
            inviter = None
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
                inviter = entry.user
                break
            if not inviter:
                inviter = guild.owner
            if inviter:
                dm_embed = discord.Embed(
                    title="Welcome to Tabletop Terminal!",
                    description=(
                        "Thank you for adding me to your server! Here are some useful commands to help you get started. "
                        "You can use these as slash commands or with your chosen prefix. Explore `/help` for more!"
                    ),
                    color=discord.Color.blurple()
                )
                # Highlight 7 useful commands, including YGO and MTG features
                dm_embed.add_field(name="/help", value="Show all available commands or details for a specific command.", inline=False)
                dm_embed.add_field(name="/shop", value="Browse the shop, buy and sell items.", inline=False)
                dm_embed.add_field(name="/balance", value="Check your wallet and bank balance.", inline=False)
                dm_embed.add_field(name="/work", value="Work for coins (with cooldown).", inline=False)
                dm_embed.add_field(name="/slots", value="Play the slot machine for a chance to win coins.", inline=False)
                dm_embed.add_field(name="/ygostart", value="Start or join a Yu-Gi-Oh! duel lobby.", inline=False)
                dm_embed.add_field(name="/mtgstart", value="Start or join a Magic: The Gathering game lobby.", inline=False)
                dm_embed.set_footer(text="Tip: Use /help to see all available commands!")
                await inviter.send(embed=dm_embed)
        except Exception as e:
            print(f"Could not send DM to inviter: {e}")
    except Exception as e:
        print(f"Error in on_guild_join for guild {guild.id}: {e}")

# Event: When the bot is removed from a guild
@bot.event
async def on_guild_remove(guild):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Remove data for the guild from all tables, i
    # ncluding new ones,
    # EXCEPT eco_players (so player inventory/coins persist across servers)
    cursor.execute("DELETE FROM welcome WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM prefixes WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM mutes WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM logs WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM announcements WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM modmail WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM eco_shop WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM bans WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM rpg_monsters WHERE guild_id = ?", (str(guild.id),))
    cursor.execute("DELETE FROM rpg_quests WHERE guild_id = ?", (str(guild.id),))
    # Add more tables here if you add more guild-specific data in the future

    conn.commit()
    conn.close()

# Event: When a member joins a guild
@bot.event
async def on_member_join(member):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT channel, message, image_url, autorole FROM welcome WHERE guild_id = ?", (str(member.guild.id),))
    result = cursor.fetchone()
    conn.close()

    if result:
        channel_id, welcome_message, image_url, autorole_id = result
        # Replace placeholders
        welcome_message = welcome_message.replace("{user}", member.mention).replace("{server}", member.guild.name)
        try:
            # Send welcome embed
            channel = member.guild.get_channel(int(channel_id)) if channel_id else None
            if channel:
                embed = discord.Embed(
                    title="Welcome!",
                    description=welcome_message,
                    color=discord.Color.blurple()
                )
                embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                if image_url:
                    embed.set_image(url=image_url)
                await channel.send(embed=embed)
            # Assign autorole if configured
            if autorole_id:
                role = member.guild.get_role(int(autorole_id))
                if role:
                    await member.add_roles(role, reason="Autorole on join")
        except Exception as e:
            print(f"Failed to send welcome message or assign autorole: {e}")

# Run the bot
if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(TOKEN)
    asyncio.run(main())