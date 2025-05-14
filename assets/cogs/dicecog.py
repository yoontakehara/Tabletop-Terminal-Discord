import discord
from discord.ext import commands
import random

class DiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="damage",
        description="Roll a damage die (d4, d6, d8, d10, d12) and pick a damage modifier."
    )
    @discord.app_commands.describe(
        dice_type="d4, d6, d8, d10, d12",
        amount="1-100, default 1",
        modifier="normal, res, vul (default normal)"
    )
    async def damage(self, ctx, dice_type: str, amount: int = 1, modifier: str = "normal"):
        dice_type = dice_type.lower()
        modifier = modifier.lower()
        valid_types = {"d4": 4, "d6": 6, "d8": 8, "d10": 10, "d12": 12}
        valid_mods = {"normal", "res", "vul"}
        if dice_type not in valid_types:
            embed = discord.Embed(
                title="Invalid Damage Die",
                description="Choose from: d4, d6, d8, d10, d12.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        if amount < 1 or amount > 100:
            embed = discord.Embed(
                title="Invalid Amount",
                description="You can roll between 1 and 100 dice.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return
        if modifier not in valid_mods:
            embed = discord.Embed(
                title="Invalid Modifier",
                description="Choose from: normal (default), res (resistance), vul (vulnerable).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        sides = valid_types[dice_type]
        rolls = [random.randint(1, sides) for _ in range(amount)]
        base_total = sum(rolls)
        if modifier == "res":
            total = base_total // 2
            mod_text = " (resistance: halved)"
        elif modifier == "vul":
            total = base_total * 2
            mod_text = " (vulnerable: doubled)"
        else:
            total = base_total
            mod_text = ""

        rolls_str = ", ".join(str(r) for r in rolls)
        embed = discord.Embed(
            title="🎲 Damage Roll",
            description=f"Rolled `{amount} x {dice_type}`: **{rolls_str}**\nTotal: **{total}**{mod_text}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="action",
        description="Roll for action: norm (Normal), adv (Advantage), dadv (Disadvantage), perc (Percentile)."
    )
    @discord.app_commands.describe(
        action_type="Type of action roll: norm, adv, dadv, perc"
    )
    async def action(self, ctx, action_type: str):
        action_type = action_type.lower()
        if action_type == "norm":
            roll = random.randint(1, 20)
            desc = f"Normal roll: **{roll}**"
        elif action_type == "adv":
            rolls = [random.randint(1, 20), random.randint(1, 20)]
            desc = f"Advantage roll: **{max(rolls)}** (rolled {rolls[0]} and {rolls[1]})"
        elif action_type == "dadv":
            rolls = [random.randint(1, 20), random.randint(1, 20)]
            desc = f"Disadvantage roll: **{min(rolls)}** (rolled {rolls[0]} and {rolls[1]})"
        elif action_type == "perc":
            roll = random.randint(1, 100)
            desc = f"Percentile roll: **{roll}%**"
        else:
            embed = discord.Embed(
                title="Invalid Action Type",
                description="Choose from: norm (Normal), adv (Advantage), dadv (Disadvantage), perc (Percentile).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title="🎲 Action Roll",
            description=desc,
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DiceCog(bot))