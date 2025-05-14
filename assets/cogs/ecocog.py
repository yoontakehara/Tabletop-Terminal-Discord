import discord
from discord.ext import commands
import sqlite3
import os
import random
import asyncio
import datetime
from discord import ui

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "data.db")

BANK_MAX = 5000  # Max coins a user can store in the bank
STEAL_COOLDOWN = 6 * 60 * 60  # 6 hours in seconds
STEAL_SUCCESS_CHANCE = 0.6    # 60% chance to succeed
STEAL_BAIL_COST = 200         # Coins lost if caught
WORK_COOLDOWN = 60  # seconds


def get_player(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT coins, bank, inventory, daily_streak, last_daily FROM eco_players WHERE user_id = ?", (str(user_id),))
    result = cursor.fetchone()
    conn.close()
    return result

def update_player(user_id, coins=None, bank=None, inventory=None, daily_streak=None, last_daily=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if coins is not None:
        cursor.execute("UPDATE eco_players SET coins = ? WHERE user_id = ?", (coins, str(user_id)))
    if bank is not None:
        cursor.execute("UPDATE eco_players SET bank = ? WHERE user_id = ?", (bank, str(user_id)))
    if inventory is not None:
        cursor.execute("UPDATE eco_players SET inventory = ? WHERE user_id = ?", (inventory, str(user_id)))
    if daily_streak is not None:
        cursor.execute("UPDATE eco_players SET daily_streak = ? WHERE user_id = ?", (daily_streak, str(user_id)))
    if last_daily is not None:
        cursor.execute("UPDATE eco_players SET last_daily = ? WHERE user_id = ?", (last_daily, str(user_id)))
    conn.commit()
    conn.close()

def add_player_if_not_exists(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO eco_players (user_id, coins, bank, inventory) VALUES (?, 0, 0, '')", (str(user_id),))
    conn.commit()
    conn.close()

def get_shop_items(guild_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, command_name, price, description, rarity, item_type FROM eco_shop WHERE guild_id = ?", (str(guild_id),))
    items = cursor.fetchall()
    conn.close()
    return items

def get_shop_item(guild_id, item_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, price, description, effect, rarity, item_type FROM eco_shop WHERE item_name = ?", (item_name,))
    item = cursor.fetchone()
    conn.close()
    return item

def get_shop_item_by_command(guild_id, command_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, command_name, price, description, effect, rarity, item_type FROM eco_shop WHERE guild_id = ? AND command_name = ?", (str(guild_id), command_name))
    item = cursor.fetchone()
    conn.close()
    return item

def get_shop_item_any(item_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, price, description, effect, rarity, item_type FROM eco_shop WHERE item_name = ?", (item_name,))
    item = cursor.fetchone()
    conn.close()
    return item

def add_shop_item(guild_id, item_name, command_name, price, description, effect=None, rarity=None, item_type=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO eco_shop (guild_id, item_name, command_name, price, description, effect, rarity, item_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(guild_id), item_name, command_name, price, description, effect, rarity, item_type)
    )
    conn.commit()
    conn.close()

def remove_shop_item(guild_id, command_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eco_shop WHERE guild_id = ? AND command_name = ?", (str(guild_id), command_name))
    conn.commit()
    conn.close()

def get_all_collectibles(guild_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, rarity FROM eco_shop WHERE guild_id = ? AND effect LIKE 'collectible:%'", (str(guild_id),))
    items = cursor.fetchall()
    conn.close()
    return items

def get_rarity_odds():
    # Odds for lootbox: common 60%, uncommon 20%, rare 10%, epic 7%, legendary 3%
    return {
        "common": 0.6,
        "uncommon": 0.2,
        "rare": 0.1,
        "epic": 0.07,
        "legendary": 0.03
    }

def get_luck_expiry(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT luck_expiry FROM eco_players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return datetime.datetime.fromisoformat(row[0])
        except Exception:
            return None
    return None

def set_luck_expiry(user_id, expiry: datetime.datetime):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE eco_players SET luck_expiry = ? WHERE user_id = ?", (expiry.isoformat(), str(user_id)))
    conn.commit()
    conn.close()

def get_cooldown(user_id, command):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT last_used FROM eco_cooldowns WHERE user_id = ? AND command = ?", (str(user_id), command))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return datetime.datetime.fromisoformat(row[0])
        except Exception:
            return None
    return None

def set_cooldown(user_id, command, last_used: datetime.datetime):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO eco_cooldowns (user_id, command, last_used) VALUES (?, ?, ?)",
        (str(user_id), command, last_used.isoformat())
    )
    conn.commit()
    conn.close()

class ShopPageView(ui.View):
    def __init__(self, ctx, items, page=0, items_per_page=6):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.items = items
        self.page = page
        self.items_per_page = items_per_page
        self.max_page = max(0, (len(items) - 1) // items_per_page)

    async def update_message(self, interaction):
        embed = discord.Embed(
            title=f"Shop (Page {self.page + 1}/{self.max_page + 1})",
            description="Use `/shop buy <command_name>` or `/shop sell <command_name>` to buy/sell.",
            color=discord.Color.blurple()
        )
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        for name, cmd, price, desc, rarity, item_type in self.items[start:end]:
            meta = []
            if item_type:
                meta.append(f"Type: {item_type.capitalize()}")
            if rarity:
                meta.append(f"Rarity: {rarity.capitalize()}")
            meta_str = " | ".join(meta)
            embed.add_field(
                name=f"{name} (`{cmd}`) - {price} coins",
                value=f"{desc}\n{meta_str}" if meta_str else desc,
                inline=False
            )
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page == self.max_page
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            self.page -= 1
        await self.update_message(interaction)

    @ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if self.page < self.max_page:
            self.page += 1
        await self.update_message(interaction)

class ShopCategoryView(ui.View):
    def __init__(self, ctx, categories, items_by_cat, page=0, mode="main"):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.categories = categories
        self.items_by_cat = items_by_cat
        self.page = page
        self.mode = mode
        self.max_page = len(categories) - 1

    async def update_message(self, interaction):
        embed = discord.Embed(
            title="Shop" if self.mode == "main" else f"Shop - {self.categories[self.page].capitalize()}",
            color=discord.Color.blurple()
        )
        if self.mode == "main":
            embed.description = "Select a category below to view items. Use `/shop buy <command_name>` or `/shop sell <command_name>` to buy/sell."
            for idx, cat in enumerate(self.categories):
                # Display "Collectibles" for "collectible", otherwise capitalize
                display_name = "Collectibles" if cat == "collectible" else cat.capitalize()
                embed.add_field(name=display_name, value=f"Page {idx+1}", inline=False)
            # Do NOT disable navigation buttons on main page
            self.children[0].disabled = False  # Previous
            self.children[1].disabled = False  # Next
        else:
            cat = self.categories[self.page]
            items = self.items_by_cat[cat]
            for name, cmd, price, desc, rarity, item_type in items:
                meta = []
                if item_type:
                    meta.append(f"Type: {item_type.capitalize()}")
                if rarity:
                    meta.append(f"Rarity: {rarity.capitalize()}")
                meta_str = " | ".join(meta)
                embed.add_field(
                    name=f"{name} (`{cmd}`) - {price} coins",
                    value=f"{desc}\n{meta_str}" if meta_str else desc,
                    inline=False
                )
            self.children[0].disabled = self.page == 0
            self.children[1].disabled = self.page == self.max_page
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            self.page -= 1
        self.mode = "category"
        await self.update_message(interaction)

    @ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if self.page < self.max_page:
            self.page += 1
        self.mode = "category"
        await self.update_message(interaction)

    @ui.button(label="Main", style=discord.ButtonStyle.primary)
    async def main(self, interaction: discord.Interaction, button: ui.Button):
        self.mode = "main"
        await self.update_message(interaction)

class EcoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.work_cooldowns = {}

    @commands.hybrid_command(name="balance", description="Check your coin and bank balance.")
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        add_player_if_not_exists(member.id)
        coins, bank, inv, *_ = get_player(member.id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Balance",
            description=f"💰 Wallet: **{coins}**\n🏦 Bank: **{bank}/{BANK_MAX}**",
            color=discord.Color.gold()
        )
        # Show inventory summary with emojis
        if inv:
            items = inv.split(",")
            item_counts = {}
            for item in items:
                if item:
                    item_counts[item] = item_counts.get(item, 0) + 1
            emoji_map = {
                "Coin Booster": "💸",
                "VIP Role": "🌟",
                "Lucky Charm": "🍀",
                "Miniature Dragon": "🐉",
                "Signed D20": "🎲",
                "Foil MTG Card": "🃏",
                "Tabletop Mug": "☕",
                "Custom Token": "🔖",
                "Lootbox": "🎁",
                "Anti-Theft Token": "🛡️",
                "Plastic Meeple": "🧩",
                "Wooden Cube": "🟫",
                "Card Sleeve": "🪪",
                "Mini Dice Set": "🎲",
                "Pawn Figure": "♟️",
                "Score Pad": "📒",
                "Plastic Coin": "🪙",
                "Reference Card": "📑",
                "Metal Coin": "🥇",
                "Acrylic Standee": "🧍",
                "Dice Bag": "🛍️",
                "Metallic Token": "🔗",
                "Meeple Keychain": "🔑",
                "Dice Tray": "🧺",
                "Game Organizer": "🗃️",
                "Enamel Pin": "📌",
                "Collector's Dice": "🎲",
                "Signed Card": "✍️",
                "Holographic Token": "✨",
                "Limited Edition Meeple": "🧙",
                "Collector's Coin": "🪙",
                "Crystal Dice": "💠",
                "Art Print": "🖼️",
                "Gold Foil Card": "🏅",
                "Golden Meeple": "🏆",
                "Diamond Dice": "💎",
                "Signed Board Game": "📦",
                "Mythic Trophy": "🏆"
            }
            lines = [f"{emoji_map.get(name, '📦')} {amount}x {name}" for name, amount in item_counts.items()]
            embed.add_field(name="Inventory", value="\n".join(lines), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="daily", description="Claim your daily coins.")
    async def daily(self, ctx):
        import datetime
        add_player_if_not_exists(ctx.author.id)
        coins, bank, inv, daily_streak, last_daily = get_player(ctx.author.id)
        now = datetime.datetime.utcnow().date()
        last = None
        if last_daily:
            try:
                last = datetime.datetime.strptime(last_daily, "%Y-%m-%d").date()
            except Exception:
                last = None
        # Streak logic
        if last == now:
            embed = discord.Embed(
                title="Already Claimed",
                description="You have already claimed your daily reward today.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        if last and (now - last).days == 1:
            daily_streak = (daily_streak or 0) + 1
        else:
            daily_streak = 1
        boost = 1
        if inv:
            items = inv.split(",") if inv else []
            if "Coin Booster" in items:
                boost = 2
        reward = 250 * boost
        coins += reward
        update_player(ctx.author.id, coins=coins, daily_streak=daily_streak, last_daily=now.strftime("%Y-%m-%d"))
        embed = discord.Embed(
            title="Daily Reward",
            description=f"You claimed your daily reward: **{reward} coins!**\nStreak: {daily_streak} days",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        # Give lootbox for 7-day streak
        if daily_streak > 0 and daily_streak % 7 == 0:
            coins, bank, inv, *_ = get_player(ctx.author.id)
            items = inv.split(",") if inv else []
            items.append("Lootbox")
            new_inv = ",".join(items)
            update_player(ctx.author.id, inventory=new_inv)
            loot_embed = discord.Embed(
                title="Weekly Streak Reward!",
                description="You received a **Lootbox** for a 7-day daily streak! Use `/lootbox` to open it.",
                color=discord.Color.gold()
            )
            await ctx.send(embed=loot_embed)

    @commands.hybrid_command(name="work", description="Work for coins (random amount).")
    async def work(self, ctx):
        add_player_if_not_exists(ctx.author.id)
        now = datetime.datetime.utcnow()
        last_used = get_cooldown(ctx.author.id, "work")
        if last_used and (now - last_used).total_seconds() < WORK_COOLDOWN:
            remaining = int(WORK_COOLDOWN - (now - last_used).total_seconds())
            embed = discord.Embed(
                title="Cooldown",
                description=f"You're tired! Try working again in {remaining} seconds.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return

        coins, bank, inv, *_ = get_player(ctx.author.id)
        boost = 1
        if inv:
            items = inv.split(",") if inv else []
            if "Coin Booster" in items:
                boost = 2
        earned = random.randint(50, 150) * boost
        coins += earned
        update_player(ctx.author.id, coins=coins)
        set_cooldown(ctx.author.id, "work", now)  # Save cooldown persistently
        embed = discord.Embed(
            title="Work Complete",
            description=f"You worked and earned **{earned} coins!**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @work.error
    async def work_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="Cooldown",
                description=f"You're tired! Try working again in {int(error.retry_after)} seconds.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="Error",
                description=f"An unexpected error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        return  # <--- Always return to prevent propagation

    @commands.hybrid_command(name="steal", description="🦹 Attempt to steal coins from another user! (6h cooldown, risk of getting caught)")
    async def steal(self, ctx, member: discord.Member):
        if member.id == ctx.author.id:
            await ctx.send("You can't steal from yourself!")
            return
        add_player_if_not_exists(ctx.author.id)
        add_player_if_not_exists(member.id)
        now = datetime.datetime.utcnow()
        last_used = get_cooldown(ctx.author.id, "steal")
        if last_used and (now - last_used).total_seconds() < STEAL_COOLDOWN:
            remaining = int(STEAL_COOLDOWN - (now - last_used).total_seconds())
            embed = discord.Embed(
                title="Cooldown",
                description=f"You're laying low! Try stealing again in {remaining // 3600}h {(remaining % 3600) // 60}m.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return

        # Check for anti-theft item
        _, _, inv_target, *_ = get_player(member.id)
        items = inv_target.split(",") if inv_target else []
        if "Anti-Theft Token" in items:
            # Remove the token after use
            items.remove("Anti-Theft Token")
            new_inv = ",".join(items)
            update_player(member.id, inventory=new_inv)
            await ctx.send(f"🛡️ {member.display_name} was protected by an Anti-Theft Token! Your attempt failed and their token was consumed.")
            return
        coins_from, bank_from, *_ = get_player(ctx.author.id)
        coins_to, bank_to, *_ = get_player(member.id)
        if coins_to < 100:
            await ctx.send("That user doesn't have enough coins to steal from (minimum 100).")
            return
        if random.random() < STEAL_SUCCESS_CHANCE:
            stolen = random.randint(50, min(300, coins_to))
            coins_to -= stolen
            coins_from += stolen
            update_player(ctx.author.id, coins=coins_from)
            update_player(member.id, coins=coins_to)
            embed = discord.Embed(
                title="Steal Success! 🦹",
                description=f"You stole {stolen} coins from {member.mention}!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            # Caught! Pay bail.
            bail = min(STEAL_BAIL_COST, coins_from)
            coins_from -= bail
            update_player(ctx.author.id, coins=coins_from)
            embed = discord.Embed(
                title="Caught! 🚨",
                description=f"You got caught trying to steal and paid {bail} coins as bail.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        set_cooldown(ctx.author.id, "steal", now)  # Save cooldown persistently

    @steal.error
    async def steal_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="Cooldown",
                description=f"You're laying low! Try stealing again in {int(error.retry_after // 3600)}h {(int(error.retry_after) % 3600) // 60}m.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="Error",
                description=f"An unexpected error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        return  # <--- Always return to prevent propagation

    @commands.hybrid_command(name="slots", description="Play the slot machine for a chance to win coins!")
    async def slots(self, ctx, bet: int):
        add_player_if_not_exists(ctx.author.id)
        coins, bank, inv, *_ = get_player(ctx.author.id)
        if bet <= 0:
            await ctx.send("Bet must be greater than 0.")
            return
        if coins < bet:
            await ctx.send("You don't have enough coins to bet that amount.")
            return

        # Add more emojis to reduce win odds
        symbols = ["🍒", "🍋", "🍉", "⭐", "💎", "🍀", "🍇"]
        result = [random.choice(symbols) for _ in range(3)]
        win = False
        payout = 0
        lootbox_won = False

        if result[0] == result[1] == result[2]:
            # Jackpot!
            payout = bet * 10
            win = True
            # 15% chance to win a lootbox on jackpot
            if random.random() < 0.15:
                lootbox_won = True
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            # Small win
            payout = bet * 2
            win = True
            # 5% chance to win a lootbox on small win
            if random.random() < 0.05:
                lootbox_won = True
        else:
            payout = -bet

        coins += payout
        # Add lootbox to inventory if won
        if lootbox_won:
            items = inv.split(",") if inv else []
            items.append("Lootbox")
            new_inv = ",".join(items)
            update_player(ctx.author.id, coins=coins, inventory=new_inv)
        else:
            update_player(ctx.author.id, coins=coins)

        embed = discord.Embed(
            title="Slots",
            description=f"{' '.join(result)}",
            color=discord.Color.gold() if win else discord.Color.red()
        )
        if win:
            msg = f"You won {payout} coins!" if payout > 0 else "You broke even!"
            if lootbox_won:
                msg += "\n🎁 **BONUS! You also won a Lootbox!**"
            embed.add_field(name="Result", value=msg, inline=False)
        else:
            embed.add_field(name="Result", value=f"You lost {bet} coins.", inline=False)
        embed.add_field(name="Balance", value=f"💰 {coins} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="shop", description="View the shop. Use /shop buy <command_name> or /shop sell <command_name>.")
    @discord.app_commands.describe(
        action="Choose 'buy' or 'sell' to interact, or leave blank to browse the shop.",
        command_name="The command name of the item to buy or sell.",
        quantity="How many to buy or sell (default 1)."
    )
    async def shop(self, ctx, action: str = None, command_name: str = None, quantity: int = 1):
        items = get_shop_items(ctx.guild.id)
        if not items:
            embed = discord.Embed(
                title="Shop",
                description="The shop is empty. Ask an admin to add items!",
                color=discord.Color.blurple()
            )
            await ctx.send(embed=embed)
            return

        # Sort items by rarity, then price (optional)
        rarity_order = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3, "legendary": 4}
        items.sort(key=lambda x: (rarity_order.get((x[4] or "").lower(), 99), x[2]))

        if not action:
            view = ShopPageView(ctx, items)
            embed = discord.Embed(
                title="Shop (Page 1)",
                description="Use `/shop buy <command_name>` or `/shop sell <command_name>` to buy/sell.",
                color=discord.Color.blurple()
            )
            for name, cmd, price, desc, rarity, item_type in items[:6]:
                meta = []
                if item_type:
                    meta.append(f"Type: {item_type.capitalize()}")
                if rarity:
                    meta.append(f"Rarity: {rarity.capitalize()}")
                meta_str = " | ".join(meta)
                embed.add_field(
                    name=f"{name} (`{cmd}`) - {price} coins",
                    value=f"{desc}\n{meta_str}" if meta_str else desc,
                    inline=False
                )
            await ctx.send(embed=embed, view=view)
            return

        action = action.lower() if action else None
        if action not in ["buy", "sell"]:
            await ctx.send("Invalid action. Use `buy` or `sell`.")
            return

        if not command_name:
            await ctx.send(f"Please specify the command name of the item to {action}.")
            return

        if quantity < 1:
            await ctx.send("Quantity must be at least 1.")
            return

        item = get_shop_item_by_command(ctx.guild.id, command_name.lower())
        if not item:
            await ctx.send(f"Item with command name `{command_name}` not found.")
            return

        item_name, cmd, price, desc, effect, rarity, item_type = item

        if action == "buy":
            coins, bank, inv, *_ = get_player(ctx.author.id)
            total_price = price * quantity
            if coins < total_price:
                await ctx.send(f"You need {total_price} coins to buy {quantity} of this item.")
                return
            items = inv.split(",") if inv else []
            items.extend([item_name] * quantity)
            new_inv = ",".join(items)
            coins -= total_price
            update_player(ctx.author.id, coins=coins, inventory=new_inv)
            embed = discord.Embed(
                title="Purchase Successful",
                description=f"You bought **{quantity}x {item_name}**!\n{desc}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        elif action == "sell":
            coins, bank, inv, *_ = get_player(ctx.author.id)
            items = inv.split(",") if inv else []
            owned = items.count(item_name)
            if owned < quantity:
                await ctx.send(f"You do not have {quantity}x `{item_name}` in your inventory.")
                return
            # Try to get price from current guild shop first
            item = get_shop_item_by_command(ctx.guild.id, command_name.lower())
            if not item:
                # Fallback: get price from any shop
                item = get_shop_item_any(item_name)
            if not item:
                await ctx.send(f"Cannot determine price for `{item_name}`. Item not found in any shop.")
                return
            _, _, price, *_ = item
            sell_price = int(price * 0.5) * quantity
            coins += sell_price
            for _ in range(quantity):
                items.remove(item_name)
            new_inv = ",".join(items)
            update_player(ctx.author.id, coins=coins, inventory=new_inv)
            embed = discord.Embed(
                title="Item Sold",
                description=f"You sold **{quantity}x {item_name}** for {sell_price} coins.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="inventory", description="View your inventory.")
    async def inventory(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        add_player_if_not_exists(member.id)
        _, _, inv, *_ = get_player(member.id)
        embed = discord.Embed(
            title=f"{member.display_name}'s Inventory",
            color=discord.Color.blurple()
        )
        emoji_map = {
            "Coin Booster": "💸",
            "VIP Role": "🌟",
            "Lucky Charm": "🍀",
            "Miniature Dragon": "🐉",
            "Signed D20": "🎲",
            "Foil MTG Card": "🃏",
            "Tabletop Mug": "☕",
            "Custom Token": "🔖",
            "Lootbox": "🎁",
            "Anti-Theft Token": "🛡️",
            "Plastic Meeple": "🧩",
            "Wooden Cube": "🟫",
            "Card Sleeve": "🪪",
            "Mini Dice Set": "🎲",
            "Pawn Figure": "♟️",
            "Score Pad": "📒",
            "Plastic Coin": "🪙",
            "Reference Card": "📑",
            "Metal Coin": "🥇",
            "Acrylic Standee": "🧍",
            "Dice Bag": "🛍️",
            "Metallic Token": "🔗",
            "Meeple Keychain": "🔑",
            "Dice Tray": "🧺",
            "Game Organizer": "🗃️",
            "Enamel Pin": "📌",
            "Collector's Dice": "🎲",
            "Signed Card": "✍️",
            "Holographic Token": "✨",
            "Limited Edition Meeple": "🧙",
            "Collector's Coin": "🪙",
            "Crystal Dice": "💠",
            "Art Print": "🖼️",
            "Gold Foil Card": "🏅",
            "Golden Meeple": "🏆",
            "Diamond Dice": "💎",
            "Signed Board Game": "📦",
            "Mythic Trophy": "🏆"
        }
        if not inv or not inv.strip():
            embed.description = "Your inventory is empty."
        else:
            items = inv.split(",")
            item_counts = {}
            for item in items:
                if item:
                    item_counts[item] = item_counts.get(item, 0) + 1
            lines = [f"{emoji_map.get(name, '📦')} {amount}x {name}" for name, amount in item_counts.items()]
            embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="give", description="Give coins to another user.")
    @discord.app_commands.describe(
        member="The member to give coins to.",
        amount="The amount of coins to give."
    )
    async def give(self, ctx, member: discord.Member, amount: int):
        if amount <= 0:
            embed = discord.Embed(
                title="Invalid Amount",
                description="You must give a positive amount of coins.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        add_player_if_not_exists(ctx.author.id)
        add_player_if_not_exists(member.id)
        coins_from, bank_from, inv_from, *_ = get_player(ctx.author.id)
        coins_to, bank_to, inv_to, *_ = get_player(member.id)
        if coins_from < amount:
            embed = discord.Embed(
                title="Not Enough Coins",
                description="You do not have enough coins to give.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        coins_from -= amount
        coins_to += amount
        update_player(ctx.author.id, coins=coins_from)
        update_player(member.id, coins=coins_to)
        embed = discord.Embed(
            title="Coins Transferred",
            description=f"You gave {amount} coins to {member.mention}.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="shopadmin", description="Shop admin commands (add, remove, price).", invoke_without_command=True)
    @commands.has_guild_permissions(administrator=True)
    async def shopadmin(self, ctx):
        embed = discord.Embed(
            title="Shop Admin Commands",
            description="Use a subcommand: `add`, `remove`, or `price`.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="/shopadmin add", value="Add an item to the shop.", inline=False)
        embed.add_field(name="/shopadmin remove", value="Remove an item from the shop.", inline=False)
        embed.add_field(name="/shopadmin price", value="Change the price of an item.", inline=False)
        await ctx.send(embed=embed)

    @shopadmin.command(name="add", description="Add an item to the shop.")
    @discord.app_commands.describe(
        item_name="Name of the item.",
        command_name="Short command name for buying/selling (e.g. coinboost).",
        price="Price of the item.",
        description="Description of the item.",
        effect="Optional effect (input help for options).",
        rarity="Rarity for collectibles (common, uncommon, rare, epic, legendary).",
        item_type="Type of the item (boost, collectible, lootbox, role, etc)."
    )
    async def shopadmin_add(
        self, ctx,
        item_name: str,
        command_name: str,
        price: int,
        description: str,
        effect: str = None,
        rarity: str = None,
        item_type: str = None
    ):
        # Show a guide for effects if requested
        if effect is not None and effect.lower() == "help":
            embed = discord.Embed(
                title="Shopadmin Add: Effect Guide",
                description="Here are the available effect formats for shop items:",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="boost",
                value="`boost` — Doubles coin gains from /daily and /work.",
                inline=False
            )
            embed.add_field(
                name="luck",
                value="`luck` — Increases your chance of getting higher rarity items from lootboxes.",
                inline=False
            )
            embed.add_field(
                name="role",
                value="`role:ROLE_ID` — Grants a Discord role when used. Replace ROLE_ID with the actual role ID.",
                inline=False
            )
            embed.add_field(
                name="collectible",
                value="`collectible:RARITY` — Marks the item as a collectible of a certain rarity (common, uncommon, rare, epic, legendary).",
                inline=False
            )
            embed.add_field(
                name="antitheft",
                value="`antitheft` — Prevents you from being stolen from for 24 hours.",
                inline=False
            )
            embed.set_footer(text="Use /shopadmin add ... effect:help to see this guide.")
            await ctx.send(embed=embed)
            return

        add_shop_item(ctx.guild.id, item_name, command_name, price, description, effect, rarity, item_type)
        embed = discord.Embed(
            title="Shop Item Added",
            description=f"**{item_name}** (`{command_name}`) has been added to the shop.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @shopadmin.command(name="remove", description="Remove an item from the shop.")
    @discord.app_commands.describe(
        command_name="Command name of the item to remove (e.g. coinboost)."
    )
    async def shopadmin_remove(self, ctx, command_name: str):
        remove_shop_item(ctx.guild.id, command_name)
        embed = discord.Embed(
            title="Shop Item Removed",
            description=f"Item with command name `{command_name}` has been removed from the shop.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @shopadmin.command(name="price", description="Change the price of an item in the shop.")
    @discord.app_commands.describe(
        command_name="Command name of the item to change price.",
        new_price="The new price for the item."
    )
    async def shopadmin_price(self, ctx, command_name: str, new_price: int):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE eco_shop SET price = ? WHERE guild_id = ? AND command_name = ?",
            (new_price, str(ctx.guild.id), command_name)
        )
        conn.commit()
        conn.close()
        embed = discord.Embed(
            title="Shop Item Price Updated",
            description=f"Price for `{command_name}` has been set to {new_price} coins.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # @commands.hybrid_command(name="eco", description="Show your economy profile.")
    # async def eco(self, ctx, member: discord.Member = None):
    #     member = member or ctx.author
    #     add_player_if_not_exists(member.id)
    #     coins, bank, inv, *_ = get_player(member.id)
    #     embed = discord.Embed(
    #         title=f"{member.display_name}'s Economy Profile",
    #         color=discord.Color.blurple()
    #     )
    #     embed.add_field(name="Coins", value=f"💰 {coins}", inline=False)
    #     embed.add_field(name="Bank", value=f"🏦 {bank}/{BANK_MAX}", inline=False)
    #     if not inv:
    #         embed.add_field(name="Inventory", value="Empty", inline=False)
    #     else:
    #         items = inv.split(",")
    #         embed.add_field(name="Inventory", value="\n".join(f"- {item}" for item in items), inline=False)
    #     await ctx.send(embed=embed)

    @commands.hybrid_command(name="use", description="Use an item from your inventory.")
    @discord.app_commands.describe(
        item_name="The name of the item to use."
    )
    async def use(self, ctx, *, item_name: str):
        add_player_if_not_exists(ctx.author.id)
        coins, bank, inv, *_ = get_player(ctx.author.id)
        items = inv.split(",") if inv else []

        # Normalize input and inventory for case-insensitive, space-insensitive match
        def normalize(s):
            return s.replace(" ", "").lower()

        normalized_input = normalize(item_name)
        matched_item = None
        for inv_item in items:
            if normalize(inv_item) == normalized_input:
                matched_item = inv_item
                break

        if not matched_item:
            embed = discord.Embed(
                title="Item Not Found",
                description="You do not have this item in your inventory.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # --- RPG item protection ---
        # Load RPG item names from default_items.json except Gold Coin
        import json
        RPG_ITEMS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "default_items.json")
        with open(RPG_ITEMS_PATH, "r", encoding="utf-8") as f:
            RPG_ITEMS = json.load(f)
        rpg_item_names = {item["item_name"] for item in RPG_ITEMS if item["item_name"] != "Gold Coin"}

        if matched_item in rpg_item_names:
            if matched_item == "Gold Coin":
                pass  # allow
            else:
                embed = discord.Embed(
                    title="Cannot Use RPG Item",
                    description="RPG items can only be used with RPG commands (e.g. `/rpgheal`, `/rpgweapon`, `/rpgspells`).",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return

        item = get_shop_item_any(matched_item)
        if not item:
            embed = discord.Embed(
                title="Item Not Found",
                description="This item does not exist in the shop.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        _, _, desc, effect, rarity, _ = item
        # Handle known effects
        if effect == "boost":
            embed = discord.Embed(
                title="Boost Activated!",
                description="Your coin gains from `/daily` and `/work` are now doubled for 7 days! (Feature coming soon)",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        elif effect == "luck":
            expiry = datetime.datetime.utcnow() + datetime.timedelta(days=1)
            set_luck_expiry(ctx.author.id, expiry)
            embed = discord.Embed(
                title="Lucky Item Used!",
                description="Your chance of getting higher rarity items from `/lootbox` is increased for 24 hours!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        elif effect and effect.startswith("role:"):
            role_id = int(effect.split(":")[1])
            role = ctx.guild.get_role(role_id)
            if role:
                try:
                    await ctx.author.add_roles(role, reason="Used item from shop")
                    embed = discord.Embed(
                        title="Role Granted!",
                        description=f"You have been given the role {role.mention}!",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=embed)
                except Exception:
                    await ctx.send("Could not assign the role. Please check my permissions.")
            else:
                await ctx.send("Role not found. Please contact an admin.")
        elif effect and effect.startswith("collectible:"):
            embed = discord.Embed(
                title="Collectible",
                description=f"You admire your {item_name}. (Collectibles can be traded or sold in the future!)",
                color=discord.Color.blurple()
            )
            await ctx.send(embed=embed)
        else:
            # Custom effect
            embed = discord.Embed(
                title="Item Used",
                description=f"You used **{item_name}**!\n{desc}\nEffect: {effect or 'None'}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        # Remove the used item if it's consumable (except collectibles/roles)
        if not (effect and (effect.startswith("collectible:") or effect.startswith("role:"))):
            items.remove(matched_item)
            new_inv = ",".join(items)
            update_player(ctx.author.id, inventory=new_inv)

    @commands.hybrid_command(name="lootbox", description="Open a lootbox for a chance at rare collectibles!")
    async def lootbox(self, ctx):
        add_player_if_not_exists(ctx.author.id)
        coins, bank, inv, *_ = get_player(ctx.author.id)
        items = inv.split(",") if inv else []
        # Check if user has a Lootbox in inventory
        if "Lootbox" not in items:
            embed = discord.Embed(
                title="No Lootbox",
                description="You don't have a Lootbox in your inventory. Buy one from the shop or earn it from your daily streak!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Remove one Lootbox from inventory
        items.remove("Lootbox")
        new_inv = ",".join(items)
        update_player(ctx.author.id, inventory=new_inv)

        collectibles = get_all_collectibles(ctx.guild.id)
        if not collectibles:
            embed = discord.Embed(
                title="No Collectibles",
                description="There are no collectibles in the shop to win.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        odds = get_rarity_odds()
        # Check for active luck effect
        luck_expiry = get_luck_expiry(ctx.author.id)
        now = datetime.datetime.utcnow()
        if luck_expiry and luck_expiry > now:
            # Boost odds for higher rarities (example: +5% to each above common, -20% from common)
            odds = {
                "common": max(odds["common"] - 0.20, 0),
                "uncommon": odds["uncommon"] + 0.08,
                "rare": odds["rare"] + 0.06,
                "epic": odds["epic"] + 0.04,
                "legendary": odds["legendary"] + 0.02
            }
            # Normalize to sum to 1.0
            total = sum(odds.values())
            for k in odds:
                odds[k] /= total

        # Group collectibles by rarity
        rarity_groups = {}
        for name, rarity in collectibles:
            rarity_groups.setdefault(rarity or "common", []).append(name)
            
        # Roll for rarity
        roll = random.random()
        cumulative = 0
        selected_rarity = "common"
        rarity_order = ["common", "uncommon", "rare", "epic", "legendary"]
        for rarity in rarity_order:
            chance = odds.get(rarity, 0)
            cumulative += chance
            if roll <= cumulative:
                selected_rarity = rarity
                break

        # Pick a random collectible from that rarity
        pool = rarity_groups.get(selected_rarity, rarity_groups.get("common", []))
        if not pool:
            pool = [name for names in rarity_groups.values() for name in names]
        won_item = random.choice(pool)
        # Add to inventory
        items.append(won_item)
        new_inv = ",".join(items)
        update_player(ctx.author.id, inventory=new_inv)
        embed = discord.Embed(
            title="Lootbox Opened!",
            description=f"You won: **{won_item}** ({selected_rarity.capitalize()})",
            color=discord.Color.gold()
        )
        if luck_expiry and luck_expiry > now:
            embed.set_footer(text="Your Lucky Charm is active!")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="leaderboard", description="Show the richest people.", invoke_without_command=True)
    async def leaderboard(self, ctx):
        embed = discord.Embed(
            title="Leaderboard Commands",
            description="Use a subcommand: `/leaderboard global` or `/leaderboard local`.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="/leaderboard global", value="Show the top 5 richest users globally.", inline=False)
        embed.add_field(name="/leaderboard local", value="Show the top 5 richest users in this server.", inline=False)
        await ctx.send(embed=embed)

    @leaderboard.command(name="global", description="Show the top 5 richest users globally.")
    async def leaderboard_global(self, ctx):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, coins, bank FROM eco_players ORDER BY (coins + bank) DESC LIMIT 5"
        )
        top = cursor.fetchall()
        conn.close()
        embed = discord.Embed(
            title="Top 5 Richest (Global)",
            color=discord.Color.gold()
        )
        if not top:
            embed.description = "No players found."
        else:
            lines = []
            for idx, (user_id, coins, bank) in enumerate(top, 1):
                user = ctx.guild.get_member(int(user_id)) or ctx.bot.get_user(int(user_id))
                name = user.display_name if user and hasattr(user, "display_name") else (user.name if user else f"User ID {user_id}")
                total = coins + bank
                lines.append(f"**{idx}. {name}** — 💰 **{total}** coins")
            embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @leaderboard.command(name="local", description="Show the top 5 richest users in this server.")
    async def leaderboard_local(self, ctx):
        guild_member_ids = {str(m.id) for m in ctx.guild.members}
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, coins, bank FROM eco_players"
        )
        all_players = cursor.fetchall()
        conn.close()
        # Filter for members in this guild
        local_players = [row for row in all_players if row[0] in guild_member_ids]
        local_players.sort(key=lambda row: row[1] + row[2], reverse=True)
        embed = discord.Embed(
            title=f"Top 5 Richest in {ctx.guild.name}",
            color=discord.Color.gold()
        )
        if not local_players:
            embed.description = "No players found."
        else:
            lines = []
            for idx, (user_id, coins, bank) in enumerate(local_players[:5], 1):
                member = ctx.guild.get_member(int(user_id))
                name = member.display_name if member else f"User ID {user_id}"
                total = coins + bank
                lines.append(f"**{idx}. {name}** — 💰 **{total}** coins")
            embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="deposit", description="🏦 Deposit coins into your bank (max capacity applies).")
    async def deposit(self, ctx, amount: int):
        add_player_if_not_exists(ctx.author.id)
        coins, bank, *_ = get_player(ctx.author.id)
        if amount <= 0:
            await ctx.send("Deposit amount must be positive.")
            return
        if coins < amount:
            await ctx.send("You don't have enough coins to deposit.")
            return
        if bank + amount > BANK_MAX:
            amount = BANK_MAX - bank
        if amount <= 0:
            await ctx.send(f"Your bank is full! Max capacity: {BANK_MAX} coins.")
            return
        coins -= amount
        bank += amount
        update_player(ctx.author.id, coins=coins, bank=bank)
        await ctx.send(f"🏦 Deposited {amount} coins to your bank. Bank: {bank}/{BANK_MAX} coins.")

    @commands.hybrid_command(name="withdraw", description="🏦 Withdraw coins from your bank.")
    async def withdraw(self, ctx, amount: int):
        add_player_if_not_exists(ctx.author.id)
        coins, bank, *_ = get_player(ctx.author.id)
        if amount <= 0:
            await ctx.send("Withdraw amount must be positive.")
            return
        if bank < amount:
            await ctx.send("You don't have that many coins in your bank.")
            return
        coins += amount
        bank -= amount
        update_player(ctx.author.id, coins=coins, bank=bank)
        await ctx.send(f"🏦 Withdrew {amount} coins from your bank. Bank: {bank}/{BANK_MAX} coins.")


async def setup(bot):
    await bot.add_cog(EcoCog(bot))