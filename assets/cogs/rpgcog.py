import discord
from discord.ext import commands
from discord.ext.commands import check
import sqlite3
import os
import random
import asyncio
import json
import datetime
from assets.cogs.ecocog import get_cooldown, set_cooldown  # Adjust import if needed

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "data.db")

RAID_COOLDOWN_COMMAND = "rpgraid"

# Load SPELLS from JSON file
SPELLS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "spells.json")
with open(SPELLS_PATH, "r", encoding="utf-8") as f:
    SPELLS = json.load(f)

QUESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "default_quests.json")
with open(QUESTS_PATH, "r", encoding="utf-8") as f:
    QUESTS = json.load(f)

ITEMS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "default_items.json")
with open(ITEMS_PATH, "r", encoding="utf-8") as f:
    DEFAULT_ITEMS = json.load(f)

# Build a lookup for weapons from default_items.json
WEAPON_ITEMS = {
    item["item_name"]: item
    for item in DEFAULT_ITEMS
    if item.get("item_type") == "weapons"
}

def load_raid_state(guild_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT boss_name, boss_hp, boss_max_hp, boss_data, participants, last_spawn FROM rpg_raid_state WHERE guild_id = ?", (str(guild_id),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    boss_name, boss_hp, boss_max_hp, boss_data, participants, last_spawn = row
    return {
        "boss_name": boss_name,
        "boss_hp": boss_hp,
        "boss_max_hp": boss_max_hp,
        "boss_data": json.loads(boss_data),
        "participants": set(json.loads(participants)),
        "last_spawn": datetime.datetime.fromisoformat(last_spawn) if last_spawn else None
    }

def save_raid_state(guild_id, state):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR REPLACE INTO rpg_raid_state
        (guild_id, boss_name, boss_hp, boss_max_hp, boss_data, participants, last_spawn)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            str(guild_id),
            state["boss_name"],
            state["boss_hp"],
            state["boss_max_hp"],
            json.dumps(state["boss_data"]),
            json.dumps(list(state["participants"])),
            state["last_spawn"].isoformat() if state["last_spawn"] else None
        )
    )
    conn.commit()
    conn.close()

