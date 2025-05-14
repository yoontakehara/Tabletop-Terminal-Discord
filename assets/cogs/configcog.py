import discord
import datetime
from discord.ext import commands
import sqlite3
import os
from discord import ui, Interaction
from assets.utils.helpers import mention_channel, mention_role, get_config_value

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "data.db")

class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def update_table(self, table, column, value, guild_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table} SET {column} = ? WHERE guild_id = ?", (value, str(guild_id)))
        conn.commit()
        conn.close()

    async def send_embed(self, ctx, description, color=discord.Color.green(), ephemeral=False):
        embed = discord.Embed(description=description, color=color)
        if hasattr(ctx, "interaction") and ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=ephemeral)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="setprefix", description="Set the command prefix for this server.")
    @commands.has_guild_permissions(administrator=True)
    @discord.app_commands.describe(
        prefix="The new prefix to use for commands."
    )
    async def set_prefix(self, ctx, prefix: str):
        self.update_table("prefixes", "prefix", prefix, ctx.guild.id)
        await self.send_embed(ctx, f"Prefix updated to `{prefix}`.", ephemeral=True)

    @commands.hybrid_group(name="setwelcome", description="Configure the welcome settings for this server.", invoke_without_command=True)
    @commands.has_guild_permissions(administrator=True)
    async def setwelcome(self, ctx):
        embed = discord.Embed(
            title="Welcome Configuration",
            description=(
                "Use the subcommands to configure welcome settings.\n\n"
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(name="channel", value="Set the welcome channel.", inline=False)
        embed.add_field(name="message", value="Set the welcome message.", inline=False)
        embed.add_field(name="autorole", value="Set the autorole for new members.", inline=False)
        embed.add_field(name="image", value="Set the welcome image URL.", inline=False)
        await ctx.send(embed=embed)

    @setwelcome.command(name="channel", description="Set the welcome channel.")
    @discord.app_commands.describe(
        channel="The channel where welcome messages will be sent."
    )
    async def setwelcome_channel(self, ctx, channel: discord.TextChannel):
        self.update_table("welcome", "channel", str(channel.id), ctx.guild.id)
        await self.send_embed(ctx, f"Welcome channel set to {channel.mention}.", ephemeral=True)

    @setwelcome.command(name="message", description="Set the welcome message. Use `{user}` and `{server}` as placeholders.")
    @discord.app_commands.describe(
        message="The welcome message to send. Configuration brackets: `{user}`, `{server}` "
    )
    async def setwelcome_message(self, ctx, *, message: str):
        self.update_table("welcome", "message", message, ctx.guild.id)
        await self.send_embed(ctx, "Welcome message updated.", ephemeral=True)

    @setwelcome.command(name="autorole", description="Set the autorole for new members.")
    @discord.app_commands.describe(
        role="The role to assign to new members."
    )
    async def setwelcome_autorole(self, ctx, role: discord.Role):
        self.update_table("welcome", "autorole", str(role.id), ctx.guild.id)
        await self.send_embed(ctx, f"Autorole set to {role.mention}.", ephemeral=True)

    @setwelcome.command(name="image", description="Set the welcome image URL.")
    @discord.app_commands.describe(
        url="The image URL to include in the welcome message."
    )
    async def setwelcome_image(self, ctx, url: str):
        self.update_table("welcome", "image_url", url, ctx.guild.id)
        await self.send_embed(ctx, "Welcome image URL updated.", ephemeral=True)

    @commands.hybrid_command(name="setmuterole", description="Set the mute role for this server.")
    @commands.has_guild_permissions(administrator=True)
    @discord.app_commands.describe(
        role="The role to assign to muted members."
    )
    async def set_mute_role(self, ctx, role: discord.Role):
        self.update_table("mutes", "mute_role", str(role.id), ctx.guild.id)
        await self.send_embed(ctx, f"Mute role set to {role.mention}.", ephemeral=True)

    @commands.hybrid_command(name="muterolehelp", description="Show a tutorial for setting up the mute role.")
    @commands.has_guild_permissions(administrator=True)
    async def muterolehelp(self, ctx):
        embed = discord.Embed(
            title="Mute Role Setup Tutorial",
            description=(
                "**How to set up the mute role:**\n"
                "1. Create a role called `Muted` (or any name you prefer).\n"
                "2. Make sure this role is **below** your admin/mod roles but **above** regular members.\n"
                "3. Edit channel permissions for this role to **deny** sending messages and speaking in all channels.\n"
                "4. Use `/setmuterole @Muted` to set it as the mute role for this server.\n"
                "5. Now you can use `/mute` and `/unmute` commands to mute or unmute members."
            ),
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setlogchannel", description="Set the log channel for this server.")
    @commands.has_guild_permissions(administrator=True)
    @discord.app_commands.describe(
        channel="The channel where logs will be sent."
    )
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        self.update_table("logs", "log_channel", str(channel.id), ctx.guild.id)
        await self.send_embed(ctx, f"Log channel set to {channel.mention}.", ephemeral=True)

    @commands.hybrid_command(name="setannouncechannel", description="Set the announcement channel for this server.")
    @commands.has_guild_permissions(administrator=True)
    @discord.app_commands.describe(
        channel="The channel where announcements will be sent."
    )
    async def set_announce_channel(self, ctx, channel: discord.TextChannel):
        self.update_table("announcements", "announcement_channel", str(channel.id), ctx.guild.id)
        await self.send_embed(ctx, f"Announcement channel set to {channel.mention}.", ephemeral=True)

    @commands.hybrid_command(name="setmodmailchannel", description="Set the modmail channel for this server.")
    @commands.has_guild_permissions(administrator=True)
    @discord.app_commands.describe(
        channel="The channel where modmail messages will be sent."
    )
    async def set_modmail_channel(self, ctx, channel: discord.TextChannel):
        self.update_table("modmail", "modmail_channel", str(channel.id), ctx.guild.id)
        await self.send_embed(ctx, f"Modmail channel set to {channel.mention}.", ephemeral=True)

    @commands.hybrid_command(name="modmailhelp", description="Show a tutorial for setting up modmail.")
    @commands.has_guild_permissions(administrator=True)
    async def modmailhelp(self, ctx):
        embed = discord.Embed(
            title="Modmail Setup Tutorial",
            description=(
                "**How to set up Modmail:**\n"
                "1. Create a private text channel for modmail (e.g., `#modmail`).\n"
                "2. Use `/setmodmail #modmail` to set it as the modmail channel.\n"
                "3. Users can now send anonymous messages to moderators using `/modmail <your message>`.\n\n"
                "**Notes:**\n"
                "- Only server admins can set the modmail channel.\n"
                "- Messages sent via `/modmail` are anonymous and do not reveal the sender's identity.\n"
                "- If you change the modmail channel, just run `/setmodmail` again."
            ),
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="showconfig", description="Show the current configuration for this server.")
    @commands.has_guild_permissions(administrator=True)
    async def show_config(self, ctx):
        guild_id = str(ctx.guild.id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Fetch all config values
        cursor.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (guild_id,))
        result = cursor.fetchone()
        prefix = get_config_value(result[0] if result else None, "Not set")

        cursor.execute("SELECT channel, message, autorole, image_url FROM welcome WHERE guild_id = ?", (guild_id,))
        welcome = cursor.fetchone()
        welcome_channel = mention_channel(welcome[0]) if welcome and welcome[0] else "Not set"
        welcome_message = f"`{welcome[1]}`" if welcome and welcome[1] else "`Not set`"
        autorole = mention_role(welcome[2]) if welcome and welcome[2] else "Not set"
        image_url = f"`{welcome[3]}`" if welcome and welcome[3] else "`Not set`"

        cursor.execute("SELECT mute_role FROM mutes WHERE guild_id = ?", (guild_id,))
        mute_row = cursor.fetchone()
        mute_role = mention_role(mute_row[0]) if mute_row and mute_row[0] else "Not set"

        cursor.execute("SELECT log_channel FROM logs WHERE guild_id = ?", (guild_id,))
        log_row = cursor.fetchone()
        log_channel = mention_channel(log_row[0]) if log_row and log_row[0] else "Not set"

        cursor.execute("SELECT announcement_channel FROM announcements WHERE guild_id = ?", (guild_id,))
        announce_row = cursor.fetchone()
        announce_channel = mention_channel(announce_row[0]) if announce_row and announce_row[0] else "Not set"

        cursor.execute("SELECT modmail_channel FROM modmail WHERE guild_id = ?", (guild_id,))
        modmail_row = cursor.fetchone()
        modmail_channel = mention_channel(modmail_row[0]) if modmail_row and modmail_row[0] else "Not set"

        conn.close()

        embed = discord.Embed(
            title=f"Server Configuration for {ctx.guild.name}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=False)
        embed.add_field(name="Welcome Channel", value=f"{welcome_channel}", inline=False)
        embed.add_field(name="Welcome Message", value=f"`{welcome_message}`", inline=False)
        embed.add_field(name="Autorole", value=f"`{autorole}`", inline=False)
        embed.add_field(name="Welcome Image URL", value=f"`{image_url}`", inline=False)
        embed.add_field(name="Mute Role", value=f"`{mute_role}`", inline=False)
        embed.add_field(name="Log Channel", value=f"`{log_channel}`", inline=False)
        embed.add_field(name="Announcement Channel", value=f"`{announce_channel}`", inline=False)
        embed.add_field(name="Modmail Channel", value=f"{modmail_channel}", inline=False)

        # Add this line to set the footer with the current time
        embed.set_footer(text=f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if hasattr(ctx, "interaction") and ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # Ignore errors already handled by local error handlers
        if hasattr(ctx.command, 'on_error'):
            return

        # Handle missing permissions
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="Permission Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True if hasattr(ctx, "interaction") and ctx.interaction else False)
            return

        # Handle missing required arguments
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Missing Argument",
                description=f"Missing required argument: `{error.param.name}`.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed, ephemeral=True if hasattr(ctx, "interaction") and ctx.interaction else False)
            return

        # Handle bad argument type
        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="Invalid Argument",
                description="You provided an invalid argument. Please check your input.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed, ephemeral=True if hasattr(ctx, "interaction") and ctx.interaction else False)
            return

        # Handle command not found (shouldn't trigger here, but for completeness)
        if isinstance(error, commands.CommandNotFound):
            embed = discord.Embed(
                title="Command Not Found",
                description="That command does not exist.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True if hasattr(ctx, "interaction") and ctx.interaction else False)
            return

        # Fallback for any other errors
        embed = discord.Embed(
            title="Error",
            description=f"An unexpected error occurred: `{str(error)}`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, ephemeral=True if hasattr(ctx, "interaction") and ctx.interaction else False)

async def setup(bot):
    await bot.add_cog(ConfigCog(bot))