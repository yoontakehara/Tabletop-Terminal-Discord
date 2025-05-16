import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "data.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Welcome table
cursor.execute("""
CREATE TABLE IF NOT EXISTS welcome (
    guild_id TEXT PRIMARY KEY,
    channel TEXT,
    message TEXT,
    autorole TEXT,
    image_url TEXT
)
""")

# Prefixes table
cursor.execute("""
CREATE TABLE IF NOT EXISTS prefixes (
    guild_id TEXT PRIMARY KEY,
    prefix TEXT
)
""")

# Mutes table
cursor.execute("""
CREATE TABLE IF NOT EXISTS mutes (
    guild_id TEXT PRIMARY KEY,
    mute_role TEXT
)
""")

# Logs table
cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    guild_id TEXT PRIMARY KEY,
    log_channel TEXT
)
""")

# Announcements table
cursor.execute("""
CREATE TABLE IF NOT EXISTS announcements (
    guild_id TEXT PRIMARY KEY,
    announcement_channel TEXT
)
""")

# Modmail table
cursor.execute("""
CREATE TABLE IF NOT EXISTS modmail (
    guild_id TEXT PRIMARY KEY,
    modmail_channel TEXT
)
""")

# Economy shop table
cursor.execute("""
CREATE TABLE IF NOT EXISTS eco_shop (
    guild_id TEXT,
    item_name TEXT,
    command_name TEXT,
    price INTEGER,
    description TEXT,
    effect TEXT DEFAULT NULL,
    rarity TEXT DEFAULT NULL,
    item_type TEXT DEFAULT NULL
)
""")

# Economy players table
cursor.execute("""
CREATE TABLE IF NOT EXISTS eco_players (
    user_id TEXT PRIMARY KEY,
    coins INTEGER DEFAULT 0,
    bank INTEGER DEFAULT 0,
    inventory TEXT DEFAULT '',
    daily_streak INTEGER DEFAULT 0,
    last_daily TEXT DEFAULT NULL,
    luck_expiry TEXT DEFAULT NULL
)
""")

# Economy cooldowns table (persistent command cooldowns)
cursor.execute("""
CREATE TABLE IF NOT EXISTS eco_cooldowns (
    user_id TEXT,
    command TEXT,
    last_used TEXT,
    PRIMARY KEY (user_id, command)
)
""")

# Bans table
cursor.execute("""
CREATE TABLE IF NOT EXISTS bans (
    guild_id TEXT,
    user_id TEXT,
    user_tag TEXT,
    reason TEXT,
    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# RPG stats table
cursor.execute("""
CREATE TABLE IF NOT EXISTS rpg_stats (
    user_id TEXT PRIMARY KEY,
    level INTEGER DEFAULT 1,
    exp INTEGER DEFAULT 0,
    hp INTEGER DEFAULT 20,
    max_hp INTEGER DEFAULT 20,
    atk INTEGER DEFAULT 5,
    defense INTEGER DEFAULT 2,
    char_class TEXT DEFAULT NULL,
    weapon TEXT DEFAULT '',
    quest TEXT DEFAULT '',
    quest_progress INTEGER DEFAULT 0,
    skill_points INTEGER DEFAULT 5,
    strength INTEGER DEFAULT 0,
    dexterity INTEGER DEFAULT 0,
    intelligence INTEGER DEFAULT 0,
    exp_to_next INTEGER DEFAULT 27,
    hp_regen INTEGER DEFAULT 0.2,
    mana INTEGER DEFAULT 5,
    mana_regen INTEGER DEFAULT 0.2,
    max_mana INTEGER DEFAULT 5,
    crit_chance REAL DEFAULT 0.01,
    crit_damage REAL DEFAULT 1.0,
    evasion_chance REAL DEFAULT 0.01,
    bonus_spell_dmg INTEGER DEFAULT 0
)
""")

# Create monsters table if not exists
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rpg_monsters (
        guild_id TEXT,
        name TEXT,
        hp INTEGER,
        max_hp INTEGER,
        hp_regen INTEGER DEFAULT 0,
        atk INTEGER,
        defense INTEGER,
        crit_chance REAL DEFAULT 0.0,
        crit_damage REAL DEFAULT 1.0,
        mana INTEGER DEFAULT 0,
        mana_regen INTEGER DEFAULT 0,
        max_mana INTEGER DEFAULT 0,
        exp INTEGER,
        loot TEXT,
        description TEXT,
        rarity TEXT,
        evasion_chance REAL DEFAULT 0.0,
        bonus_spell_dmg INTEGER DEFAULT 0,
        sign_attack TEXT DEFAULT NULL,
        PRIMARY KEY (guild_id, name)
    )
""")

# Create quests table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS rpg_quests (
    guild_id TEXT,
    quest_name TEXT,
    description TEXT,
    target TEXT,
    amount INTEGER,
    reward TEXT,
    PRIMARY KEY (guild_id, quest_name)
)
""")

conn.commit()
conn.close()
print("All tables created successfully.")