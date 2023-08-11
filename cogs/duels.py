import os, json
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands  # type: ignore

from constants import *

from __main__ import log, cogsReady


class Duels(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        if not os.path.exists(SCORES_FILE):
            with open(SCORES_FILE, "w") as f:
                json.dump({}, f)
        if not os.path.exists(DUELS_HISTORY_FILE):
            with open(DUELS_HISTORY_FILE, "w") as f:
                json.dump([], f)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.debug("Cog ready: Duels", flush=True)
        cogsReady["duels"] = True

    @app_commands.command(name="challenge", description="Challenge a user to a duel")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        opponent="Opponent to challenge to a duel",
        challenger="Challenger to challenge the opponent to a duel (defaults to the user who invoked the command)"
    )
    async def challenge(self, interaction: discord.Interaction, opponent: discord.Member, challenger: discord.Member = None) -> None:
        """Challenge a user to a duel"""
        if interaction.channel.id != THE_CHALLENGE_ROOM:
            channel = self.bot.get_channel(THE_CHALLENGE_ROOM)
            await interaction.response.send_message(f"This command can only be used in {channel.jump_url}", ephemeral=True)
            return
        
        if challenger is None:
            challenger = interaction.user

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            challenger: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            opponent: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.get_role(SQUADRON_LEADER): discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.get_role(UNIT_STAFF): discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.get_role(SNEK_LORD): discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        channelName = f"{challenger.display_name} vs {opponent.display_name} - {datetime.now(timezone.utc).strftime('%Y-%m-%d @ %H:%M:%S')}"
        channel = await interaction.guild.create_text_channel(channelName, category=self.bot.get_channel(DUELS_CATEGORY), overwrites=overwrites)
        
        view = DuelView()
        view.challengerWins.label = f"{challenger.display_name} Wins"
        view.challenger = challenger
        view.opponentWins.label = f"{opponent.display_name} Wins"
        view.opponent = opponent
        view.mainChannel = interaction.channel
        view.channel = channel
        await channel.send(view=view)
        await channel.send(f"{challenger.mention} vs {opponent.mention}")
        
        log.debug(f"Duel created: {challenger.display_name} ({challenger.id}) vs {opponent.display_name} ({opponent.id})")
        await interaction.response.send_message(f"Duel created: {channel.jump_url}")


