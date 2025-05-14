import discord
from discord.ext import commands

class YGOCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {guild_id: {game_id: {"players": {user_id: {"life": int, "active": bool}}, "active": bool, "owner": user_id, "lobby": bool}}}
        self.games = {}
        # {guild_id: {user_id: game_id}}
        self.player_games = {}

    def get_next_game_id(self, guild_id):
        if guild_id not in self.games or not self.games[guild_id]:
            return 1
        return max(self.games[guild_id].keys()) + 1

    def get_player_game(self, guild_id, user_id):
        return self.player_games.get(guild_id, {}).get(user_id)

    def cleanup_game(self, guild_id, game_id):
        # Remove game from games dict
        if guild_id in self.games and game_id in self.games[guild_id]:
            del self.games[guild_id][game_id]
            # If no more games, remove the guild entry
            if not self.games[guild_id]:
                del self.games[guild_id]
        # Remove all player references to this game
        if guild_id in self.player_games:
            to_remove = [uid for uid, gid in self.player_games[guild_id].items() if gid == game_id]
            for uid in to_remove:
                del self.player_games[guild_id][uid]
            # If no more player refs, remove the guild entry
            if not self.player_games[guild_id]:
                del self.player_games[guild_id]

    @commands.hybrid_command(name="ygostart", description="Create or join a Yu-Gi-Oh! duel lobby (2 or 4 players).")
    @discord.app_commands.describe(
        players="Number of players (2 for single duel, 4 for tag duel)"
    )
    async def ygostart(self, ctx, players: int = 2):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        if players not in [2, 4]:
            embed = discord.Embed(
                title="Invalid Player Count",
                description="Please choose 2 (single duel) or 4 (tag duel) players.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Check if user is already in a game or lobby
        if guild_id in self.player_games and user_id in self.player_games[guild_id]:
            game_id = self.player_games[guild_id][user_id]
            embed = discord.Embed(
                title="Already in a Game or Lobby",
                description=f"You are already in Game {game_id}. You must leave or wait for it to end before joining/starting another.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return

        # Find an open lobby for this player count
        open_lobby_id = None
        if guild_id in self.games:
            for gid, game in self.games[guild_id].items():
                if game.get("lobby", False) and len(game["players"]) < players:
                    open_lobby_id = gid
                    break

        if open_lobby_id is not None:
            # Join the open lobby
            game = self.games[guild_id][open_lobby_id]
            game["players"][user_id] = {"life": 8000, "active": True}
            self.player_games[guild_id][user_id] = open_lobby_id

            # If lobby is now full, start the game
            if len(game["players"]) == players:
                game["active"] = True
                game["lobby"] = False
                embed = discord.Embed(
                    title=f"Yu-Gi-Oh! Game {open_lobby_id} Started",
                    description=f"Players: {', '.join(ctx.guild.get_member(pid).mention for pid in game['players'])}",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                first = self.pick_first_player(ctx, game)
                if first:
                    await ctx.send(f"🎲 {first.mention} goes first!")
                await self.show_game_life_totals(ctx, guild_id, open_lobby_id)
            else:
                embed = discord.Embed(
                    title=f"Joined Lobby for Game {open_lobby_id}",
                    description=f"Waiting for more players... ({len(game['players'])}/{players})",
                    color=discord.Color.blurple()
                )
                await ctx.send(embed=embed)
            return

        # No open lobby, create a new one
        if guild_id not in self.games:
            self.games[guild_id] = {}
        if guild_id not in self.player_games:
            self.player_games[guild_id] = {}

        game_id = self.get_next_game_id(guild_id)
        players_dict = {user_id: {"life": 8000, "active": True}}

        self.games[guild_id][game_id] = {
            "players": players_dict,
            "active": False,
            "owner": user_id,
            "lobby": True,
            "max_players": players
        }
        self.player_games[guild_id][user_id] = game_id

        embed = discord.Embed(
            title=f"Lobby Created for Game {game_id}",
            description=f"Waiting for more players... (1/{players})\nAnother player must use `/ygostart players:{players}` to join.",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ygojoin", description="Join an open Yu-Gi-Oh! lobby by Game ID.")
    @discord.app_commands.describe(
        game_id="Game ID of the lobby you want to join"
    )
    async def ygojoin(self, ctx, game_id: int):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # Check if user is already in a game or lobby
        if guild_id in self.player_games and user_id in self.player_games[guild_id]:
            embed = discord.Embed(
                title="Already in a Game or Lobby",
                description="You must leave or wait for your current game to end before joining another.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return

        if guild_id not in self.games or game_id not in self.games[guild_id]:
            embed = discord.Embed(
                title="Lobby Not Found",
                description=f"Game {game_id} does not exist.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        game = self.games[guild_id][game_id]
        if not game.get("lobby", False):
            embed = discord.Embed(
                title="Not a Lobby",
                description="This game is already in progress or finished.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        max_players = game.get("max_players", 2)
        if len(game["players"]) >= max_players:
            embed = discord.Embed(
                title="Lobby Full",
                description="This lobby is already full.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Add player to lobby
        game["players"][user_id] = {"life": 8000, "active": True}
        self.player_games[guild_id][user_id] = game_id

        # If lobby is now full, start the game
        if len(game["players"]) == max_players:
            game["active"] = True
            game["lobby"] = False
            embed = discord.Embed(
                title=f"Yu-Gi-Oh! Game {game_id} Started",
                description=f"Players: {', '.join(ctx.guild.get_member(pid).mention for pid in game['players'])}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            first = self.pick_first_player(ctx, game)
            if first:
                await ctx.send(f"🎲 {first.mention} goes first!")
            await self.show_game_life_totals(ctx, guild_id, game_id)
        else:
            embed = discord.Embed(
                title=f"Joined Lobby for Game {game_id}",
                description=f"Waiting for more players... ({len(game['players'])}/{max_players})",
                color=discord.Color.blurple()
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="ygolife", description="View or update your life total in your current game, or view any game's stats.")
    @discord.app_commands.describe(
        amount="Amount to add/subtract (optional, e.g. -2000 or 500). Leave blank to just view.",
        game_id="Game ID to view (optional, shows stats for that game if provided)"
    )
    async def ygolife(self, ctx, amount: int = None, game_id: int = None):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # If game_id is provided, show stats for that game (view only)
        if game_id is not None:
            if guild_id not in self.games or game_id not in self.games[guild_id]:
                embed = discord.Embed(
                    title="Game Not Found",
                    description=f"Game {game_id} does not exist.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            game = self.games[guild_id][game_id]
            await self.show_game_life_totals(ctx, guild_id, game_id)
            return

        # Otherwise, default to user's current game (update/view)
        game_id = self.get_player_game(guild_id, user_id)
        if (
            not game_id
            or guild_id not in self.games
            or game_id not in self.games[guild_id]
        ):
            embed = discord.Embed(
                title="No Game Running",
                description="You are not in an active game. Start one with `/ygostart`.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        game = self.games[guild_id][game_id]
        if user_id not in game["players"]:
            # Clean up stale mapping if present
            if guild_id in self.player_games and user_id in self.player_games[guild_id]:
                del self.player_games[guild_id][user_id]
                if not self.player_games[guild_id]:
                    del self.player_games[guild_id]
            embed = discord.Embed(
                title="No Game Running",
                description="You are not in an active game. Start one with `/ygostart`.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        player = game["players"][user_id]

        if amount is not None:
            player["life"] += amount
            if player["life"] <= 0:
                player["active"] = False
                embed = discord.Embed(
                    title="Player Eliminated",
                    description=f"{ctx.author.mention} has lost all their life points and is eliminated!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                # Check if only one player remains
                active_players = [uid for uid, pdata in game["players"].items() if pdata["active"]]
                if len(active_players) == 1:
                    winner = ctx.guild.get_member(active_players[0])
                    game["active"] = False
                    win_embed = discord.Embed(
                        title="Game Over",
                        description=f"{winner.mention} is the last duelist standing and wins the game!",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=win_embed)
                    self.cleanup_game(guild_id, game_id)
                    return  # <--- Prevent further code from running after cleanup
                await self.show_game_life_totals(ctx, guild_id, game_id)
                return
        await self.show_game_life_totals(ctx, guild_id, game_id)

    async def show_game_life_totals(self, ctx, guild_id, game_id):
        game = self.games[guild_id][game_id]
        embed = discord.Embed(
            title=f"Yu-Gi-Oh! Game {game_id} Life Totals",
            color=discord.Color.blurple()
        )
        for pid, pdata in game["players"].items():
            member = ctx.guild.get_member(pid)
            status = "Active" if pdata.get("active", True) else "Eliminated"
            value = f"Life: **{pdata['life']}**\nStatus: **{status}**"
            embed.add_field(name=member.display_name if member else str(pid), value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ygolobbies", description="List all Yu-Gi-Oh! lobbies and active games in this server.")
    async def ygolobbies(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.games or not self.games[guild_id]:
            embed = discord.Embed(
                title="No Lobbies or Games",
                description="There are currently no lobbies or active games.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="Yu-Gi-Oh! Lobbies & Active Games",
            color=discord.Color.blurple()
        )
        found = False
        for game_id, game in self.games[guild_id].items():
            players = [ctx.guild.get_member(pid).mention for pid in game["players"]]
            max_players = game.get("max_players", 2)
            if game.get("lobby", False):
                status = f"Lobby (waiting: {len(players)}/{max_players})"
            elif game.get("active", False):
                status = "Active Game"
            else:
                status = "Finished"
            embed.add_field(
                name=f"Game {game_id}",
                value=f"Players: {', '.join(players)}\nStatus: {status}",
                inline=False
            )
            found = True
        if not found:
            embed.description = "There are currently no lobbies or active games."
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ygoleave", description="Leave a Yu-Gi-Oh! lobby you have joined but hasn't started yet.")
    async def ygoleave(self, ctx):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # Check if user is in a game/lobby
        game_id = self.get_player_game(guild_id, user_id)
        if not game_id or guild_id not in self.games or game_id not in self.games[guild_id]:
            embed = discord.Embed(
                title="Not in a Lobby",
                description="You are not currently in any lobby.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        game = self.games[guild_id][game_id]
        if not game.get("lobby", False):
            embed = discord.Embed(
                title="Game Already Started",
                description="You cannot leave a game that has already started. Use `/ygosurrender` to forfeit instead.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Remove player from lobby
        if user_id in game["players"]:
            del game["players"][user_id]
        if user_id in self.player_games[guild_id]:
            del self.player_games[guild_id][user_id]

        embed = discord.Embed(
            title="Left Lobby",
            description=f"{ctx.author.mention} has left the lobby for Game {game_id}.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        # If lobby is empty, delete it
        if not game["players"]:
            del self.games[guild_id][game_id]

    @commands.hybrid_command(name="ygoforcestart", description="Force start a lobby before max players are reached (owner only).")
    @discord.app_commands.describe(
        game_id="Game ID of the lobby you want to start (optional, defaults to your current lobby)"
    )
    async def ygoforcestart(self, ctx, game_id: int = None):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # Determine which lobby to start
        if game_id is None:
            game_id = self.get_player_game(guild_id, user_id)
        if not game_id or guild_id not in self.games or game_id not in self.games[guild_id]:
            embed = discord.Embed(
                title="Lobby Not Found",
                description="You are not in a lobby or the lobby does not exist.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        game = self.games[guild_id][game_id]
        if not game.get("lobby", False):
            embed = discord.Embed(
                title="Game Already Started",
                description="This game has already started.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Only the owner can force start
        if game.get("owner") != user_id:
            embed = discord.Embed(
                title="Not Lobby Owner",
                description="Only the player who created the lobby can force start it.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Start the game
        game["active"] = True
        game["lobby"] = False
        embed = discord.Embed(
            title=f"Yu-Gi-Oh! Game {game_id} Started (Forced)",
            description=f"Players: {', '.join(ctx.guild.get_member(pid).mention for pid in game['players'])}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        first = self.pick_first_player(ctx, game)
        if first:
            await ctx.send(f"🎲 {first.mention} goes first!")
        await self.show_game_life_totals(ctx, guild_id, game_id)

    @commands.hybrid_command(name="ygosurrender", description="Forfeit the current Yu-Gi-Oh! game (you will be eliminated).")
    async def ygosurrender(self, ctx):
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        game_id = self.get_player_game(guild_id, user_id)
        if not game_id or guild_id not in self.games or game_id not in self.games[guild_id]:
            embed = discord.Embed(
                title="No Game Running",
                description="There is no active game to forfeit.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        game = self.games[guild_id][game_id]
        if not game["active"] or user_id not in game["players"] or not game["players"][user_id]["active"]:
            embed = discord.Embed(
                title="No Game Running",
                description="There is no active game to forfeit.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        game["players"][user_id]["active"] = False
        embed = discord.Embed(
            title="Player Forfeited",
            description=f"{ctx.author.mention} has forfeited and is eliminated from the game.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        # Check if only one player remains
        active_players = [uid for uid, pdata in game["players"].items() if pdata["active"]]
        if len(active_players) == 1:
            winner = ctx.guild.get_member(active_players[0])
            game["active"] = False
            win_embed = discord.Embed(
                title="Game Over",
                description=f"{winner.mention} is the last duelist standing and wins the game!",
                color=discord.Color.green()
            )
            await ctx.send(embed=win_embed)
            self.cleanup_game(guild_id, game_id)

    def pick_first_player(self, ctx, game):
        player_ids = list(game["players"].keys())
        if not player_ids:
            return None
        import random
        first_id = random.choice(player_ids)
        member = ctx.guild.get_member(first_id)
        return member

async def setup(bot):
    await bot.add_cog(YGOCog(bot))