def clear_raid_state(guild_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rpg_raid_state WHERE guild_id = ?", (str(guild_id),))
    conn.commit()
    conn.close()

def get_player(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT coins, bank, inventory FROM eco_players WHERE user_id = ?", (str(user_id),))
    result = cursor.fetchone()
    conn.close()
    if result:
        coins, bank, inv = result
        inv = inv or ""
        return coins, bank, inv
    return 0, 0, ""

def update_player_inventory(user_id, inventory):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE eco_players SET inventory = ? WHERE user_id = ?", (inventory, str(user_id)))
    conn.commit()
    conn.close()

def add_player_if_not_exists(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO eco_players (user_id, coins, bank, inventory) VALUES (?, 0, 0, '')", (str(user_id),))
    conn.commit()
    conn.close()

def get_rpg_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points, strength, dexterity, intelligence, exp_to_next,
                  hp_regen, mana, mana_regen, max_mana, crit_chance, crit_damage, evasion_chance, bonus_spell_dmg
           FROM rpg_stats WHERE user_id = ?""",
        (str(user_id),)
    )
    stats = cursor.fetchone()
    conn.close()
    return stats

def update_rpg_stats(user_id, **kwargs):
    ALLOWED_FIELDS = {
        "level", "exp", "hp", "max_hp", "atk", "defense", "char_class", "weapon", "quest", "quest_progress",
        "skill_points", "strength", "dexterity", "intelligence", "exp_to_next", "hp_regen", "mana", "mana_regen",
        "max_mana", "crit_chance", "crit_damage", "evasion_chance", "bonus_spell_dmg"
    }
    # Filter only allowed fields
    kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
    if "quest_progress" in kwargs and kwargs["quest_progress"] is None:
        kwargs["quest_progress"] = 0
    if not kwargs:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values())
    values.append(str(user_id))
    cursor.execute(f"UPDATE rpg_stats SET {fields} WHERE user_id = ?", values)
    conn.commit()
    conn.close()

def exp_to_next_level(level):
    return int(20 + (level ** 1.5) * 7)

def rpg_started():
    async def predicate(ctx):
        stats = get_rpg_stats(ctx.author.id)
        if not stats or stats[0] is None:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart` to begin!")
            raise commands.CheckFailure("User has not started an adventure.")
        return True
    return check(predicate)

def remove_all_rpg_items_from_inventory(user_id):
    """
    Remove all RPG-related items (weapons, armor, consumables, collectibles) from the user's inventory.
    """
    coins, bank, inv = get_player(user_id)
    items = inv.split(",") if inv else []
    # Load all RPG item names from DEFAULT_ITEMS
    rpg_item_names = {item["item_name"] for item in DEFAULT_ITEMS}
    # Remove all items that are in the RPG item list
    items = [item for item in items if item not in rpg_item_names]
    update_player_inventory(user_id, ",".join(items))
    # Unequip weapon in rpg_stats
    update_rpg_stats(user_id, weapon="")

class RPGMarketPageView(discord.ui.View):
    def __init__(self, ctx, items, page=0, items_per_page=6):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.items = items
        self.page = page
        self.items_per_page = items_per_page
        self.max_page = max(0, (len(items) - 1) // items_per_page)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.ctx.author.id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            await self.update_message(interaction)

    async def update_message(self, interaction):
        embed = discord.Embed(
            title=f"RPG Marketplace (Page {self.page + 1}/{self.max_page + 1})",
            description="Use `/rpgmarket buy <item name> [quantity]` or `/rpgmarket sell <item name> [quantity]`.\n",
            color=discord.Color.blurple()
        )
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        for item in self.items[start:end]:
            price = item.get("price", 0)
            desc = item.get("description", "")
            rarity = item.get("rarity", "common").capitalize()
            item_type = item.get("item_type", "misc").capitalize()
            embed.add_field(
                name=f"{item['item_name']} ({item_type}) - {price} coins",
                value=f"{desc}\nRarity: {rarity}",
                inline=False
            )
        # Update button states
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page == self.max_page
        await interaction.response.edit_message(embed=embed, view=self)

class RPGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = {}
        self.active_parties = {}
        self.parties = {}
        self.party_counter = 1
        self.raid_turn_actions = {}  # {guild_id: set(user_ids who attacked this turn)}

        # Load default monsters JSON once at cog init
        monsters_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "default_monsters.json"
        )
        with open(monsters_path, "r", encoding="utf-8") as f:
            self.default_monsters = json.load(f)

    @commands.hybrid_command(name="treasurechest", description="Open a Treasure Chest for a random RPG reward!")
    @rpg_started()
    async def treasurechest(self, ctx):
        user_id = ctx.author.id
        coins, bank, inv = get_player(user_id)
        items = inv.split(",") if inv else []

        # Check if user has a Treasure Chest
        if "Treasure Chest" not in items:
            await ctx.send("You don't have a Treasure Chest in your inventory. Defeat a Mimic or complete certain quests to get one!")
            return

        # Remove one Treasure Chest from inventory
        items.remove("Treasure Chest")
        update_player_inventory(user_id, ",".join(items))

        # Define possible rewards (customize as you wish)
        possible_rewards = [
            {"type": "coins", "amount": random.randint(300, 800)},
            {"type": "item", "name": "Magic Scroll"},
            {"type": "item", "name": "Greater Potion"},
            {"type": "item", "name": "Mana Potion"},
            {"type": "item", "name": "Revive Feather"},
            {"type": "item", "name": "Elixir"},
            {"type": "item", "name": "Silver Apple"},
            {"type": "item", "name": "Bomb"},
            {"type": "item", "name": "Random Weapon"},
        ]

        reward = random.choice(possible_rewards)
        embed = discord.Embed(
            title="Treasure Chest Opened!",
            color=discord.Color.gold()
        )

        if reward["type"] == "coins":
            coins += reward["amount"]
            update_player_inventory(user_id, ",".join(items))
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE eco_players SET coins = ? WHERE user_id = ?", (coins, str(user_id)))
            conn.commit()
            conn.close()
            embed.description = f"You found **{reward['amount']} coins** inside the chest!"
        elif reward["type"] == "item":
            item_name = reward["name"]
            # If "Random Weapon", pick a random buyable weapon
            if item_name == "Random Weapon":
                weapon_items = [
                    item for item in DEFAULT_ITEMS
                    if item.get("item_type") == "weapons" and item.get("rarity") in ("common", "uncommon", "rare")
                ]
                if weapon_items:
                    weapon = random.choice(weapon_items)
                    item_name = weapon["item_name"]
                else:
                    item_name = "Potion"
            items.append(item_name)
            update_player_inventory(user_id, ",".join(items))
            embed.description = f"You found a **{item_name}** inside the chest!"

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rpgmarket", description="Buy or sell RPG gear using your coins!")
    @rpg_started()
    async def rpgmarket(self, ctx, action: str = None, item_name: str = None, quantity: int = 1):
        user_id = ctx.author.id
        coins, bank, inv = get_player(user_id)
        items = inv.split(",") if inv else []

        # --- Define buyable and sellable items ---
        # Buyable: common/rare consumables, common/uncommon weapons
        buyable_items = [
            item for item in DEFAULT_ITEMS
            if (
                (item.get("item_type") == "consumables" and item.get("rarity") in ("common", "uncommon", "rare") and not item.get("shop_hidden", False))
                or (item.get("item_type") == "weapons" and item.get("rarity") in ("common", "uncommon") and not item.get("shop_hidden", False))
            )
        ]
        # Sellable: all items in default_items.json
        sellable_items = [item for item in DEFAULT_ITEMS]

        # Show marketplace if no action
        if not action:
            view = RPGMarketPageView(ctx, buyable_items)
            embed = discord.Embed(
                title="RPG Marketplace (Page 1)",
                description="Use `/rpgmarket buy <item name> [quantity]` or `/rpgmarket sell <item name> [quantity]`.",
                color=discord.Color.blurple()
            )
            for item in buyable_items[:6]:
                price = item.get("price", 0)
                desc = item.get("description", "")
                rarity = item.get("rarity", "common").capitalize()
                embed.add_field(
                    name=f"{item['item_name']} ({item['item_type'].capitalize()}) - {price} coins",
                    value=f"{desc}\nRarity: {rarity}",
                    inline=False
                )
            await ctx.send(embed=embed, view=view)
            return

        action = action.lower()
        if action not in ("buy", "sell"):
            await ctx.send("Invalid action. Use `/rpgmarket buy <item name> [quantity]` or `/rpgmarket sell <item name> [quantity]`.")
            return

        if not item_name:
            await ctx.send("Please specify the item name to buy or sell.")
            return

        # Find the item (case-insensitive)
        if action == "buy":
            item = next((i for i in buyable_items if i["item_name"].lower() == item_name.lower()), None)
            if not item:
                await ctx.send("That item is not available for purchase in the marketplace.")
                return
        else:  # sell
            item = next((i for i in sellable_items if i["item_name"].lower() == item_name.lower()), None)
            if not item:
                await ctx.send("That item cannot be sold.")
                return

        if quantity < 1:
            await ctx.send("Quantity must be at least 1.")
            return

        if action == "buy":
            total_price = item.get("price", 0) * quantity
            if coins < total_price:
                await ctx.send(f"You need {total_price} coins to buy {quantity}x {item['item_name']}.")
                return

            # Add item(s) to inventory
            for _ in range(quantity):
                items.append(item["item_name"])
            update_player_inventory(user_id, ",".join(items))
            # Deduct coins
            new_coins = coins - total_price
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE eco_players SET coins = ? WHERE user_id = ?", (new_coins, str(user_id)))
            conn.commit()
            conn.close()

            await ctx.send(f"You bought {quantity}x **{item['item_name']}** for {total_price} coins! (Coins left: {new_coins})")
            return

        if action == "sell":
            # Check if user owns enough of the item
            owned_count = items.count(item["item_name"])
            if owned_count < quantity:
                await ctx.send(f"You don't have {quantity}x **{item['item_name']}** to sell.")
                return

            # Calculate sell price (e.g., 50% of buy price)
            sell_price = int(item.get("price", 0) * 0.5) * quantity
            # Remove items from inventory
            for _ in range(quantity):
                items.remove(item["item_name"])
            update_player_inventory(user_id, ",".join(items))
            # Add coins
            new_coins = coins + sell_price
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE eco_players SET coins = ? WHERE user_id = ?", (new_coins, str(user_id)))
            conn.commit()
            conn.close()

            await ctx.send(f"You sold {quantity}x **{item['item_name']}** for {sell_price} coins! (Coins now: {new_coins})")

    @commands.hybrid_command(name="rpgraid", description="Challenge a random weekly raid boss with your party!")
    @rpg_started()
    async def rpgraid(self, ctx):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # Only allow parties (not solo)
        if user_id not in self.active_parties:
            await ctx.send("You must be in a party to challenge the weekly raid boss!")
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        if party["leader"] != user_id:
            await ctx.send("Only the party leader can start a raid.")
            return

        # Check for existing raid state
        raid_state = load_raid_state(guild_id)
        now = datetime.datetime.utcnow()
        if raid_state and raid_state["last_spawn"] and (now - raid_state["last_spawn"]).days < 7:
            boss = raid_state["boss_data"]
            await ctx.send(
                f"A raid boss (**{boss['name']}**) is already active!\n"
                f"HP: {raid_state['boss_hp']}/{raid_state['boss_max_hp']}\n"
                "Use `/rpgraidattack` to join the fight!"
            )
            return

        # Randomly select a raid boss from your monsters
        raid_bosses = [m for m in self.default_monsters if m.get("rarity") == "raid"]
        if not raid_bosses:
            await ctx.send("No raid boss is configured. Please ask an admin to add one to the monsters file.")
            return
        raid_boss = random.choice(raid_bosses)

        # Scale HP for party size
        party_size = len(party["members"])
        boss = dict(raid_boss)
        boss["hp"] = boss["max_hp"] = int(boss["max_hp"] * (1 + 0.8 * (party_size - 1)))

        # Set raid state
        raid_state = {
            "boss_name": boss["name"],
            "boss_hp": boss["hp"],
            "boss_max_hp": boss["max_hp"],
            "boss_data": boss,
            "participants": set(party["members"]),
            "last_spawn": now
        }
        save_raid_state(guild_id, raid_state)
        self.active_battles[f"raid_{guild_id}"] = boss
        self.active_battles[f"raid_{guild_id}_regen_remainder"] = 0.0
        boss["regen_remainder"] = 0.0

        member_mentions = ", ".join(f"<@{uid}>" for uid in party["members"])
        await ctx.send(
            f"🌑 **Weekly Raid Boss Appears!** 🌑\n"
            f"Your party ({member_mentions}) faces **{boss['name']}**!\n"
            f"HP: {boss['hp']}, ATK: {boss['atk']}\n"
            "All party members can use `/rpgraidattack` to fight the raid boss!"
        )

    @commands.hybrid_command(name="rpgraidattack", description="Attack the weekly raid boss!")
    @rpg_started()
    async def rpgraidattack(self, ctx, spell_name: str = None, target: str = None):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # --- Check daily raid participation cooldown ---
        now = datetime.datetime.utcnow()
        last_used = get_cooldown(user_id, f"{RAID_COOLDOWN_COMMAND}_{guild_id}")
        if last_used and (now - last_used).total_seconds() < 86400:
            hours = int((86400 - (now - last_used).total_seconds()) // 3600)
            await ctx.send(f"You have already participated in a raid in the last 24 hours. Try again in {hours} hour(s).")
            return

        raid_state = load_raid_state(guild_id)
        if not raid_state or raid_state["boss_hp"] <= 0:
            await ctx.send("There is no active raid boss right now. Use `/rpgraid` to start one!")
            return
        boss = raid_state["boss_data"]
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return

        # Only allow party members who participated
        if user_id not in raid_state["participants"]:
            await ctx.send("You are not a participant in this week's raid.")
            return

        # Only allow attacking raid monsters
        if boss.get("rarity") != "raid":
            await ctx.send("The current boss is not a raid-class monster.")
            return

        party_members = raid_state["participants"]

        # --- Turn-based raid logic ---
        if guild_id not in self.raid_turn_actions:
            self.raid_turn_actions[guild_id] = set()
        if user_id in self.raid_turn_actions[guild_id]:
            await ctx.send("You have already attacked this turn. Wait for your party to finish their moves!")
            return

        # --- Player's attack logic ---
        target_type, target_user_id = self.resolve_attack_target(ctx, target, party_members)
        if spell_name:
            msg = await self.handle_spell_attack(ctx, user_id, stats, spell_name, target_type, target_user_id, boss, party_members, raid_mode=True)
        else:
            msg = await self.handle_player_attack(ctx, user_id, stats, boss, party_members, target_type, target_user_id, raid_mode=True)

        # Save that this user has acted this turn
        self.raid_turn_actions[guild_id].add(user_id)

        # --- Display which party members have attacked this turn ---
        attacked_ids = self.raid_turn_actions[guild_id]
        attacked_mentions = [f"<@{uid}>" for uid in attacked_ids]
        not_attacked_mentions = [f"<@{uid}>" for uid in party_members if uid not in attacked_ids]
        status_msg = (
            f"**Party Raid Turn Progress:**\n"
            f"Attacked: {', '.join(attacked_mentions) if attacked_mentions else 'None'}\n"
            f"Waiting: {', '.join(not_attacked_mentions) if not_attacked_mentions else 'None'}"
        )

        # Update persistent HP
        raid_state["boss_hp"] = boss["hp"]
        save_raid_state(guild_id, raid_state)

        # If boss defeated, reward all participants and clear state
        if boss["hp"] <= 0:
            for pid in raid_state["participants"]:
                coins, bank, inv = get_player(pid)
                items = inv.split(",") if inv else []
                items.append(boss.get("loot", "Titan Relic"))
                update_player_inventory(pid, ",".join(items))
                member = self.bot.get_user(pid)
                if member:
                    try:
                        asyncio.create_task(member.send(f"You received a **{boss.get('loot', 'Titan Relic')}** for defeating the weekly raid boss!"))
                    except Exception:
                        pass
                # Set raid cooldown for all participants
                set_cooldown(pid, f"{RAID_COOLDOWN_COMMAND}_{guild_id}", now)
            clear_raid_state(guild_id)
            self.raid_turn_actions[guild_id] = set()
            msg += "\n**Your party has conquered the Weekly Raid Boss! All participants receive the reward!**"
            await ctx.send(self.format_battle_message(msg))
            return

        # Show the result of the player's attack and party turn status
        await ctx.send(self.format_battle_message(msg) + "\n" + status_msg)

        # --- Only after all party members have acted, boss attacks and regen happens ---
        if self.raid_turn_actions[guild_id] >= set(party_members):
            # Boss attacks a random alive party member
            alive_members = [pid for pid in party_members if get_rpg_stats(pid)[2] > 0]
            if alive_members:
                target_id = random.choice(list(alive_members))
                target_stats = get_rpg_stats(target_id)
                boss_msg = f"\n**Raid Boss's Turn!**\n"
                boss_msg = self.monster_attack_phase(ctx, target_id, boss, target_stats, boss_msg)
                # Boss regen phase (after attack)
                boss_msg += self.regen_phase(target_id, boss, target_stats, target_stats[2], target_stats[3], target_stats[16], target_stats[18], target_stats[15], target_stats[17])
                await ctx.send(boss_msg)
            # Reset for next turn
            self.raid_turn_actions[guild_id] = set()
    
    # --- Improved Party System ---
    @commands.hybrid_group(name="rpgparty", description="Party commands for co-op RPG play.")
    @rpg_started()
    async def rpgparty(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Party commands: create, invite, join, leave, kick, promote, status")

    @rpgparty.command(name="create")
    @rpg_started()
    async def party_create(self, ctx):
        user_id = ctx.author.id
        if user_id in self.active_parties:
            await ctx.send("You are already in a party.")
            return
        party_id = self.party_counter
        self.party_counter += 1
        self.parties[party_id] = {
            "members": {user_id},
            "leader": user_id,
            "quest": None,
            "progress": 0,
            "invited": set()
        }
        self.active_parties[user_id] = party_id
        await ctx.send(f"Party created! You are the leader. Party ID: {party_id}")

    @rpgparty.command(name="invite")
    @rpg_started()
    async def party_invite(self, ctx, member: discord.Member):
        user_id = ctx.author.id
        if user_id not in self.active_parties:
            await ctx.send("You are not in a party.")
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        if party["leader"] != user_id:
            await ctx.send("Only the party leader can invite members.")
            return
        if member.id in self.active_parties:
            await ctx.send("That user is already in a party.")
            return
        if member.id in party["invited"]:
            await ctx.send(f"{member.display_name} has already been invited.")
            return
        party["invited"].add(member.id)
        try:
            await member.send(f"You have been invited to join Party {party_id} by {ctx.author.display_name}. Use `/rpgparty join {party_id}` to accept.")
        except Exception:
            await ctx.send(f"Could not DM {member.display_name}, but they have been invited.")
        await ctx.send(f"{member.mention} has been invited to Party {party_id}.")

    @rpgparty.command(name="join")
    @rpg_started()
    async def party_join(self, ctx, party_id: int):
        user_id = ctx.author.id
        if user_id in self.active_parties:
            await ctx.send("You are already in a party.")
            return
        party = self.parties.get(party_id)
        if not party:
            await ctx.send("That party does not exist.")
            return
        if user_id not in party["invited"]:
            await ctx.send("You have not been invited to this party.")
            return
        party["members"].add(user_id)
        self.active_parties[user_id] = party_id
        party["invited"].remove(user_id)
        await ctx.send(f"You joined Party {party_id}! Members: {', '.join(f'<@{uid}>' for uid in party['members'])}")

    @rpgparty.command(name="leave")
    @rpg_started()
    async def party_leave(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.active_parties:
            await ctx.send("You are not in a party.")
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        party["members"].remove(user_id)
        del self.active_parties[user_id]
        if not party["members"]:
            del self.parties[party_id]
            await ctx.send("Party disbanded.")
            return
        if party["leader"] == user_id:
            party["leader"] = next(iter(party["members"]))
            await ctx.send(f"You left the party. New leader: <@{party['leader']}>")
        else:
            await ctx.send("You left the party.")

    @rpgparty.command(name="kick")
    @rpg_started()
    async def party_kick(self, ctx, member: discord.Member):
        user_id = ctx.author.id
        if user_id not in self.active_parties:
            await ctx.send("You are not in a party.")
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        if party["leader"] != user_id:
            await ctx.send("Only the party leader can kick members.")
            return
        if member.id == user_id:
            await ctx.send("You can't kick yourself. Use `/rpgparty leave` to leave the party.")
            return
        if member.id not in party["members"]:
            await ctx.send("That user is not in your party.")
            return
        party["members"].remove(member.id)
        if member.id in self.active_parties:
            del self.active_parties[member.id]
        await ctx.send(f"{member.display_name} has been kicked from the party.")

    @rpgparty.command(name="promote")
    @rpg_started()
    async def party_promote(self, ctx, member: discord.Member):
        user_id = ctx.author.id
        if user_id not in self.active_parties:
            await ctx.send("You are not in a party.")
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        if party["leader"] != user_id:
            await ctx.send("Only the party leader can promote another member.")
            return
        if member.id not in party["members"]:
            await ctx.send("That user is not in your party.")
            return
        if member.id == user_id:
            await ctx.send("You are already the leader.")
            return
        party["leader"] = member.id
        await ctx.send(f"{member.display_name} is now the party leader!")

    @rpgparty.command(name="status")
    @rpg_started()
    async def party_status(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.active_parties:
            await ctx.send("You are not in a party.")
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        members = [f"<@{uid}>" for uid in party["members"]]
        leader = party["leader"]
        invited = [f"<@{uid}>" for uid in party.get("invited", set())]
        embed = discord.Embed(
            title=f"Party {party_id} Status",
            description=f"Leader: <@{leader}>\nMembers: {', '.join(members)}",
            color=discord.Color.green()
        )
        if invited:
            embed.add_field(name="Invited", value=", ".join(invited), inline=False)
        embed.add_field(name="Quest", value=party.get("quest") or "None", inline=True)
        embed.add_field(name="Progress", value=party.get("progress", 0), inline=True)
        await ctx.send(embed=embed)

    # --- Richer Quest Logic ---
    def get_quests(self, guild_id):
        """
        Loads quests from default_quests.json instead of the database.
        Ignores guild_id (all guilds get the same default quests).
        """
        quests = {}
        for q in QUESTS:
            quests[q["quest_name"]] = {
                "desc": q["description"],
                "target": q["target"],
                "amount": q["amount"],
                "reward": q["reward"]
            }
        return quests

    @commands.hybrid_command(name="rpgquest", description="Accept, view, or abandon quests for extra rewards! Supports party quests.")
    @rpg_started()
    async def rpgquest(self, ctx, action: str = None, *, quest: str = None):
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        quests = self.get_quests(guild_id)

        # --- Track user's current quest(s) ---
        stats = get_rpg_stats(user_id)
        current_quest = stats[8] if stats and len(stats) > 8 else None
        current_progress = stats[9] if stats and len(stats) > 9 else 0

        # --- Show available quests and current quest ---
        if not action:
            msg = "**Available quests:**\n"
            for qname, q in quests.items():
                msg += f"• **{qname}**: {q['desc']} (Target: {q['target']} x{q['amount']}, Reward: {q['reward']})\n"
            if current_quest:
                msg += f"\n**Your current quest:** {current_quest} ({current_progress}/{quests.get(current_quest, {}).get('amount', '?')})"
            else:
                msg += "\nYou have no active quest. Use `/rpgquest accept <quest name>` to start one."
            await ctx.send(msg)
            return

        action = action.lower()
        if action == "accept":
            if not quest or quest not in quests:
                await ctx.send(f"Specify a valid quest to accept. Available: {', '.join(quests.keys())}")
                return
            if current_quest:
                await ctx.send(f"You already have an active quest: **{current_quest}**. Use `/rpgquest abandon` to abandon it first.")
                return
            q = quests[quest]
            # Party quest logic
            if user_id in self.active_parties:
                party_id = self.active_parties[user_id]
                party = self.parties[party_id]
                party["quest"] = quest
                party["progress"] = 0
                await ctx.send(f"Party quest accepted: **{quest}** - {q['desc']}. Reward: {q['reward']}")
            else:
                update_rpg_stats(user_id, quest=quest, quest_progress=0)
                await ctx.send(f"Quest accepted: **{quest}** - {q['desc']}. Reward: {q['reward']}")
            return

        elif action == "status":
            if current_quest:
                q = quests.get(current_quest)
                if q:
                    await ctx.send(f"**Current quest:** {current_quest}\nDescription: {q['desc']}\nProgress: {current_progress}/{q['amount']}\nReward: {q['reward']}")
                else:
                    await ctx.send(f"**Current quest:** {current_quest}\nProgress: {current_progress}")
            else:
                await ctx.send("You have no active quest.")
            return

        elif action == "abandon":
            if not current_quest:
                await ctx.send("You have no active quest to abandon.")
                return
            update_rpg_stats(user_id, quest=None, quest_progress=0)
            await ctx.send(f"You have abandoned the quest: **{current_quest}**.")
            return

        else:
            await ctx.send("Usage: `/rpgquest`, `/rpgquest accept <quest name>`, `/rpgquest status`, `/rpgquest abandon`")

    # Example: Party quest progress update (call this in your battle logic)
    async def update_party_quest_progress(self, user_id, monster_name):
        if user_id not in self.active_parties:
            return
        party_id = self.active_parties[user_id]
        party = self.parties[party_id]
        if not party["quest"]:
            return
        guild_id = None
        for g in self.bot.guilds:
            if g.get_member(user_id):
                guild_id = g.id
                break
        if not guild_id:
            return
        quests = self.get_quests(guild_id)
        quest = quests.get(party["quest"])
        if not quest:
            return
        # Check if monster matches quest target
        if quest["target"].lower() in monster_name.lower():
            party["progress"] += 1
            # Notify party
            channel = None
            for m_id in party["members"]:
                member = self.bot.get_user(m_id)
                if member:
                    try:
                        await member.send(f"Party quest progress: {party['progress']}/{quest['amount']}")
                    except Exception:
                        pass
            # Complete quest
            if party["progress"] >= int(quest["amount"]):
                for m_id in party["members"]:
                    # Give reward to each member
                    coins, bank, inv = get_player(m_id)
                    items = inv.split(",") if inv else []
                    items.append(quest["reward"])
                    update_player_inventory(m_id, ",".join(items))
                    update_rpg_stats(m_id, quest=None, quest_progress=0)
                    member = self.bot.get_user(m_id)
                    if member:
                        try:
                            await member.send(f"Party quest **{party['quest']}** complete! You received: {quest['reward']}")
                        except Exception:
                            pass
                party["quest"] = None
                party["progress"] = 0
    
    @commands.hybrid_command(name="rpgstart", description="Start your RPG adventure!")
    async def rpgstart(self, ctx):
        user_id = ctx.author.id

        # --- Ensure user exists in eco_players table ---
        def add_player_if_not_exists(user_id):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO eco_players (user_id, coins, bank, inventory) VALUES (?, 0, 0, '')", (str(user_id),))
            conn.commit()
            conn.close()
        add_player_if_not_exists(user_id)

        # Check if user already exists in rpg_stats
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM rpg_stats WHERE user_id = ?", (str(user_id),))
        exists = cursor.fetchone()
        if exists:
            conn.close()
            await ctx.send("You have already started your adventure! Use `/rpgstatus` to view your stats or `/rpgquit` to reset your adventure.")
            return
        # Now insert a fresh row
        exp_to_next = exp_to_next_level(1)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rpg_stats (
                user_id, level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
                strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
                crit_damage, evasion_chance, bonus_spell_dmg
            ) VALUES (?, 1, 0, 20, 20, 5, 2, NULL, '', '', 0, 5, 0, 0, 0, 27, 0.5, 5, 0.2, 5, 0.01, 1.0, 0.01, 0)
        """, (str(user_id),))
        conn.commit()
        conn.close()
        await ctx.send(
            f"{ctx.author.mention} begins their adventure! "
            "You have 5 skill points to assign. Use `/rpgstatus` to view your stats and `/rpgspend <stat> <amount>` to assign points."
        )

    @commands.hybrid_command(name="rpgstatus", description="Check your RPG stats and inventory.")
    @rpg_started()
    async def rpgstatus(self, ctx):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        # Defensive check: None, wrong length, or any field None
        required_indexes = [i for i in range(22) if i != 6]  # allow char_class to be None
        if (
            not stats or
            not isinstance(stats, (list, tuple)) or
            len(stats) < 22 or
            any(stats[i] is None for i in required_indexes)
        ):
            return

        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats

        coins, bank, inv = get_player(user_id)
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s RPG Status",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Class", value=char_class or "Unchosen")
        embed.add_field(name="Level", value=level)
        embed.add_field(name="EXP", value=f"{exp}/{exp_to_next}")
        embed.add_field(name="Skill Points", value=skill_points)
        embed.add_field(name="Weapon", value=weapon or "None")
        embed.add_field(name="HP", value=f"{round(hp,1):.1f}/{round(max_hp,1):.1f} (+{round(hp_regen,1):.1f}/turn)")
        embed.add_field(name="HP Regen", value=f"{round(hp_regen,1):.1f}")
        embed.add_field(name="Mana", value=f"{round(mana,1):.1f}/{round(max_mana,1):.1f} (+{round(mana_regen,1):.1f}/turn)")
        embed.add_field(name="Mana Regen", value=f"{round(mana_regen,1):.1f}")
        embed.add_field(name="Attack", value=f"{round(atk,1):.1f}")
        embed.add_field(name="Defense", value=f"{round(defense,1):.1f}")
        embed.add_field(name="Strength", value=strength)
        embed.add_field(name="Dexterity", value=dexterity)
        embed.add_field(name="Intelligence", value=intelligence)
        embed.add_field(name="Crit Chance", value=f"{round(crit_chance*100,1):.1f}%")
        embed.add_field(name="Crit Damage", value=f"{round(crit_damage,2):.2f}x")
        embed.add_field(name="Evasion", value=f"{round(evasion_chance*100,1):.1f}%")
        embed.add_field(name="Spell Amplifier", value=f"+{round(bonus_spell_dmg,1):.1f}")
        # Show quest progress if on a quest
        if quest:
            embed.add_field(name="Quest", value=f"{quest} ({quest_progress})", inline=False)
        # Inventory
        if inv:
            items = inv.split(",")
            item_counts = {}
            for item in items:
                if item:
                    item_counts[item] = item_counts.get(item, 0) + 1
            lines = [f"{amount}x {name}" for name, amount in item_counts.items()]
            embed.add_field(name="Inventory", value="\n".join(lines), inline=False)
        # Show class choice prompt if eligible
        if char_class is None and level >= 3:
            embed.add_field(
                name="Class Choice",
                value="You can now choose a class! Use `/rpgclass <class>` (Warrior, Assassin, Mage).",
                inline=False
            )
        # Show coins/bank
        embed.set_footer(text=f"Coins: {coins} | Bank: {bank}")

        # --- Add equipped spells if class is chosen ---
        if char_class and char_class in SPELLS:
            # Load equipped spells from DB
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT equipped_spells FROM rpg_stats WHERE user_id = ?", (str(user_id),))
            row = cursor.fetchone()
            conn.close()
            if row and row[0]:
                equipped_spells = row[0].split(",")
                if equipped_spells:
                    embed.add_field(
                        name="Equipped Spells",
                        value=", ".join(equipped_spells),
                        inline=False
                    )
            embed.add_field(
                name="Tip",
                value="Use `/rpgspells` to view and manage your class spells.",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rpgspend", description="Spend skill points to upgrade your stats.")
    @rpg_started()
    async def rpgspend(self, ctx, stat: str, amount: int):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats
        if amount <= 0 or amount > skill_points:
            await ctx.send(f"You have {skill_points} skill points. Specify a valid amount to spend.")
            return
        stat = stat.lower()
        if stat not in ["strength", "dexterity", "intelligence"]:
            await ctx.send("Stat must be one of: strength, dexterity, intelligence.")
            return

        # Calculate new stat values and associated upgrades
        updates = {}
        # Scaling factor: higher level = less gain per point
        import math
        scaling = 0.8 + 0.2 / (math.sqrt(level) if level > 0 else 1)

        if stat == "strength":
            updates["strength"] = strength + amount
            updates["max_hp"] = round(max_hp + (0.6 * scaling * amount), 1)
            updates["hp_regen"] = round(hp_regen + (0.3 * scaling * amount), 1)
            updates["atk"] = round(atk + (0.1 * scaling * amount), 1)
            msg = (
                f"Added {amount} to Strength "
                f"(+{round(0.6*scaling*amount, 1)} Max HP, "
                f"+{0.3*scaling*amount:.1f} HP Regen, "
                f"+{0.2*scaling*amount:.1f} Attack)."
            )
        elif stat == "dexterity":
            updates["dexterity"] = dexterity + amount

            new_crit_chance = round(crit_chance + (0.0025 * scaling * amount), 3)
            new_crit_damage = round(crit_damage + (0.005 * scaling * amount), 3)
            new_evasion_chance = round(evasion_chance + (0.0025 * scaling * amount), 3)

            crit_chance_capped = min(0.5, new_crit_chance)
            crit_damage_capped = min(5.0, new_crit_damage)
            evasion_chance_capped = min(0.5, new_evasion_chance)

            updates["crit_chance"] = round(crit_chance_capped, 3)
            updates["crit_damage"] = round(crit_damage_capped, 3)
            updates["defense"] = round(defense + (0.1 * scaling * amount), 1)
            updates["evasion_chance"] = round(evasion_chance_capped, 3)

            warnings = []
            if new_crit_chance > 0.5:
                warnings.append("⚠️ Crit Chance is capped at 50%.")
            if new_crit_damage > 5.0:
                warnings.append("⚠️ Crit Damage is capped at x5.00.")
            if new_evasion_chance > 0.5:
                warnings.append("⚠️ Evasion is capped at 50%.")

            msg = (
                f"Added {amount} to Dexterity "
                f"(+{round(0.1*scaling*amount, 1):.1f} Defense, "
                f"+{0.25*scaling*amount:.1f}% Crit Rate, "
                f"+{0.5*scaling*amount:.1f}% Crit Damage, "
                f"+{0.5*scaling*amount:.1f}% Evasion)."
            )
            if warnings:
                msg += "\n" + "\n".join(warnings)
        elif stat == "intelligence":
            updates["intelligence"] = intelligence + amount
            old_max_mana = max_mana
            mana_increase = float(0.7 * scaling * amount)
            updates["max_mana"] = round(old_max_mana + mana_increase, 1)
            updates["mana_regen"] = round(mana_regen + (0.03 * scaling * amount), 1)
            updates["bonus_spell_dmg"] = round(bonus_spell_dmg + (0.5 * scaling * amount), 1)
            # Also increase current mana by the same amount, but do not exceed new max_mana
            updates["mana"] = round(min(updates["max_mana"], mana + mana_increase), 1)
            msg = (
                f"Added {amount} to Intelligence "
                f"(+{mana_increase:.1f} Max Mana, "
                f"+{0.1*scaling*amount:.1f} Mana Regen, "
                f"+{0.5*scaling*amount:.1f} Bonus Spell Damage)."
            )

        updates["skill_points"] = skill_points - amount
        update_rpg_stats(user_id, **updates)
        await ctx.send(f"{msg} You have {updates['skill_points']} skill points left.")

    @commands.hybrid_command(name="rpgclass", description="Choose your class at level 3 or higher.")
    @rpg_started()
    async def rpgclass(self, ctx, chosen_class: str):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats
        if char_class is not None:
            await ctx.send("You have already chosen a class.")
            return
        if level < 3:
            await ctx.send("You must reach level 3 to choose a class.")
            return

        chosen_class = chosen_class.capitalize()
        # Level-based scaling for class bonus

        class_data = {
            "Warrior": {
                "starter_weapon": "Iron Sword",
                "bonus": {
                    "max_hp": 4,        # Lowered from 6
                    "atk": 0.3 ,           # Lowered from 2
                    "defense": 1,
                    "hp_regen": 0.1,    # Lowered from 0.5
                    "strength": 1
                },
                "desc": "Warriors gain extra HP, Attack, Defense, and HP Regen."
            },
            "Assassin": {
                "starter_weapon": "Rusty Dagger",
                "bonus": {
                    "dexterity": 1,
                    "crit_chance": 0.02,
                    "crit_damage": 0.05,
                    "evasion_chance": 0.01,
                    "atk": 0.5
                },
                "desc": "Assassins gain extra Dexterity, Crit Chance, Crit Damage, Evasion, and Attack."
            },
            "Mage": {
                "starter_weapon": "Wooden Staff",
                "bonus": {
                    "max_mana": 7,      # Lowered from 10
                    "mana_regen": 0.7,  # Lowered from 1
                    "intelligence": 1,
                    "bonus_spell_dmg": 1.5  # Lowered from 1.5
                },
                "desc": "Mages gain extra Max Mana, Mana Regen, Intelligence, and Bonus Spell Damage."
            }
        }
        if chosen_class not in class_data:
            await ctx.send("Choose a class: Warrior, Assassin, or Mage.")
            return

        # Give starter weapon for class if not present
        starter_weapon = class_data[chosen_class]["starter_weapon"]
        coins, bank, inv = get_player(user_id)
        items = inv.split(",") if inv else []
        # Only add the starter weapon if the user doesn't already own it
        if starter_weapon not in items:
            items.append(starter_weapon)
            update_player_inventory(user_id, ",".join(items))

        # Do NOT auto-equip the starter weapon; keep the user's currently equipped weapon
        updates = {"char_class": chosen_class}
        # Apply class bonuses (scaled)
        bonus = class_data[chosen_class]["bonus"]
        # Only update the weapon if the user has no weapon equipped
        if not weapon:
            updates["weapon"] = starter_weapon
        # Correct stat indexes for get_rpg_stats tuple
        stat_index = {
            "max_hp": 3, "atk": 4, "defense": 5, "hp_regen": 15, "strength": 11,
            "dexterity": 12, "intelligence": 13,
            "max_mana": 18, "mana_regen": 17,  # <-- Corrected indexes
            "crit_chance": 19, "crit_damage": 20, "evasion_chance": 21, "bonus_spell_dmg": 22
        }
        for key, value in bonus.items():
            if key in stat_index:
                current = stats[stat_index[key]]
                # Clamp crit_chance and evasion_chance to a max of 1.0 (100%)
                if key in ("crit_chance", "evasion_chance"):
                    updates[key] = min(1.0, round(current + value, 4))
                else:
                    updates[key] = round(current + value, 2)
            else:
                updates[key] = value

        update_rpg_stats(user_id, **updates)
        await ctx.send(
            f"You are now a **{chosen_class}**! Starter weapon: {starter_weapon}.\n"
            f"{class_data[chosen_class]['desc']}"
        )
    
    @commands.hybrid_command(name="rpgencounter", description="Encounter a random monster! Supports solo and party encounters.")
    @rpg_started()
    async def rpgencounter(self, ctx):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return

        # --- Party logic: Only leader can start an encounter ---
        if user_id in self.active_parties:
            party_id = self.active_parties[user_id]
            party = self.parties[party_id]
            if party_id in self.active_battles:
                await ctx.send("Your party is already in a battle! Use `/rpgattack`.")
                return
            if party["leader"] != user_id:
                await ctx.send("Only the party leader can start an encounter.")
                return
            party_members = party["members"]
            # Calculate average party level
            levels = []
            for pid in party_members:
                pstats = get_rpg_stats(pid)
                if pstats:
                    levels.append(pstats[0])
            avg_level = int(sum(levels) / len(levels)) if levels else 1
        else:
            if user_id in self.active_battles:
                await ctx.send("You are already in a battle! Use `/rpgattack`.")
                return
            party_members = {user_id}
            avg_level = stats[0] if stats else 1

        guild_id = ctx.guild.id
        monsters = self.load_monsters(guild_id)

        # --- Progressive rarity unlocks based on average party level ---
        rarity_thresholds = {
            "common": 1,
            "uncommon": 6,
            "rare": 12,
            "epic": 20,
            "legendary": 30
        }
        base_odds = {
            "common": 0.7,
            "uncommon": 0.0,
            "rare": 0.0,
            "epic": 0.0,
            "legendary": 0.0
        }
        odds = base_odds.copy()
        level = avg_level
        if level >= rarity_thresholds["uncommon"]:
            odds["uncommon"] += 0.15 + 0.02 * (level - rarity_thresholds["uncommon"])
            odds["common"] -= 0.10 + 0.02 * (level - rarity_thresholds["uncommon"])
        if level >= rarity_thresholds["rare"]:
            odds["rare"] += 0.08 + 0.01 * (level - rarity_thresholds["rare"])
            odds["common"] -= 0.05 + 0.005 * (level - rarity_thresholds["rare"])
            odds["uncommon"] -= 0.03 + 0.005 * (level - rarity_thresholds["rare"])
        if level >= rarity_thresholds["epic"]:
            odds["epic"] += 0.05 + 0.01 * (level - rarity_thresholds["epic"])
            odds["common"] -= 0.03 + 0.003 * (level - rarity_thresholds["epic"])
            odds["uncommon"] -= 0.02 + 0.003 * (level - rarity_thresholds["epic"])
            odds["rare"] -= 0.01 + 0.002 * (level - rarity_thresholds["epic"])
        if level >= rarity_thresholds["legendary"]:
            odds["legendary"] += 0.02 + 0.002 * (level - rarity_thresholds["legendary"])
            odds["common"] -= 0.06 + 0.001 * (level - rarity_thresholds["legendary"])
            odds["uncommon"] -= 0.05 + 0.001 * (level - rarity_thresholds["legendary"])
            odds["rare"] -= 0.04 + 0.001 * (level - rarity_thresholds["legendary"])
            odds["epic"] -= 0.03 + 0.001 * (level - rarity_thresholds["legendary"])

        for k in odds:
            odds[k] = max(0.0, odds[k])
        total = sum(odds.values())
        if total > 0:
            for k in odds:
                odds[k] /= total
        else:
            odds = {"common": 1.0, "uncommon": 0.0, "rare": 0.0, "epic": 0.0, "legendary": 0.0}

        rarity_order = ["common", "uncommon", "rare", "epic", "legendary"]
        monsters_by_rarity = {r: [] for r in rarity_order}
        for m in monsters:
            monsters_by_rarity.get(m["rarity"], monsters_by_rarity["common"]).append(m)

        roll = random.random()
        cumulative = 0
        selected_rarity = "common"
        for rarity in rarity_order:
            cumulative += odds[rarity]
            if roll <= cumulative:
                selected_rarity = rarity
                break

        # After selecting the pool:
        pool = monsters_by_rarity[selected_rarity]
        if not pool:
            pool = monsters_by_rarity["common"]
        if not pool:
            await ctx.send("No monsters are available for encounters. Please ask an admin to add monsters to the database.")
            return

        # Prevent raid monsters from appearing in normal encounters (solo or party)
        pool = [m for m in pool if m.get("rarity") != "raid"]

        if not pool:
            await ctx.send("No monsters are available for solo encounters at this rarity.")
            return

        monster = random.choice(pool).copy()

        # --- Scale monster stats for party size ---
        party_size = len(party_members)
        if party_size > 1:
            monster["hp"] = int(monster["hp"] * (1 + 0.7 * (party_size - 1)))
            monster["max_hp"] = int(monster["max_hp"] * (1 + 0.7 * (party_size - 1)))
            monster["atk"] = int(monster["atk"] * (1 + 0.4 * (party_size - 1)))
            monster["defense"] = int(monster.get("defense", 0) * (1 + 0.2 * (party_size - 1)))

        # --- Legendary warning ---
        if selected_rarity == "legendary":
            confirm_view = ConfirmView(ctx)
            embed = discord.Embed(
                title="⚠️ Legendary Monster Encountered!",
                description="This is a party-wide encounter. All party members will face this monster together!"
                if party_size > 1 else None,
            )
            await ctx.send(embed=embed, view=confirm_view)
            timeout = await confirm_view.wait()
            if confirm_view.value is None:
                await ctx.send("No response. Encounter cancelled.")
                return
            if not confirm_view.value:
                await ctx.send("You backed out from the legendary encounter.")
                return

        # --- Start the encounter ---
        if party_size > 1:
            party_id = self.active_parties[user_id]
            self.active_battles[party_id] = monster
            self.active_battles[f"{party_id}_regen_remainder"] = 0.0
            monster["regen_remainder"] = 0.0
            member_mentions = ", ".join(f"<@{uid}>" for uid in party_members)
            await ctx.send(
                f"Your party ({member_mentions}) encounters **{monster['name']}** ({monster['rarity'].capitalize()})!\n"
                f"HP: {monster['hp']}, ATK: {monster['atk']}\n"
                "All party members can use `/rpgattack` to fight!"
            )
        else:
            self.active_battles[user_id] = monster
            self.active_battles[f"{user_id}_regen_remainder"] = 0.0
            monster["regen_remainder"] = 0.0
            await ctx.send(
                f"A wild **{monster['name']}** ({monster['rarity'].capitalize()}) appears! (HP: {monster['hp']}, ATK: {monster['atk']})\n"
                "Use `/rpgattack` to fight!"
            )

    @commands.hybrid_command(name="rpgattack", description="Attack the monster! (Use /rpgattack [spell name] [target] to cast a spell)")
    @rpg_started()
    async def rpgattack(self, ctx, spell_name: str = None, target: str = None):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return

        # --- Party/monster setup ---
        if user_id in self.active_parties:
            party_id = self.active_parties[user_id]
            monster = self.active_battles.get(party_id)
            party_members = self.parties[party_id]["members"]
            turn_key = f"party_{party_id}"
        else:
            monster = self.active_battles.get(user_id)
            party_members = {user_id}
            turn_key = f"solo_{user_id}"

        if not monster:
            await ctx.send("You are not in a battle. Use `/rpgencounter`.")
            return

        # Prevent solo players from attacking raid monsters
        if monster and monster.get("rarity") == "raid" and user_id not in self.active_parties:
            await ctx.send("Raid bosses can only be fought by parties. Use `/rpgraid` with a party!")
            return

        # --- Turn-based logic for parties ---
        if len(party_members) > 1:
            if not hasattr(self, "party_turn_actions"):
                self.party_turn_actions = {}
            # Defensive: always initialize the turn set
            if turn_key not in self.party_turn_actions:
                self.party_turn_actions[turn_key] = set()
            if user_id in self.party_turn_actions[turn_key]:
                await ctx.send("You have already attacked this turn. Wait for your party to finish their moves!")
                return

        # Target resolution
        target_type, target_user_id = self.resolve_attack_target(ctx, target, party_members)

        # --- Spell casting logic ---
        if spell_name:
            msg = await self.handle_spell_attack(ctx, user_id, stats, spell_name, target_type, target_user_id, monster, party_members)
        else:
            msg = await self.handle_player_attack(ctx, user_id, stats, monster, party_members, target_type, target_user_id)

        # Save that this user has acted this turn (for parties)
        if len(party_members) > 1:
            self.party_turn_actions[turn_key].add(user_id)
            # Display party turn progress
            attacked_ids = self.party_turn_actions[turn_key]
            attacked_mentions = [f"<@{uid}>" for uid in attacked_ids]
            not_attacked_mentions = [f"<@{uid}>" for uid in party_members if uid not in attacked_ids]
            status_msg = (
                f"**Party Turn Progress:**\n"
                f"Attacked: {', '.join(attacked_mentions) if attacked_mentions else 'None'}\n"
                f"Waiting: {', '.join(not_attacked_mentions) if not_attacked_mentions else 'None'}"
            )
        else:
            status_msg = ""

        # Show the result of the player's attack and party turn status
        await ctx.send(self.format_battle_message(msg) + ("\n" + status_msg if status_msg else ""))

        # If monster is defeated, clean up and return
        if monster["hp"] <= 0:
            if len(party_members) > 1:
                self.active_battles.pop(party_id, None)
                self.party_turn_actions.pop(turn_key, None)
            else:
                self.active_battles.pop(user_id, None)
            return

        # If all party members have acted, monster attacks a random alive party member
        if len(party_members) > 1 and self.party_turn_actions[turn_key] >= set(party_members):
            alive_members = [pid for pid in party_members if get_rpg_stats(pid)[2] > 0]
            if alive_members:
                target_id = random.choice(list(alive_members))
                target_stats = get_rpg_stats(target_id)
                boss_msg = f"\n**Monster's Turn!**\n"
                boss_msg = self.monster_attack_phase(ctx, target_id, monster, target_stats, boss_msg)
                await ctx.send(boss_msg)
            # Reset for next turn
            self.party_turn_actions[turn_key] = set()

    def resolve_attack_target(self, ctx, target, party_members):
        user_id = ctx.author.id
        target_user_id = None
        if not target or target.lower() in ("monster", "enemy"):
            target_type = "monster"
        elif target.lower() in ("self", "me", str(ctx.author), str(ctx.author.id), f"<@{ctx.author.id}>"):
            target_type = "self"
            target_user_id = user_id
        else:
            try:
                if target.startswith("<@") and target.endswith(">"):
                    target_id = int(target.strip("<@!>"))
                else:
                    target_id = int(target)
                if target_id in party_members:
                    target_type = "party"
                    target_user_id = target_id
                else:
                    target_type = "monster"
            except Exception:
                target_type = "monster"
        return target_type, target_user_id

    async def handle_spell_attack(self, ctx, user_id, stats, spell_name, target_type, target_user_id, monster, party_members, raid_mode=False):
        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats

        if not char_class or char_class not in SPELLS:
            return "You must choose a class to use spells. Use `/rpgclass`."
        spell = next((s for s in SPELLS[char_class] if s["name"].lower() == spell_name.lower()), None)
        if not spell:
            return "Spell not found. Use `/rpgspells` to see your available spells."
        if mana < spell["mana"]:
            return f"Not enough mana! You have {mana:.1f}/{max_mana:.1f} mana."

        msg, updates = await self.handle_spell_cast(
            ctx, user_id, spell, spell_name, char_class, atk, strength, dexterity, intelligence,
            bonus_spell_dmg, max_hp, hp, max_mana, mana, weapon, party_members, target_type, target_user_id, monster
        )
        updates["mana"] = updates.get("mana", mana - spell["mana"])
        update_rpg_stats(user_id, **updates)

        # Monster debuffs and defeat check
        msg_debuff, monster_dead = self.process_monster_debuffs(monster)
        msg += msg_debuff
        if monster_dead or monster["hp"] <= 0:
            msg += self.handle_monster_defeat(ctx, user_id, monster, stats, msg, weapon, quest, quest_progress)
            return msg

        if raid_mode:
            # In raid mode, do not process monster attack or regen here
            return self.format_battle_message(msg)

        msg += self.monster_attack_phase(ctx, user_id, monster, stats, "")
        msg += self.regen_phase(user_id, monster, stats, hp, max_hp, mana, max_mana, hp_regen, mana_regen)
        return self.format_battle_message(msg)

    def format_battle_message(self, msg):
        import re
        # Remove accidental newlines after decimals
        msg = re.sub(r'(\d+)\.\n(\d+)', r'\1.\2', msg)
        # Remove accidental double newlines
        msg = re.sub(r'\n{2,}', r'\n', msg)
        # Strip leading/trailing whitespace and ensure single newline between events
        return msg.strip()

    async def handle_player_attack(self, ctx, user_id, stats, monster, party_members, target_type, target_user_id, raid_mode=False):
        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats

        msg = ""
        # --- Player buffs/debuffs ---
        player_state = self.active_battles.setdefault(f"{user_id}_state", {})
        atk_mod, def_mod, evasion_mod, spell_dmg_mod = self.process_player_buffs(user_id, player_state)
        str_bonus = strength // 2
        int_bonus = intelligence // 2

        # --- Monster debuffs and defeat check ---
        msg_debuff, monster_dead = self.process_monster_debuffs(monster)
        msg += msg_debuff
        if monster_dead:
            msg += self.handle_monster_defeat(ctx, user_id, monster, stats, msg, weapon, quest, quest_progress)
            return msg

        # --- Initiative roll: who attacks first? ---
        if raid_mode:
            # Only do the player's attack, skip monster attack and regen
            msg += await self._player_attack_sequence(
                ctx, user_id, stats, monster, party_members, target_type, target_user_id,
                atk_mod, str_bonus, crit_chance, crit_damage, weapon, bonus_spell_dmg,
                hp, max_hp, mana, max_mana, hp_regen, mana_regen, quest, quest_progress
            )
            return msg

        player_first = random.choice([True, False])
        if player_first:
            # Player attacks first
            msg += await self._player_attack_sequence(
                ctx, user_id, stats, monster, party_members, target_type, target_user_id,
                atk_mod, str_bonus, crit_chance, crit_damage, weapon, bonus_spell_dmg,
                hp, max_hp, mana, max_mana, hp_regen, mana_regen, quest, quest_progress
            )
            # If monster is defeated, skip monster attack and regen
            if monster["hp"] <= 0:
                return msg
            # Monster attacks
            msg += self.monster_attack_phase(ctx, user_id, monster, stats, "")
            # If monster is defeated after monster attack, skip regen
            if monster["hp"] <= 0:
                return msg
            # Regen phase
            msg += self.regen_phase(user_id, monster, stats, hp, max_hp, mana, max_mana, hp_regen, mana_regen)
        else:
            # Monster attacks first
            msg += self.monster_attack_phase(ctx, user_id, monster, stats, "")
            # If player is defeated, skip player attack and regen
            if "You have been defeated!" in msg:
                return msg
            # Player attacks
            msg += await self._player_attack_sequence(
                ctx, user_id, stats, monster, party_members, target_type, target_user_id,
                atk_mod, str_bonus, crit_chance, crit_damage, weapon, bonus_spell_dmg,
                hp, max_hp, mana, max_mana, hp_regen, mana_regen, quest, quest_progress
            )
            # If monster is defeated after player attack, skip regen
            if monster["hp"] <= 0:
                return msg
            # Regen phase
            msg += self.regen_phase(user_id, monster, stats, hp, max_hp, mana, max_mana, hp_regen, mana_regen)
        return self.format_battle_message(msg)
    
    async def _player_attack_sequence(
        self, ctx, user_id, stats, monster, party_members, target_type, target_user_id,
        atk_mod, str_bonus, crit_chance, crit_damage, weapon, bonus_spell_dmg,
        hp, max_hp, mana, max_mana, hp_regen, mana_regen, quest, quest_progress
    ):
        msg = ""
        crit = random.random() < crit_chance
        monster_evasion = monster.get("evasion_chance", 0.0)

        # --- FIX: Case-insensitive weapon lookup ---
        actual_weapon = next((w for w in WEAPON_ITEMS if w.lower() == (weapon or "").lower()), None)
        if not actual_weapon:
            weapon_bonus = 0
            attack_flavor = "You have no weapon equipped! You attack bare-handed with your base strength.\n"
            weapon_item = {"damage": 0, "rarity": "common"}
        else:
            weapon_item = WEAPON_ITEMS[actual_weapon]
            weapon_bonus = weapon_item.get("damage", 0)
            attack_flavor = ""

        if weapon_item.get("effect") == "never_miss":
            monster_evasion = 0
        if random.random() < monster_evasion:
            msg += f"The {monster['name']} evaded your attack!\n"
            return msg

        effect_msgs = []
        # --- More randomized damage ---
        # Add a random factor: ±10% of the total calculated damage (after all bonuses)
        base_dmg = stats[4] + atk_mod + weapon_bonus + str_bonus
        variance = random.uniform(0.9, 1.1)  # 90% to 110%
        base_dmg = base_dmg * variance + random.randint(-1, 1)
        if crit:
            base_dmg = int(base_dmg * crit_damage)

        monster_def = monster.get("defense", 0)
        base_dmg = max(1, base_dmg - monster_def)

        # Use the actual_weapon for special effects
        base_dmg, hp, effect_msgs = self.apply_weapon_special_effects(
            user_id, actual_weapon, monster, base_dmg, hp, max_hp, crit, bonus_spell_dmg
        )

        if monster.get("debuffs", {}).get("curse", 0) > 0:
            base_dmg = int(base_dmg * 1.2)
            monster["debuffs"]["curse"] -= 1
            effect_msgs.append("Your attack deals extra damage due to curse!")

        monster["hp"] -= base_dmg

        # Always start player's attack on a new line
        if msg and not msg.endswith('\n'):
            msg += '\n'
        msg += f"You attack the {monster['name']} for {round(base_dmg, 1)} damage! (Monster HP: {max(round(monster['hp'], 1), 0)})\n"
        if crit:
            msg += "**Critical hit!**\n"
        if effect_msgs:
            msg += "\n".join(effect_msgs) + "\n"

        if monster["hp"] <= 0:
            msg += self.handle_monster_defeat(ctx, user_id, monster, stats, msg, weapon, quest, quest_progress)
            return msg
        if msg and not msg.endswith('\n'):
            msg += '\n'
        return msg

    async def handle_spell_cast(
        self, ctx, user_id, spell, spell_name, char_class, atk, strength, dexterity, intelligence,
        bonus_spell_dmg, max_hp, hp, max_mana, mana, weapon, party_members, target_type, target_user_id, monster
    ):
        """
        Handles spell casting logic using spell_type and amount.
        Returns (msg, updates).
        """
        updates = {}
        msg = ""
        player_state = self.active_battles.setdefault(f"{user_id}_state", {})

        # Prevent self-targeting with damaging spells
        if spell["spell_type"] == "damage" and target_type == "self":
            return "You cannot target yourself with damaging spells.", updates

        # --- Damage Spells ---
        if spell["spell_type"] == "damage":
            # Calculate damage (can be customized per class)
            base = spell.get("amount", 0)
            # Add scaling for class, stats, or randomness if desired
            if char_class == "Warrior":
                dmg = base + atk + strength + bonus_spell_dmg + random.randint(0, 5)
            elif char_class == "Assassin":
                crit = random.random() < (0.2 + spell.get("crit_chance", 0))
                dmg = base + atk + dexterity + bonus_spell_dmg + random.randint(0, 5)
                if crit:
                    dmg = int(dmg * (1.5 + spell.get("crit_damage", 0)))
                    msg += "**Critical!**\n"
            elif char_class == "Mage":
                dmg = base + bonus_spell_dmg * 2 + random.randint(0, 5)
            else:
                dmg = base

            monster["hp"] -= dmg
            msg += f"You cast {spell['name']} and deal {round(dmg,1):.1f} damage to the {monster['name']}!\n"

            # Special effects (e.g., stun, poison, etc.)
            if spell["effect"] in ("warrior_shield_bash", "mage_lightning_bolt") and random.random() < 0.3:
                monster["stunned"] = True
                msg += "The enemy is stunned!\n"
            if spell["effect"] == "assassin_poison_blade":
                monster.setdefault("debuffs", {})["poison"] = 3
                msg += "The enemy is poisoned for 3 turns!\n"
            if spell["effect"] == "mage_frost_nova":
                monster.setdefault("debuffs", {})["frost_nova"] = 2
                msg += "The enemy's attack is reduced for 2 turns!\n"
            if spell["effect"] == "assassin_mark_for_death":
                monster.setdefault("debuffs", {})["mark_for_death"] = 2
                msg += "The enemy is marked for death for 2 turns!\n"

        # --- Buff Spells ---
        elif spell["spell_type"] == "buff":
            if spell["effect"] in ("warrior_battle_cry", "warrior_iron_wall", "warrior_taunt", "assassin_smoke_bomb", "assassin_adrenaline_rush", "mage_ice_barrier", "mage_arcane_surge", "mage_mana_shield", "mage_haste", "assassin_vanish"):
                # Use spell.amount as turns or value
                buff_name = spell["effect"].replace(f"{char_class.lower()}_", "")
                player_state.setdefault("buffs", {})[buff_name] = int(spell.get("amount", 2))
                msg += f"You cast {spell['name']}! Buff applied for {spell.get('amount', 2)} turns.\n"
            elif spell["effect"] == "warrior_second_wind":
                heal = int(max_hp * spell.get("amount", 0.25)) + strength + bonus_spell_dmg
                hp = min(max_hp, hp + heal)
                updates["hp"] = hp
                msg += f"You use Second Wind and heal {round(heal,1):.1f} HP! (Your HP: {round(hp,1):.1f}/{round(max_hp,1):.1f})\n"
            elif spell["effect"] == "warrior_rally":
                heal = spell.get("amount", 10) + strength + bonus_spell_dmg
                if user_id in self.active_parties:
                    party_id = self.active_parties[user_id]
                    party_members = self.parties[party_id]["members"]
                    for pid in party_members:
                        p_stats = get_rpg_stats(pid)
                        if p_stats:
                            p_hp, p_max_hp = p_stats[2], p_stats[3]
                            new_hp = min(p_max_hp, p_hp + heal)
                            update_rpg_stats(pid, hp=new_hp)
                    msg += f"You rally your party! All members heal {round(heal,1):.1f} HP.\n"
                else:
                    hp = min(max_hp, hp + heal)
                    updates["hp"] = hp
                    msg += f"You rally yourself and heal {round(heal,1):.1f} HP! (Your HP: {round(hp,1):.1f}/{round(max_hp,1):.1f})\n"
            elif spell["effect"] == "mage_heal":
                heal = spell.get("amount", 18) + bonus_spell_dmg + random.randint(2, 8)
                if target_type == "self":
                    hp = min(max_hp, hp + heal)
                    updates["hp"] = hp
                    msg += f"You cast Heal and restore {round(heal,1):.1f} HP to yourself! (Your HP: {round(hp,1):.1f}/{round(max_hp,1):.1f})\n"
                elif target_type == "party" and target_user_id:
                    t_stats = get_rpg_stats(target_user_id)
                    if not t_stats:
                        await ctx.send("That party member does not have an RPG profile.")
                        return None, None
                    t_hp, t_max_hp = t_stats[2], t_stats[3]
                    t_hp = min(t_max_hp, t_hp + heal)
                    update_rpg_stats(target_user_id, hp=t_hp)
                    msg += f"You cast Heal and restore {round(heal,1):.1f} HP to <@{target_user_id}>! (Their HP: {round(t_hp,1):.1f}/{round(t_max_hp,1):.1f})\n"
                else:
                    hp = min(max_hp, hp + heal)
                    updates["hp"] = hp
                    msg += f"You cast Heal and restore {round(heal,1):.1f} HP to yourself! (Your HP: {round(hp,1):.1f}/{round(max_hp,1):.1f})\n"
            elif spell["effect"] == "assassin_vanish":
                player_state.setdefault("buffs", {})["vanish"] = 1
                heal = spell.get("amount", 8) + bonus_spell_dmg
                hp = min(max_hp, hp + heal)
                updates["hp"] = hp
                msg += f"You vanish into the shadows, becoming untargetable for 1 turn and healing {round(heal,1):.1f} HP! (Your HP: {round(hp,1):.1f}/{round(max_hp,1):.1f})\n"
            elif spell["effect"] == "assassin_adrenaline_rush":
                player_state.setdefault("buffs", {})["adrenaline_rush"] = spell.get("amount", 2)
                mana_restored = min(max_mana - mana, 5 + bonus_spell_dmg)
                updates["mana"] = mana + mana_restored
                msg += f"You surge with adrenaline! Restored {round(mana_restored,1):.1f} mana and increased crit chance for 2 turns.\n"
            elif spell["effect"] == "mage_arcane_surge":
                mana_restored = min(max_mana - mana, 8 + bonus_spell_dmg)
                updates["mana"] = mana + mana_restored
                player_state.setdefault("buffs", {})["arcane_surge"] = spell.get("amount", 3)
                msg += f"You surge with arcane power! Restored {round(mana_restored,1):.1f} mana and increased spell damage for 3 turns.\n"

        # --- Debuff Spells ---
        elif spell["spell_type"] == "debuff":
            if spell["effect"] == "warrior_taunt":
                monster["taunted"] = user_id
                player_state.setdefault("buffs", {})["taunt"] = spell.get("amount", 2)
                msg += f"You taunt the {monster['name']}! It will focus attacks on you and you take reduced damage for {spell.get('amount', 2)} turns.\n"
            elif spell["effect"] == "assassin_mark_for_death":
                monster.setdefault("debuffs", {})["mark_for_death"] = spell.get("amount", 2)
                msg += f"You mark the {monster['name']} for death! It will take increased damage for {spell.get('amount', 2)} turns.\n"
            else:
                # Generic debuff: apply to monster
                debuff_name = spell["effect"].replace(f"{char_class.lower()}_", "")
                monster.setdefault("debuffs", {})[debuff_name] = spell.get("amount", 2)
                msg += f"You cast {spell['name']}! Debuff applied for {spell.get('amount', 2)} turns.\n"

        else:
            msg = "Spell effect not implemented."

        return msg, updates
    
    def handle_monster_defeat(self, ctx, user_id, monster, stats, msg, weapon, quest, quest_progress):
        """
        Handles monster defeat: EXP, level up, loot, quest progress, and cleanup.
        Returns a string to append to msg.
        """
        # Unpack stats
        (
            level, exp, hp, max_hp, atk, defense, char_class, _weapon, _quest, _quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats

        defeat_msg = ""
        int_bonus = 0  # Add intelligence bonus logic if needed

        # EXP gain
        gained_exp = monster.get("exp", 0) + int_bonus
        exp += gained_exp
        defeat_msg += f"You defeated the {monster['name']}! You gain {gained_exp} EXP."

        # Level up logic
        while exp >= exp_to_next:
            exp -= exp_to_next
            level += 1
            atk += 0.3
            defense += 0.2
            max_hp += 2.5
            hp = max_hp
            skill_points += 2
            exp_to_next = exp_to_next_level(level)
            defeat_msg += f"\n**Level up!** You are now level {level}. You gained 2 skill points."
            if level == 3 and (char_class is None or char_class == ""):
                defeat_msg += "\nYou can now choose a class! Use `/rpgclass <class>`."
            self.active_battles[f"{user_id}_regen_remainder"] = 0.0

        defeat_msg += f"\nYou now have {skill_points} skill points."

        # Loot (randomized drop chance, legendary always drops)
        loot = monster.get("loot", None)
        rarity = monster.get("rarity", "common")
        loot_drop_chance = {
            "common": 0.5,
            "uncommon": 0.4,
            "rare": 0.35,
            "epic": 0.3,
            "legendary": 1.0  # Legendary always drops loot
        }
        drop_chance = loot_drop_chance.get(rarity, 0.4)
        if loot and (random.random() < drop_chance or rarity == "legendary"):
            coins, bank, inv = get_player(user_id)
            items = [item for item in inv.split(",") if item]  # Filter out empty strings
            items.append(loot)
            update_player_inventory(user_id, ",".join(items))
            defeat_msg += f"\nYou found a **{loot}**!"
        elif loot:
            defeat_msg += f"\nNo loot dropped this time."

        # --- Quest progress update ---
        quests = self.get_quests(ctx.guild.id)
        progress_updated = False
        if quest and quest in quests:
            quest_data = quests[quest]
            quest_target = quest_data["target"].lower()
            monster_name = monster["name"].lower()

            if quest_target == "mixed":
                mixed_targets = ["slime", "goblin", "wolf", "orc", "bandit"]
                if any(t in monster_name for t in mixed_targets):
                    quest_progress += 1
                    progress_updated = True
            elif quest_target == "weapon":
                pass  # Implement weapon quest logic if needed
            elif quest_target == "magic":
                if weapon and ("staff" in weapon.lower() or "wand" in weapon.lower()):
                    quest_progress += 1
                    progress_updated = True
            elif quest_target == "dagger":
                if weapon and ("dagger" in weapon.lower() or "knife" in weapon.lower()):
                    quest_progress += 1
                    progress_updated = True
            elif quest_target == "sword":
                if weapon and ("sword" in weapon.lower() or "axe" in weapon.lower()):
                    quest_progress += 1
                    progress_updated = True
            else:
                if quest_target in monster_name:
                    quest_progress += 1
                    progress_updated = True

            if progress_updated:
                defeat_msg += f"\nQuest progress: {quest_progress}/{quest_data['amount']}"
                if quest_progress >= int(quest_data["amount"]):
                    coins, bank, inv = get_player(user_id)
                    items = inv.split(",") if inv else []
                    items.append(quest_data["reward"])
                    update_player_inventory(user_id, ",".join(items))
                    defeat_msg += f"\n**Quest complete!** You received: {quest_data['reward']}"
                    quest = None
                    quest_progress = 0

        # Update stats in DB
        update_rpg_stats(
            user_id,
            level=level,
            exp=exp,
            hp=hp,
            max_hp=max_hp,
            atk=atk,
            defense=defense,
            quest=quest,
            quest_progress=quest_progress,
            skill_points=skill_points,
            exp_to_next=exp_to_next
        )

        # Remove from active battles/cleanup
        if user_id in self.active_parties:
            party_id = self.active_parties[user_id]
            if party_id in self.active_battles:
                del self.active_battles[party_id]
            self.active_battles.pop(f"{party_id}_regen_remainder", None)
            self.active_battles.pop(f"{party_id}_state", None)
        else:
            if user_id in self.active_battles:
                del self.active_battles[user_id]
            self.active_battles.pop(f"{user_id}_regen_remainder", None)
            self.active_battles.pop(f"{user_id}_state", None)

        return defeat_msg

    def regen_phase(self, user_id, monster, stats, hp, max_hp, mana, max_mana, hp_regen, mana_regen):
        # Always fetch the latest HP and Mana from the DB to avoid using stale values
        db_stats = get_rpg_stats(user_id)
        if db_stats:
            hp = db_stats[2]
            max_hp = db_stats[3]
            mana = db_stats[16]
            max_mana = db_stats[18]
        msg = ""

        # --- Prevent regen if player is dead ---
        if hp <= 0:
            return msg

        # --- HP Regeneration for Player (accumulating fractional) ---
        regen_factor = 0.5  # Reduce regen to 50% (adjust as desired)
        player_regen_rem = self.active_battles.get(f"{user_id}_regen_remainder", 0.0)
        total_regen = hp_regen * regen_factor + player_regen_rem
        regen_amt = round(total_regen, 2)
        regen_int = int(regen_amt)
        player_regen_rem = round(regen_amt - regen_int, 2)

        if hp > 0 and hp < max_hp and regen_amt > 0:
            hp_gain = min(regen_amt, max_hp - hp)
            hp = min(max_hp, hp + hp_gain)
            msg += f"\nYou regenerate {hp_gain:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})"
            update_rpg_stats(user_id, hp=hp)
        self.active_battles[f"{user_id}_regen_remainder"] = player_regen_rem

        # --- Mana Regeneration for Player (accumulating fractional) ---
        mana_regen_factor = 0.5  # Reduce mana regen to 50% (adjust as desired)
        player_mana_regen_rem = self.active_battles.get(f"{user_id}_mana_regen_remainder", 0.0)
        total_mana_regen = mana_regen * mana_regen_factor + player_mana_regen_rem
        mana_regen_amt = round(total_mana_regen, 2)
        mana_regen_int = int(mana_regen_amt)
        player_mana_regen_rem = round(mana_regen_amt - mana_regen_int, 2)

        if hp > 0 and mana < max_mana and mana_regen_amt > 0:
            mana_gain = min(mana_regen_amt, max_mana - mana)
            mana = min(max_mana, mana + mana_gain)
            msg += f"\nYou regenerate {mana_gain:.1f} Mana! (Your Mana: {mana:.1f}/{max_mana:.1f})"
            update_rpg_stats(user_id, mana=mana)
        self.active_battles[f"{user_id}_mana_regen_remainder"] = player_mana_regen_rem

        # --- HP Regeneration for Monster (accumulating fractional) ---
        monster_regen_rem = monster.get("regen_remainder", 0.0)
        mregen = monster.get("hp_regen", 0)
        total_mregen = (mregen or 0) + monster_regen_rem
        mregen_amt = round(total_mregen, 2)
        mregen_int = int(mregen_amt)
        monster_regen_rem = round(mregen_amt - mregen_int, 2)

        if monster["hp"] > 0 and mregen_amt > 0 and monster["hp"] < monster["max_hp"]:
            m_gain = min(mregen_amt, monster["max_hp"] - monster["hp"])
            monster["hp"] = min(monster["max_hp"], monster["hp"] + m_gain)
            msg += f"\nThe {monster['name']} regenerates {m_gain:.1f} HP! (Monster HP: {monster['hp']:.1f}/{monster['max_hp']:.1f})"
        monster["regen_remainder"] = monster_regen_rem

        if msg and not msg.startswith('\n'):
            msg = '\n' + msg
        return msg
    
    def monster_attack_phase(self, ctx, user_id, monster, stats, msg):
        # Always end previous message with a newline
        if msg and not msg.endswith('\n'):
            msg += '\n'
        # Unpack player stats
        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats

        # Get player buffs/debuffs
        player_state = self.active_battles.setdefault(f"{user_id}_state", {})
        atk_mod, def_mod, evasion_mod, spell_dmg_mod = self.process_player_buffs(user_id, player_state)

        # Evasion check
        evasion_total = min(0.25, 0.01 * dexterity + evasion_chance + evasion_mod)
        if monster.get("stunned", False):
            msg += f"The {monster['name']} is stunned and cannot attack this turn!\n"
            monster["stunned"] = False
            return msg
        elif random.random() < evasion_total:
            msg += f"You evaded the {monster['name']}'s attack!\n"
            return msg

        # Monster attack
        monster_crit = random.random() < monster.get("crit_chance", 0.0)
        monster_crit_damage = monster.get("crit_damage", 1.0)
        monster_base_dmg = monster["atk"] - (defense + def_mod) + random.randint(-1, 1)
        if monster_crit:
            monster_base_dmg = int(monster_base_dmg * monster_crit_damage)
        monster_dmg = max(1, monster_base_dmg)
        hp -= monster_dmg

        msg += f"The {monster['name']} attacks you for {round(monster_dmg, 1)} damage! (Your HP: {max(round(hp, 1), 0)})\n"
        if monster_crit:
            msg += "**Critical hit!**\n"

        # --- Monster Signature Attack Logic ---
        sign_attack = monster.get("sign_attack")
        rarity = monster.get("rarity", "common")
        sign_chance = {"rare": 0.25, "epic": 0.33, "legendary": 0.5}.get(rarity, 0)
        if sign_attack and random.random() < sign_chance:
            msg, hp = self.handle_signature_attack(user_id, monster, sign_attack, hp, max_hp, msg)

        # Revive/defeat logic
        if hp <= 0:
            coins, bank, inv = get_player(user_id)
            items = inv.split(",") if inv else []
            revive_item = None
            if "Phoenix Down" in items:
                revive_item = "Phoenix Down"
                hp = max_hp
            elif "Revive Feather" in items:
                revive_item = "Revive Feather"
                hp = int(max_hp * 0.7)
            if revive_item:
                items.remove(revive_item)
                update_player_inventory(user_id, ",".join(items))
                update_rpg_stats(user_id, hp=hp)
                msg += (
                    f"\nYou were defeated, but your **{revive_item}** activates!"
                    f"\nYou revive with {hp:.1f}/{max_hp:.1f} HP and continue the fight!\n"
                )
            else:
                # --- Only remove weapons/items if NOT a raid boss ---
                if monster.get("rarity") == "raid":
                    mana = max_mana  # Restore Mana to max after raid defeat
                    hp = max_hp  # Restore HP to max after raid defeat
                    update_rpg_stats(user_id, hp=hp, mana=mana)
                    msg += "\nYou have been defeated by the raid boss! Your HP and Mana has been restored. You keep your items and can try again tomorrow.\n"
                    # --- Set 24-hour raid cooldown for this user ---
                    set_cooldown(user_id, f"{RAID_COOLDOWN_COMMAND}_{ctx.guild.id}", datetime.datetime.utcnow())
                    # --- Remove defeated player from raid participants ---
                    raid_state = load_raid_state(ctx.guild.id)
                    if raid_state and user_id in raid_state["participants"]:
                        raid_state["participants"].remove(user_id)
                        save_raid_state(ctx.guild.id, raid_state)
                else:
                    remove_all_rpg_items_from_inventory(user_id)
                    msg += "\nYou have been defeated! Use `/rpgstart` to try again.\n"
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM rpg_stats WHERE user_id = ?", (str(user_id),))
                    conn.commit()
                    conn.close()
                if user_id in self.active_battles:
                    del self.active_battles[user_id]
                self.active_battles.pop(f"{user_id}_regen_remainder", None)
                self.active_battles.pop(f"{user_id}_state", None)
        update_rpg_stats(user_id, hp=hp)
        return msg

    def handle_signature_attack(self, user_id, monster, sign_attack, hp, max_hp, msg):
        # Define effect parameters for each signature attack
        effects = {
            "Regenerating Smash": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Regenerating Smash and regenerates {int(monster['max_hp'] * 0.15)} HP!",
                None,
                lambda: monster.update({"hp": min(monster["max_hp"], monster["hp"] + int(monster["max_hp"] * 0.15))})
            ),
            "Labyrinth Charge": lambda: (
                f"\n**Signature Attack!** The {monster['name']} charges and lowers your defense!",
                int(monster["atk"] * 0.7),
                lambda: self.active_battles.setdefault(f'{user_id}_state', {}).setdefault("debuffs", {}).update({"defense_down": 2})
            ),
            "Commanding Strike": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Commanding Strike for {int(monster['atk'] * 0.5)} bonus damage!",
                int(monster["atk"] * 0.5),
                None
            ),
            "Arcane Blast": lambda: (
                f"\n**Signature Attack!** The {monster['name']} unleashes Arcane Blast for {int(monster['atk'] * 0.7 + 10)} magic damage!",
                int(monster["atk"] * 0.7 + 10),
                None
            ),
            "Frost Nova": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Frost Nova and chills you, lowering your defense!",
                None,
                lambda: None  # You can apply a debuff here if needed
            ),
            "Flame Burst": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Flame Burst and burns you for 3 turns!",
                None,
                lambda: self.active_battles.setdefault(f"{user_id}_state", {}).setdefault("debuffs", {}).update({"burn": 3})
            ),
            "Surprise Chomp": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Surprise Chomp for {int(monster['atk'] * 0.8)} surprise damage!",
                int(monster["atk"] * 0.8),
                None
            ),
            "Venom Breath": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Venom Breath and poisons you for 3 turns!",
                None,
                lambda: self.active_battles.setdefault(f"{user_id}_state", {}).setdefault("debuffs", {}).update({"poison": 3})
            ),
            "Earthquake": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Earthquake for {int(monster['atk'] * 0.6)} earth-shaking damage!",
                int(monster["atk"] * 0.6),
                 lambda: self.active_battles.setdefault(f'{user_id}_state', {}).setdefault("debuffs", {}).update({"defense_down": 2})
            ),
            "Death Ray": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Death Ray for {int(monster['atk'] * 1.2)} necrotic damage!",
                int(monster["atk"] * 1.2),
                None
            ),
            "Multi-Strike": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Multi-Strike and hits you {hits} times for {total} total damage!",
                None,
                None
            ),
            "Hellfire": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Hellfire for {int(monster['atk'] * 0.7)} fire damage!",
                int(monster["atk"] * 0.7),
                None
            ),
            "Aerial Assault": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Aerial Assault and increases its evasion!",
                None,
                lambda: monster.update({"evasion_chance": monster.get("evasion_chance", 0) + 0.1})
            ),
            "Blood Drain": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Blood Drain, draining {int(monster['atk'] * 0.5)} HP from you!",
                int(monster["atk"] * 0.5),
                lambda: monster.update({"hp": min(monster["max_hp"], monster["hp"] + int(monster["atk"] * 0.5))})
            ),
            "Inferno Breath": lambda: (
                f"\n**Signature Attack!** The {monster['name']} breathes inferno for {int(monster['atk'] * 1.0)} damage!",
                int(monster["atk"] * 1.0),
                None
            ),
            "Titanic Slam": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Titanic Slam for {int(monster['atk'] * 0.9)} crushing damage!",
                int(monster["atk"] * 0.9),
                None
            ),
            "Rebirth Flame": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Rebirth Flame and revives itself for {int(monster['max_hp'] * 0.5)} HP!",
                None,
                lambda: monster.update({"hp": min(monster["max_hp"], monster["hp"] + int(monster["max_hp"] * 0.5))}) if monster["hp"] <= monster["max_hp"] // 2 else None
            ),
            "Shadow Slash": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Shadow Slash for {int(monster['atk'] * 0.8)} shadow damage!",
                int(monster["atk"] * 0.8),
                None
            ),
            "Cataclysm": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Cataclysm for {int(monster['atk'] * 1.5)} catastrophic damage!",
                int(monster["atk"] * 1.5),
                None
            ),
            "Tsunami": lambda: (
                f"\n**Signature Attack!** The {monster['name']} unleashes Tsunami, dealing {int(monster['atk'] * 1.2)} water damage to all party members!",
                int(monster["atk"] * 1.2),
                None
            ),
            "Judgment Ray": lambda: (
                f"\n**Signature Attack!** The {monster['name']} fires Judgment Ray, dealing {int(monster['atk'] * 1.3)} holy damage and lowering defense!",
                int(monster["atk"] * 1.3),
                lambda: self.active_battles.setdefault(f'{user_id}_state', {}).setdefault("debuffs", {}).update({"defense_down": 2})
            ),
            "Volcanic Eruption": lambda: (
                f"\n**Signature Attack!** The {monster['name']} causes a Volcanic Eruption, burning you for 3 turns!",
                int(monster["atk"] * 1.1),
                lambda: self.active_battles.setdefault(f'{user_id}_state', {}).setdefault("debuffs", {}).update({"burn": 3})
            ),
            "Thunderstorm": lambda: (
                f"\n**Signature Attack!** The {monster['name']} summons a Thunderstorm, stunning you for 1 turn!",
                int(monster["atk"] * 1.0),
                lambda: self.active_battles.setdefault(f'{user_id}_state', {}).setdefault("debuffs", {}).update({"stun": 1})
            ),
            "Armor Break": lambda: (
                f"\n**Signature Attack!** The {monster['name']} uses Armor Break, lowering your defense!",
                int(monster["atk"] * 0.5),
                lambda: self.active_battles.setdefault(f'{user_id}_state', {}).setdefault("debuffs", {}).update({"defense_down": 2})
            ),
        }

        # Set chance based on rarity
        rarity = monster.get("rarity", "common")
        sign_chance = {
            "rare": 0.25,
            "epic": 0.33,
            "legendary": 0.5,
            "raid": 0.10  # much lower chance for raid bosses
        }.get(rarity, 0)

        # Multi-Strike needs special handling for hits/total
        if sign_attack == "Multi-Strike":
            hits = random.randint(2, 4)
            total = 0
            for _ in range(hits):
                hit_dmg = max(1, int(monster["atk"] * 0.5))
                hp -= hit_dmg
                total += hit_dmg
            msg += f"\n**Signature Attack!** The {monster['name']} uses Multi-Strike and hits you {hits} times for {total} total damage!"
        elif sign_attack in effects and random.random() < sign_chance:
            effect_msg, dmg, extra = effects[sign_attack]()
            msg += effect_msg
            if dmg:
                hp -= dmg
            if extra:
                extra()
        return msg, hp

    def apply_weapon_special_effects(self, user_id, weapon, monster, base_dmg, hp, max_hp, crit, bonus_spell_dmg):
        effect_msgs = []
        weapon_item = WEAPON_ITEMS.get(weapon, {"damage": 0, "rarity": "common"})
        special_effect = weapon_item.get("effect")
        rarity = weapon_item.get("rarity", "common")
        # Use a single effect_amount for scaling
        effect_amount = weapon_item.get("effect_amount", 1)

        # Rarity scaling factors
        rarity_scale = {
            "common": 1.0,
            "uncommon": 1.2,
            "rare": 1.5,
            "epic": 2.0,
            "legendary": 3.0,
            "raid": 4.0
        }
        scale = rarity_scale.get(rarity, 1.0)
        scaled_amount = effect_amount * scale

        if not special_effect:
            return base_dmg, hp, effect_msgs

        # Effects that may modify base_dmg, hp, or monster state
        if special_effect == "bonus_vs_dragon" and "dragon" in monster["name"].lower():
            bonus = int(scaled_amount)
            base_dmg += bonus
            effect_msgs.append(f"Bonus damage vs Dragon! (+{bonus})")
        elif special_effect == "stun" and random.random() < 0.25 * scale:
            monster["stunned"] = True
            effect_msgs.append("You stunned the monster!")
        elif special_effect == "heal_on_crit" and crit:
            heal = int(max_hp * 0.2 * scale)
            hp = min(max_hp, hp + heal)
            self.update_rpg_stats(user_id, hp=hp)
            effect_msgs.append(f"You healed {heal} HP on crit!")
        elif special_effect == "burn" and random.random() < 0.3 * scale:
            monster.setdefault("debuffs", {})["burn"] = int(3 * scale)
            effect_msgs.append("The monster is burning!")
        elif special_effect == "lifesteal":
            heal = int(base_dmg * 0.5 * scale)
            hp = min(max_hp, hp + heal)
            self.update_rpg_stats(user_id, hp=hp)
            effect_msgs.append(f"You lifesteal {heal} HP!")
        elif special_effect == "ignore_defense":
            bonus = int(monster.get("defense", 0) * scale)
            base_dmg += bonus
            effect_msgs.append("You ignore the monster's defense!")
        elif special_effect == "multi_hit":
            extra_hits = random.randint(1, int(2 * scale))
            extra_dmg = extra_hits * int(effect_amount)
            base_dmg += extra_dmg
            effect_msgs.append(f"Multi-hit! You strike {1 + extra_hits} times for {extra_dmg} bonus damage!")
        elif special_effect == "curse" and random.random() < 0.2 * scale:
            monster.setdefault("debuffs", {})["curse"] = int(2 * scale)
            effect_msgs.append("The monster is cursed and will take extra damage!")
        elif special_effect == "bleed" and random.random() < 0.3 * scale:
            monster.setdefault("debuffs", {})["bleed"] = int(3 * scale)
            effect_msgs.append("The monster is bleeding!")
        elif special_effect == "reap" and monster["hp"] < monster["max_hp"] * 0.25:
            bonus = int(monster["max_hp"] * 0.2 * scale)
            base_dmg += bonus
            effect_msgs.append("Reap! Extra damage to weakened foes!")
        elif special_effect == "smite" and "undead" in monster["name"].lower():
            bonus = int(scaled_amount)
            base_dmg += bonus
            effect_msgs.append("Smite! Bonus damage to undead!")
        elif special_effect == "never_miss":
            monster["evasion_chance"] = 0
            effect_msgs.append("Your attack cannot miss!")
        elif special_effect == "leadership":
            if user_id in self.active_parties:
                party_id = self.active_parties[user_id]
                for pid in self.parties[party_id]["members"]:
                    if pid != user_id:
                        state = self.active_battles.setdefault(f"{pid}_state", {})
                        state.setdefault("buffs", {})["leadership"] = int(2 * scale)
                effect_msgs.append("Your leadership inspires your party!")
        elif special_effect == "instant_kill" and random.random() < 0.05 * scale:
            monster["hp"] = 0
            effect_msgs.append("**INSTANT KILL!**")
        elif special_effect == "memory_wipe" and random.random() < 0.15 * scale:
            monster.setdefault("debuffs", {})["memory_wipe"] = int(2 * scale)
            effect_msgs.append("The monster is confused and loses its next turn!")
        elif special_effect == "blind" and random.random() < 0.2 * scale:
            monster.setdefault("debuffs", {})["blind"] = int(2 * scale)
            effect_msgs.append("The monster is blinded and its accuracy drops!")
        elif special_effect == "infinite_power":
            bonus = int(scaled_amount)
            base_dmg += bonus
            effect_msgs.append("Infinite Power! Massive bonus damage!")
        elif special_effect == "bonus_spell":
            bonus = int(bonus_spell_dmg * 1.5 * scale)
            base_dmg += bonus
            effect_msgs.append("Your spell power surges with this weapon!")
        elif special_effect == "pierce":
            bonus = int(scaled_amount)
            base_dmg += bonus
            effect_msgs.append("Piercing attack! Ignores some defense.")
        elif special_effect == "revive_on_death" and hp <= 0:
            hp = int(max_hp * 0.5 * scale)
            self.update_rpg_stats(user_id, hp=hp)
            effect_msgs.append("You are revived by the Phoenix Bow!")
        elif special_effect == "sleep" and random.random() < 0.2 * scale:
            monster.setdefault("debuffs", {})["sleep"] = int(2 * scale)
            effect_msgs.append("The monster is put to sleep!")
        elif special_effect == "double_damage_night":
            from datetime import datetime
            if 0 <= datetime.utcnow().hour < 6:
                base_dmg *= 2 * scale
                effect_msgs.append("It's night! Double damage!")

        return base_dmg, hp, effect_msgs

    @commands.hybrid_command(name="rpgheal", description="Use a consumable to heal yourself.")
    @rpg_started()
    async def rpgheal(self, ctx, *, item_name: str = None):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        (
            level, exp, hp, max_hp, atk, defense, char_class, weapon, quest, quest_progress, skill_points,
            strength, dexterity, intelligence, exp_to_next, hp_regen, mana, mana_regen, max_mana, crit_chance,
            crit_damage, evasion_chance, bonus_spell_dmg
        ) = stats
        coins, bank, inv = get_player(user_id)
        items = inv.split(",") if inv else []

        # List available consumables if no item_name is given
        consumables = [
            "Elixir", "Greater Potion", "Mana Potion", "Golden Apple", "Bandage", "Cheese", "Bat Wing", "Rotten Flesh", "Potion"
        ]
        owned = [item for item in items if item in consumables]
        if not item_name:
            if not owned:
                await ctx.send("You don't have any usable healing items in your inventory!")
                return
            lines = [f"{owned.count(item)}x {item}" for item in sorted(set(owned), key=owned.index)]
            await ctx.send(
                "**Usable consumables in your inventory:**\n"
                + "\n".join(lines)
                + "\n\nUse `/rpgheal <item name>` to consume one."
            )
            return

        item_name = item_name.strip().title()
        if item_name not in items:
            await ctx.send(f"You don't have a **{item_name}** in your inventory!")
            return

        # --- Consumable logic ---
        if item_name == "Elixir":
            items.remove("Elixir")
            heal = random.randint(18, 28) + int(strength) + int(hp_regen)
            hp = min(max_hp, hp + heal)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            await ctx.send(f"You used an **Elixir** and healed {heal:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})")
            return
        if item_name == "Greater Potion":
            items.remove("Greater Potion")
            heal = random.randint(12, 20) + int(strength) + int(hp_regen)
            hp = min(max_hp, hp + heal)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            await ctx.send(f"You used a **Greater Potion** and healed {heal:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})")
            return
        if item_name == "Mana Potion":
            items.remove("Mana Potion")
            mana_gain = random.randint(10, 20) + int(intelligence)
            mana = min(max_mana, mana + mana_gain)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, mana=mana)
            await ctx.send(f"You used a **Mana Potion** and restored {mana_gain:.1f} Mana! (Your Mana: {mana:.1f}/{max_mana:.1f})")
            return
        if item_name == "Golden Apple":
            items.remove("Golden Apple")
            heal = int(max_hp * 0.5)
            hp = min(max_hp, hp + heal)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            await ctx.send(f"You ate a **Golden Apple** and healed {heal:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})")
            return
        if item_name == "Bandage":
            items.remove("Bandage")
            heal = random.randint(6, 12) + int(strength)
            hp = min(max_hp, hp + heal)
            # Remove 'bleed' debuff if present
            player_state = self.active_battles.setdefault(f"{user_id}_state", {})
            debuffs = player_state.setdefault("debuffs", {})
            if "bleed" in debuffs:
                del debuffs["bleed"]
                bleed_msg = " and stopped your bleeding"
            else:
                bleed_msg = ""
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            await ctx.send(f"You used a **Bandage** and healed {heal:.1f} HP{bleed_msg}! (Your HP: {hp:.1f}/{max_hp:.1f})")
            return
        if item_name == "Cheese":
            items.remove("Cheese")
            heal = random.randint(7, 13) + int(strength // 2)
            hp = min(max_hp, hp + heal)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            await ctx.send(f"You ate some **Cheese** and healed {heal:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})")
            return
        if item_name == "Bat Wing":
            items.remove("Bat Wing")
            heal = random.randint(3, 7)
            mana_gain = random.randint(2, 5)
            hp = min(max_hp, hp + heal)
            mana = min(max_mana, mana + mana_gain)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp, mana=mana)
            await ctx.send(f"You used a **Bat Wing** and healed {heal:.1f} HP and restored {mana_gain} Mana! (HP: {hp:.1f}/{max_hp:.1f}, Mana: {mana:.1f}/{max_mana:.1f})")
            return
        if item_name == "Rotten Flesh":
            items.remove("Rotten Flesh")
            heal = random.randint(4, 8)
            hp = min(max_hp, hp + heal)
            poisoned = random.random() < 0.4
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            msg = f"You ate **Rotten Flesh** and healed {heal:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})"
            if poisoned:
                player_state = self.active_battles.setdefault(f"{user_id}_state", {})
                debuffs = player_state.setdefault("debuffs", {})
                debuffs["poison"] = 2
                msg += " But you got **poisoned**!"
            await ctx.send(msg)
            return
        if item_name == "Potion":
            items.remove("Potion")
            heal = random.randint(5, 10) + int(strength) + int(hp_regen)
            hp = min(max_hp, hp + heal)
            update_player_inventory(user_id, ",".join(items))
            update_rpg_stats(user_id, hp=hp)
            await ctx.send(f"You used a Potion and healed {heal:.1f} HP! (Your HP: {hp:.1f}/{max_hp:.1f})")
            return

        await ctx.send(f"**{item_name}** is not a usable healing item or not implemented yet.")
    
    @commands.hybrid_command(name="rpgquit", description="End your RPG adventure (keeps your inventory).")
    @rpg_started()
    async def rpgquit(self, ctx):
        user_id = ctx.author.id
        # Remove weapons from inventory and unequip
        remove_all_rpg_items_from_inventory(user_id)
        # Remove from rpg_stats table
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rpg_stats WHERE user_id = ?", (str(user_id),))
        conn.commit()
        conn.close()
        # Remove from active battles and parties
        if user_id in self.active_battles:
            del self.active_battles[user_id]
        if f"{user_id}_state" in self.active_battles:
            del self.active_battles[f"{user_id}_state"]
        if user_id in self.active_parties:
            party_id = self.active_parties[user_id]
            party = self.parties.get(party_id)
            if party:
                party["members"].discard(user_id)
                party["invited"].discard(user_id)
                if not party["members"]:
                    del self.parties[party_id]
            del self.active_parties[user_id]
        self.active_battles.pop(f"{user_id}_regen_remainder", None)
        self.active_battles.pop(f"{user_id}_state", None)
        await ctx.send("Your adventure has ended and your RPG stats have been removed. All your weapons have been lost. Use `/rpgstart` to begin a new one.")
    
    @commands.hybrid_command(name="rpgspells", description="List your available spells and manage your equipped spells (max 5).")
    @rpg_started()
    async def rpgspells(self, ctx, action: str = None, *, spell_name: str = None):
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        char_class = stats[6]
        if not char_class or char_class not in SPELLS:
            await ctx.send("You must choose a class to use spells. Use `/rpgclass`.")
            return

        # --- Load equipped spells from DB (add a new column if needed) ---
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT equipped_spells FROM rpg_stats WHERE user_id = ?", (str(user_id),))
        row = cursor.fetchone()
        if row and row[0]:
            equipped_spells = row[0].split(",")
        else:
            equipped_spells = []

        available_spells = SPELLS[char_class]

        # --- Equip/unequip logic ---
        if action:
            action = action.lower()
            if action == "equip" and spell_name:
                spell = next((s for s in available_spells if s["name"].lower() == spell_name.lower()), None)
                if not spell:
                    await ctx.send("Spell not found. Use `/rpgspells` to see your available spells.")
                    return
                if spell["name"] in equipped_spells:
                    await ctx.send(f"**{spell['name']}** is already equipped.")
                    return
                if len(equipped_spells) >= 5:
                    await ctx.send("You can only equip up to 5 spells. Use `/rpgspells unequip <spell name>` to remove one.")
                    return
                equipped_spells.append(spell["name"])
                cursor.execute("UPDATE rpg_stats SET equipped_spells = ? WHERE user_id = ?", (",".join(equipped_spells), str(user_id)))
                conn.commit()
                await ctx.send(f"Equipped **{spell['name']}**.")
                conn.close()
                return
            elif action == "unequip" and spell_name:
                spell = next((s for s in available_spells if s["name"].lower() == spell_name.lower()), None)
                if not spell or spell["name"] not in equipped_spells:
                    await ctx.send("That spell is not equipped.")
                    return
                equipped_spells.remove(spell["name"])
                cursor.execute("UPDATE rpg_stats SET equipped_spells = ? WHERE user_id = ?", (",".join(equipped_spells), str(user_id)))
                conn.commit()
                await ctx.send(f"Unequipped **{spell['name']}**.")
                conn.close()
                return
            else:
                await ctx.send("Usage: `/rpgspells equip <spell name>` or `/rpgspells unequip <spell name>`")
                conn.close()
                return

        # --- Show available and equipped spells ---
        embed = discord.Embed(
            title=f"{char_class} Spells",
            color=discord.Color.purple()
        )
        for spell in available_spells:
            equipped = "✅" if spell["name"] in equipped_spells else ""
            embed.add_field(
                name=f"{spell['name']} (Mana: {spell['mana']}) {equipped}",
                value=spell['desc'],
                inline=False
            )
        if equipped_spells:
            embed.add_field(
                name="Equipped Spells",
                value=", ".join(equipped_spells),
                inline=False
            )
        embed.set_footer(text="Use `/rpgspells equip <spell name>` or `/rpgspells unequip <spell name>`. Max 5 equipped.")
        await ctx.send(embed=embed)
        conn.close()

    def process_player_buffs(self, user_id, player_state):
        """Apply and decrement player buffs/debuffs at the start of their turn, including bonus_spell_dmg scaling."""
        buffs = player_state.setdefault("buffs", {})
        debuffs = player_state.setdefault("debuffs", {})
        atk_mod = 0
        def_mod = 0
        evasion_mod = 0
        spell_dmg_mod = 0

        stats = get_rpg_stats(user_id)
        bonus_spell_dmg = stats[22] if stats and len(stats) > 22 else 0

        # --- Buffs ---
        if buffs.get("battle_cry", 0) > 0:
            atk_mod += 3 + int(bonus_spell_dmg * 0.5)
            def_mod += 2 + int(bonus_spell_dmg * 0.3)
            buffs["battle_cry"] -= 1
        if buffs.get("iron_wall", 0) > 0:
            def_mod += 8 + int(bonus_spell_dmg * 0.7)
            buffs["iron_wall"] -= 1
        if buffs.get("taunt", 0) > 0:
            def_mod += 3 + int(bonus_spell_dmg * 0.2)
            buffs["taunt"] -= 1
        if buffs.get("vanish", 0) > 0:
            evasion_mod += 1.0
            buffs["vanish"] -= 1
        if buffs.get("smoke_bomb", 0) > 0:
            evasion_mod += 0.25 + min(0.15, bonus_spell_dmg * 0.01)
            buffs["smoke_bomb"] -= 1
        if buffs.get("adrenaline_rush", 0) > 0:
            atk_mod += 2 + int(bonus_spell_dmg * 0.2)
            buffs["adrenaline_rush"] -= 1
        if buffs.get("arcane_surge", 0) > 0:
            spell_dmg_mod += 5 + int(bonus_spell_dmg * 0.5)
            buffs["arcane_surge"] -= 1
        if buffs.get("ice_barrier", 0) > 0:
            def_mod += 5 + int(bonus_spell_dmg * 0.5)
            buffs["ice_barrier"] -= 1
        if buffs.get("mana_shield", 0) > 0:
            def_mod += 7 + int(bonus_spell_dmg * 0.7)
            buffs["mana_shield"] -= 1
        if buffs.get("haste", 0) > 0:
            evasion_mod += 0.15 + min(0.1, bonus_spell_dmg * 0.01)
            spell_dmg_mod += 2 + int(bonus_spell_dmg * 0.2)
            buffs["haste"] -= 1
        # New: Leadership (King's Claymore)
        if buffs.get("leadership", 0) > 0:
            atk_mod += 4
            buffs["leadership"] -= 1

        # --- Debuffs ---
        if debuffs.get("burn", 0) > 0:
            atk_mod -= 2 + int(bonus_spell_dmg * 0.2)
            debuffs["burn"] -= 1
        if debuffs.get("poison", 0) > 0:
            def_mod -= 2 + int(bonus_spell_dmg * 0.2)
            debuffs["poison"] -= 1
        if debuffs.get("curse", 0) > 0:
            atk_mod -= 2 + int(bonus_spell_dmg * 0.2)
            def_mod -= 2 + int(bonus_spell_dmg * 0.2)
            evasion_mod -= 0.05 + min(0.05, bonus_spell_dmg * 0.002)
            debuffs["curse"] -= 1
        if debuffs.get("frost_nova", 0) > 0:
            def_mod += 2 + int(bonus_spell_dmg * 0.2)
            debuffs["frost_nova"] -= 1
        if debuffs.get("mark_for_death", 0) > 0:
            def_mod -= 3 + int(bonus_spell_dmg * 0.3)
            debuffs["mark_for_death"] -= 1
        # New: Bleed (Shadow Blade, Bloodletter)
        if debuffs.get("bleed", 0) > 0:
            bleed_dmg = int(stats[3] * 0.07)
            stats = list(stats)
            stats[2] = max(1, stats[2] - bleed_dmg)
            update_rpg_stats(user_id, hp=stats[2])
            debuffs["bleed"] -= 1
        # New: Sleep (Nightshade Dagger)
        if debuffs.get("sleep", 0) > 0:
            atk_mod -= 1000  # Effectively skip turn
            debuffs["sleep"] -= 1
        # New: Blind (Eclipse Whip)
        if debuffs.get("blind", 0) > 0:
            evasion_mod += 0.2
            debuffs["blind"] -= 1
        # New: Memory Wipe (Oblivion Blade)
        if debuffs.get("memory_wipe", 0) > 0:
            atk_mod -= 1000  # Skip turn
            debuffs["memory_wipe"] -= 1
        # New: Defense Down (Judgment Ray)
        if debuffs.get("defense_down", 0) > 0:
            def_mod -= 5  # Reduce defense by 5 (adjust as needed)
            debuffs["defense_down"] -= 1
        # New: Stun (Thunderstorm)
        if debuffs.get("stun", 0) > 0:
            atk_mod -= 1000  # Effectively skip turn
            debuffs["stun"] -= 1

        # Clean up expired buffs/debuffs
        for k in list(buffs):
            if buffs[k] <= 0:
                del buffs[k]
        for k in list(debuffs):
            if debuffs[k] <= 0:
                del debuffs[k]

        return atk_mod, def_mod, evasion_mod, spell_dmg_mod

    def process_monster_debuffs(self, monster):
        debuffs = monster.setdefault("debuffs", {})
        msg = ""
        dead = False
        # Poison
        if debuffs.get("poison", 0) > 0:
            poison_dmg = int(0.05 * monster["max_hp"])
            monster["hp"] -= poison_dmg
            debuffs["poison"] -= 1
            msg += f"\nThe monster takes {poison_dmg} poison damage!"
        # Burn
        if debuffs.get("burn", 0) > 0:
            burn_dmg = int(0.05 * monster["max_hp"])
            monster["hp"] -= burn_dmg
            debuffs["burn"] -= 1
            msg += f"\nThe monster takes {burn_dmg} burn damage!"
        # New: Bleed
        if debuffs.get("bleed", 0) > 0:
            bleed_dmg = int(0.07 * monster["max_hp"])
            monster["hp"] -= bleed_dmg
            debuffs["bleed"] -= 1
            msg += f"\nThe monster bleeds for {bleed_dmg} damage!"
        # New: Curse (already handled in player attack, but decrement here)
        if debuffs.get("curse", 0) > 0:
            debuffs["curse"] -= 1
        # New: Sleep (skip monster turn)
        if debuffs.get("sleep", 0) > 0:
            debuffs["sleep"] -= 1
            msg += "\nThe monster is asleep and skips its turn!"
        # New: Blind (reduce accuracy)
        if debuffs.get("blind", 0) > 0:
            debuffs["blind"] -= 1
            msg += "\nThe monster is blinded and its accuracy is reduced!"
        # New: Memory Wipe (skip monster turn)
        if debuffs.get("memory_wipe", 0) > 0:
            debuffs["memory_wipe"] -= 1
            msg += "\nThe monster is confused and loses its turn!"

        # Clean up expired debuffs
        for k in list(debuffs):
            if debuffs[k] <= 0:
                del debuffs[k]
        if monster["hp"] <= 0:
            dead = True
        return msg, dead

    def load_monsters(self, guild_id=None):
        # Ignore guild_id, always load from JSON file
        return [dict(m) for m in self.default_monsters]

    @commands.hybrid_group(name="rpgweapon", description="Manage your weapons.")
    @rpg_started()
    async def rpgweapon(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Weapon commands: equip, unequip, status, list, info")

    @rpgweapon.command(name="equip")
    @rpg_started()
    async def weapon_equip(self, ctx, *, weapon_name: str):
        """Equip a weapon from your inventory. Equipping a new weapon will unequip your old one."""
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        coins, bank, inv = get_player(user_id)
        items = inv.split(",") if inv else []
        weapon_name = weapon_name.strip().lower()
        owned_weapons = [w.lower() for w in items if w in WEAPON_ITEMS]
        if weapon_name not in [w.lower() for w in WEAPON_ITEMS]:
            await ctx.send("That weapon does not exist.")
            return
        if weapon_name not in owned_weapons:
            await ctx.send("You do not have that weapon in your inventory.")
            return
        # Find the actual weapon name for update
        actual_weapon = next(w for w in WEAPON_ITEMS if w.lower() == weapon_name)
        # Remove the previously equipped weapon from inventory (if any)
        current_weapon = stats[7]
        if current_weapon and current_weapon in items:
            items.remove(current_weapon)
        # Remove the new weapon from inventory (since it will be equipped)
        items.remove(actual_weapon)
        # Add the previously equipped weapon back to inventory (if any)
        if current_weapon:
            items.append(current_weapon)
        # Add the new weapon to equipped slot
        update_player_inventory(user_id, ",".join(items))
        update_rpg_stats(user_id, weapon=actual_weapon)
        await ctx.send(f"You have equipped **{actual_weapon}**!")

    @rpgweapon.command(name="unequip")
    @rpg_started()
    async def weapon_unequip(self, ctx):
        """Unequip your current weapon and fight bare-handed."""
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        weapon = stats[7]
        if not weapon:
            await ctx.send("You already have no weapon equipped.")
            return
        update_rpg_stats(user_id, weapon="")
        await ctx.send("You have unequipped your weapon and will now fight bare-handed.")

    @rpgweapon.command(name="status")
    @rpg_started()
    async def weapon_status(self, ctx):
        """Show your currently equipped weapon and its stats."""
        user_id = ctx.author.id
        stats = get_rpg_stats(user_id)
        if not stats:
            await ctx.send("You haven't started your adventure yet. Use `/rpgstart`.")
            return
        weapon = stats[7]
        if not weapon:
            await ctx.send("You have no weapon equipped.")
            return
        weapon_stats = WEAPON_ITEMS.get(weapon)
        if not weapon_stats:
            await ctx.send(f"Equipped weapon: **{weapon}** (not found in weapon database).")
            return
        desc = f"**{weapon}**\nDamage: {weapon_stats['damage']}\nRarity: {weapon_stats.get('rarity', 'common').capitalize()}"
        if weapon_stats.get("effect"):
            desc += f"\nSpecial Effect: {weapon_stats['effect']}"
        await ctx.send(desc)

    @rpgweapon.command(name="list")
    @rpg_started()
    async def weapon_list(self, ctx):
        """List all weapons you own in your inventory."""
        user_id = ctx.author.id
        coins, bank, inv = get_player(user_id)
        items = inv.split(",") if inv else []
        weapon_counts = {}
        for item in items:
            if item in WEAPON_ITEMS:
                weapon_counts[item] = weapon_counts.get(item, 0) + 1
        if not weapon_counts:
            await ctx.send("You have no weapons in your inventory.")
            return
        lines = [
            f"{amount}x {name} (DMG: {WEAPON_ITEMS[name]['damage']}, {WEAPON_ITEMS[name].get('rarity', 'common').capitalize()})"
            for name, amount in weapon_counts.items()
        ]
        await ctx.send("**Your Weapons:**\n" + "\n".join(lines))

    @rpgweapon.command(name="info")
    @rpg_started()
    async def weapon_info(self, ctx, *, weapon_name: str):
        """Show info about any weapon in the game."""
        weapon_name = weapon_name.strip().lower()
        found = next((w for w in WEAPON_ITEMS if w.lower() == weapon_name), None)
        if not found:
            await ctx.send("That weapon does not exist.")
            return
        weapon_stats = WEAPON_ITEMS[found]
        desc = f"**{found}**\nDamage: {weapon_stats['damage']}\nRarity: {weapon_stats.get('rarity', 'common').capitalize()}"
        if weapon_stats.get("effect"):
            desc += f"\nSpecial Effect: {weapon_stats['effect']}"
        await ctx.send(desc)

    @commands.hybrid_command(name="rpgretreat", description="Retreat from your current encounter (no rewards, no penalty).")
    @rpg_started()
    async def rpgretreat(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.active_battles:
            await ctx.send("You are not in a battle.")
            return
        monster = self.active_battles[user_id]
        monster_name = monster.get("name", "the monster")
        # Remove from active battles and reset regen remainder
        if user_id in self.active_parties:
            party_id = self.active_parties[user_id]
            if party_id in self.active_battles:
                del self.active_battles[party_id]
            self.active_battles.pop(f"{party_id}_regen_remainder", None)
            self.active_battles.pop(f"{party_id}_state", None)
            # Optionally notify all party members
        else:
            if user_id in self.active_battles:
                del self.active_battles[user_id]
            self.active_battles.pop(f"{user_id}_regen_remainder", None)
            self.active_battles.pop(f"{user_id}_state", None)
        await ctx.send(f"You have successfully retreated from your encounter with **{monster_name}**. Live to fight another day!")

# Helper for confirmation
class ConfirmView(discord.ui.View):
    def __init__(self, ctx, timeout=20):
        super().__init__(timeout=timeout)
        self.value = None
        self.ctx = ctx

    @discord.ui.button(label="Fight!", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your encounter!", ephemeral=True)
            return
        self.value = True
        self.stop()
        await interaction.response.edit_message(content="You brace yourself for battle!", view=None)

    @discord.ui.button(label="Back Out", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your encounter!", ephemeral=True)
            return
        self.value = False
        self.stop()
        await interaction.response.edit_message(content="You backed out from the legendary encounter.", view=None)

async def setup(bot):
    await bot.add_cog(RPGCog(bot))