class DuelView(discord.ui.View):
    mainChannel: discord.TextChannel = None
    channel: discord.TextChannel = None
    challenger: discord.Member = None
    opponent: discord.Member = None
    
    @discord.ui.button(label="Challenger Wins", style=discord.ButtonStyle.green)
    async def challengerWins(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(f"{self.challenger.display_name} wins!", ephemeral=True)
        await self.handleWin(self.challenger, self.opponent)
    
    @discord.ui.button(label="Opponent Wins", style=discord.ButtonStyle.green)
    async def opponentWins(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(f"{self.opponent.display_name} wins!", ephemeral=True)
        await self.handleWin(self.opponent, self.challenger)
    
    @discord.ui.button(label="Refuse challenge (-2pts)", style=discord.ButtonStyle.red)
    async def challengeRefused(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Challenge refused!", ephemeral=True)
        await self.handleRefusal(interaction.user)
    
    @discord.ui.button(label="Cancel challenge (only for legitimate use, no score change)", style=discord.ButtonStyle.blurple)
    async def challengeCancelled(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Challenge cancelled!", ephemeral=True)
        
        log.debug(f"Challenge cancelled by {interaction.user.display_name} ({interaction.user.id})")
        await self.mainChannel.send(f"{interaction.user.mention} cancelled a challenge")
        
        await self.channel.delete()
    
    async def handleWin(self, winner: discord.Member, loser: discord.Member) -> None:
        log.debug(f"{winner.display_name} ({winner.id}) wins against {loser.display_name} ({loser.id})")
        await self.mainChannel.send(f"{winner.mention} wins against {loser.mention}")
        
        with open(SCORES_FILE) as f:
            scores = json.load(f)
        
        if str(winner.id) not in scores:
            scores[str(winner.id)] = 0
        if str(loser.id) not in scores:
            scores[str(loser.id)] = 0
        
        # 1 point per win + 1 extra point per rank above
        pointsWon = 1 + max(0, (max(0, scores[str(loser.id)] - 1) // 5) - (max(0, scores[str(winner.id)] - 1) // 5))
        
        winnerRank = RANKS_BY_SCORE[scores[str(winner.id)]]
        loserRank = RANKS_BY_SCORE[scores[str(loser.id)]]
        
        scores[str(winner.id)] = min(max(scores[str(winner.id)] + pointsWon, 0), 30)
        scores[str(loser.id)] = max(scores[str(loser.id)] - 1, 0)
        
        winnerNewRank = RANKS_BY_SCORE[scores[str(winner.id)]]
        loserNewRank = RANKS_BY_SCORE[scores[str(loser.id)]]
        
        with open(SCORES_FILE, "w") as f:
            json.dump(scores, f, indent=4)
        
        if winnerNewRank == winnerRank == INITIATE:
            await winner.add_roles(self.mainChannel.guild.get_role(winnerNewRank))
        elif winnerNewRank != winnerRank:
            await winner.remove_roles(self.mainChannel.guild.get_role(winnerRank))
            await winner.add_roles(self.mainChannel.guild.get_role(winnerNewRank))
            await self.mainChannel.send(f"{winner.mention} is now {self.mainChannel.guild.get_role(winnerNewRank).name}!")
        
        if loserNewRank == loserRank == INITIATE:
            await loser.add_roles(self.mainChannel.guild.get_role(loserNewRank))
        elif loserNewRank != loserRank:
            await loser.remove_roles(self.mainChannel.guild.get_role(loserRank))
            await loser.add_roles(self.mainChannel.guild.get_role(loserNewRank))
            await self.mainChannel.send(f"{loser.mention} is now {self.mainChannel.guild.get_role(loserNewRank).name}!")
        
        with open(DUELS_HISTORY_FILE) as f:
            history = json.load(f)
        
        history.append({
            "challenger": self.challenger.id,
            "challengerName": self.challenger.display_name,
            "opponent": self.opponent.id,
            "opponentName": self.opponent.display_name,
            "accepted": True,
            "winner": winner.id,
            "pointsWon": pointsWon,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        with open(DUELS_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
        
        await self.channel.delete()
    
    async def handleRefusal(self, refuser: discord.Member) -> None:
        log.debug(f"Challenge refused by {refuser.display_name} ({refuser.id})")
        await self.mainChannel.send(f"{refuser.mention} refused a challenge")
        with open(SCORES_FILE) as f:
            scores = json.load(f)
        
        if str(refuser.id) not in scores:
            scores[str(refuser.id)] = 0
        
        refuserRank = RANKS_BY_SCORE[scores[str(refuser.id)]]
        
        scores[str(refuser.id)] = max(scores[str(refuser.id)] - 2, 0)
        
        refuserNewRank = RANKS_BY_SCORE[scores[str(refuser.id)]]
        
        with open(SCORES_FILE, "w") as f:
            json.dump(scores, f, indent=4)
        
        if refuserNewRank == refuserRank == INITIATE:
            await refuser.add_roles(self.mainChannel.guild.get_role(refuserNewRank))
        elif refuserNewRank != refuserRank:
            await refuser.remove_roles(self.mainChannel.guild.get_role(refuserRank))
            await refuser.add_roles(self.mainChannel.guild.get_role(refuserNewRank))
            await self.mainChannel.send(f"{refuser.mention} is now {self.mainChannel.guild.get_role(refuserNewRank).name}!")
        
        with open(DUELS_HISTORY_FILE) as f:
            history = json.load(f)
        
        history.append({
            "challenger": self.challenger.id,
            "challengerName": self.challenger.display_name,
            "opponent": self.opponent.id,
            "opponentName": self.opponent.display_name,
            "accepted": False,
            "winner": self.challenger.id if self.opponent.id == refuser.id else self.opponent.id if self.challenger.id == refuser.id else None,
            "pointsWon": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        with open(DUELS_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
        
        await self.channel.delete()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Duels(bot))
