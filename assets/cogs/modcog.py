import discord
from discord.ext import commands
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "data.db")

def get_mute_role_id(guild_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT mute_role FROM mutes WHERE guild_id = ?", (str(guild_id),))
    result = cursor.fetchone()
    conn.close()
    return int(result[0]) if result and result[0] else None

def ensure_bans_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            guild_id TEXT,
            user_id TEXT,
            user_tag TEXT,
            reason TEXT,
            banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_modmail_channel_id(guild_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT modmail_channel FROM modmail WHERE guild_id = ?", (str(guild_id),))
    result = cursor.fetchone()
    conn.close()
    return int(result[0]) if result and result[0] else None

class ModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ensure_bans_table()

    @commands.hybrid_command(name="modmail", description="Send an anonymous message to the server moderators.")
    async def modmail(self, ctx, *, message: str):
        """User command to send an anonymous message to the modmail channel."""
        modmail_channel_id = get_modmail_channel_id(ctx.guild.id)
        if not modmail_channel_id:
            embed = discord.Embed(
                title="Modmail Not Set Up",
                description="Modmail is not set up for this server. Please ask an admin to use `/setmodmail <channel>`.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        channel = ctx.guild.get_channel(modmail_channel_id)
        if not channel:
            embed = discord.Embed(
                title="Modmail Channel Not Found",
                description="The configured modmail channel does not exist. Please ask an admin to set it up again.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="📬 New Anonymous Modmail",
            description=message,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Sent via Modmail | The sender's identity is hidden.")
        await channel.send(embed=embed)
        await ctx.send("Your anonymous message has been sent to the moderators.", ephemeral=True)

    @commands.hybrid_command(name="mute", description="Mute a member (prevents sending messages).")
    @commands.has_guild_permissions(manage_messages=True)
    @discord.app_commands.describe(
        member="The member to mute.",
        reason="Reason for muting."
    )
    async def mute(self, ctx, member: discord.Member, reason: str = "No reason provided"):
        mute_role_id = get_mute_role_id(ctx.guild.id)
        if not mute_role_id:
            embed = discord.Embed(
                title="Mute Role Not Set",
                description="Please set a mute role using `/setmuterole` before using this command.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            embed = discord.Embed(
                title="Mute Role Not Found",
                description="The mute role configured does not exist. Please set it again.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        try:
            await member.add_roles(mute_role, reason=reason)
            embed = discord.Embed(
                title="Member Muted",
                description=f"{member.mention} has been muted.\nReason: {reason}",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to mute {member.mention}: {e}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="unmute", description="Unmute a member.")
    @commands.has_guild_permissions(manage_messages=True)
    @discord.app_commands.describe(
        member="The member to unmute."
    )
    async def unmute(self, ctx, member: discord.Member):
        mute_role_id = get_mute_role_id(ctx.guild.id)
        if not mute_role_id:
            embed = discord.Embed(
                title="Mute Role Not Set",
                description="Please set a mute role using `/setmuterole` before using this command.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            embed = discord.Embed(
                title="Mute Role Not Found",
                description="The mute role configured does not exist. Please set it again.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        try:
            await member.remove_roles(mute_role, reason="Unmuted by moderator")
            embed = discord.Embed(
                title="Member Unmuted",
                description=f"{member.mention} has been unmuted.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to unmute {member.mention}: {e}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_guild_permissions(kick_members=True)
    @discord.app_commands.describe(
        member="The member to kick.",
        reason="Reason for kicking."
    )
    async def kick(self, ctx, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                title="Member Kicked",
                description=f"{member.mention} has been kicked.\nReason: {reason}",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to kick {member.mention}: {e}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.has_guild_permissions(ban_members=True)
    @discord.app_commands.describe(
        member="The member to ban.",
        reason="Reason for banning."
    )
    async def ban(self, ctx, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.ban(reason=reason)
            # Save to bans table
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO bans (guild_id, user_id, user_tag, reason) VALUES (?, ?, ?, ?)",
                (str(ctx.guild.id), str(member.id), f"{member.name}#{member.discriminator}", reason)
            )
            conn.commit()
            conn.close()
            embed = discord.Embed(
                title="Member Banned",
                description=f"{member.mention} has been banned.\nReason: {reason}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to ban {member.mention}: {e}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="unban", description="Unban a user by ID or username#discriminator.")
    @commands.has_guild_permissions(ban_members=True)
    @discord.app_commands.describe(
        user="The user to unban (ID or username#discriminator)."
    )
    async def unban(self, ctx, user: str):
        try:
            bans = await ctx.guild.bans()
            user_obj = None
            for ban_entry in bans:
                if (
                    str(ban_entry.user.id) == user
                    or f"{ban_entry.user.name}#{ban_entry.user.discriminator}" == user
                ):
                    user_obj = ban_entry.user
                    break
            if user_obj is None:
                embed = discord.Embed(
                    title="User Not Found",
                    description="Could not find a banned user with that ID or username.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            await ctx.guild.unban(user_obj)
            # Remove from bans table
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM bans WHERE guild_id = ? AND user_id = ?",
                (str(ctx.guild.id), str(user_obj.id))
            )
            conn.commit()
            conn.close()
            embed = discord.Embed(
                title="User Unbanned",
                description=f"{user_obj.mention} has been unbanned.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to unban user: {e}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ModCog(bot))