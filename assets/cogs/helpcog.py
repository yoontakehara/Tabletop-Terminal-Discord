import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show all available commands or details for a specific command.")
    async def custom_help(self, ctx, *, command_name: str = None):
        if command_name:
            # Show help for a specific command
            command = self.bot.get_command(command_name)
            if not command or command.hidden:
                embed = discord.Embed(
                    title="Command Not Found",
                    description=f"No command named `{command_name}` found.",
                    color=discord.Color.red()
                )
            else:
                signature = f"/{command.qualified_name} {command.signature}".strip()
                embed = discord.Embed(
                    title=f"Help for `{command.qualified_name}`",
                    description=f"**Usage:** `{signature}`\n\n**Description:** {command.help or command.description or 'No description.'}",
                    color=discord.Color.blurple()
                )
            if hasattr(ctx, "interaction") and ctx.interaction is not None:
                await ctx.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed)
            return

        # Show all commands grouped by cog, skip HelpCog
        embed = discord.Embed(
            title="Tabletop Terminal Help",
            description="Commands are grouped by category (cog). Use them as slash commands or with your server's prefix.",
            color=discord.Color.blurple()
        )

        cog_map = {}
        for command in self.bot.commands:
            if command.hidden or (command.cog_name and command.cog_name.lower() == "helpcog"):
                continue
            cog_name = command.cog_name or "Other"
            cog_map.setdefault(cog_name, []).append(command)

        for cog, commands_list in cog_map.items():
            # Join command names in a single line, each in backticks
            value = " ".join(f"`{command.qualified_name}`" for command in commands_list)
            embed.add_field(
                name=f"{cog} Commands",
                value=value,
                inline=False
            )

        embed.set_footer(text="Use t!help <command> or /help <command> for details on a specific command.")

        if hasattr(ctx, "interaction") and ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))