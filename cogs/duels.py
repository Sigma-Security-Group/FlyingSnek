from __future__ import annotations

import os, json
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands  # type: ignore

from constants import *

from __main__ import log, cogsReady, client


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
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True, view_channel=True),
            challenger: discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True, view_channel=True),
            opponent: discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True, view_channel=True),
            guild.get_role(SQUADRON_LEADER): discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True, view_channel=True),
            guild.get_role(UNIT_STAFF): discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True, view_channel=True),
            guild.get_role(SNEK_LORD): discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True, view_channel=True),
        }
        channelName = f"{challenger.display_name} vs {opponent.display_name} - {datetime.now(timezone.utc).strftime('%Y-%m-%d @ %H:%M:%S')}"
        channel = await interaction.guild.create_text_channel(channelName, category=self.bot.get_channel(DUELS_CATEGORY), overwrites=overwrites)
        
        view = discord.ui.View()
        
        view.add_item(DuelButton(label=f"{challenger.display_name} Wins", style=discord.ButtonStyle.green, custom_id=f"duelWin_{channel.id}_{challenger.id}_{opponent.id}_challenger"))
        view.add_item(DuelButton(label=f"{opponent.display_name} Wins", style=discord.ButtonStyle.green, custom_id=f"duelWin_{channel.id}_{challenger.id}_{opponent.id}_opponent"))
        view.add_item(DuelButton(label="Refuse challenge (-2pts)", style=discord.ButtonStyle.red, custom_id=f"duelRefused_{channel.id}_{challenger.id}_{opponent.id}_none"))
        view.add_item(DuelButton(label="Cancel challenge (only for legitimate use, no score change)", style=discord.ButtonStyle.blurple, custom_id=f"duelCancelled_{channel.id}_{challenger.id}_{opponent.id}_none"))
        
        await channel.send(view=view)
        await channel.send(f"{challenger.mention} vs {opponent.mention}")
        
        log.debug(f"Duel created: {challenger.display_name} ({challenger.id}) vs {opponent.display_name} ({opponent.id})")
        await interaction.response.send_message(f"Duel created: {channel.jump_url}")
    
async def buttonHandling(button: DuelButton, interaction: discord.Interaction) -> None:
    # sourcery skip: low-code-quality
    if not isinstance(interaction.user, discord.Member):
        log.exception("ButtonHandling: user not discord.Member")
        return
    
    try:
        action, channelId, challengerId, opponentId, winnerLbl = button.custom_id.split("_")
    except Exception:
        log.exception("ButtonHandling: invalid custom_id")
        return
    
    mainChannel = client.get_channel(THE_CHALLENGE_ROOM)
    channel = client.get_channel(int(channelId))
    challenger = channel.guild.get_member(int(challengerId))
    opponent = channel.guild.get_member(int(opponentId))
    if winnerLbl == "challenger":
        winner = challenger
        loser = opponent
    elif winnerLbl == "opponent":
        winner = opponent
        loser = challenger
    else:
        winner = None
        loser = None
    
    if action == "duelWin":
        await channel.send(f"{winner.display_name} wins!")
        log.debug(f"{winner.display_name} ({winner.id}) wins against {loser.display_name} ({loser.id})")
        await mainChannel.send(f"{winner.mention} wins against {loser.mention}")
        
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
            await winner.add_roles(mainChannel.guild.get_role(winnerNewRank))
        elif winnerNewRank != winnerRank:
            await winner.remove_roles(mainChannel.guild.get_role(winnerRank))
            await winner.add_roles(mainChannel.guild.get_role(winnerNewRank))
            await mainChannel.send(f"{winner.mention} is now {mainChannel.guild.get_role(winnerNewRank).name}!")
        
        if loserNewRank == loserRank == INITIATE:
            await loser.add_roles(mainChannel.guild.get_role(loserNewRank))
        elif loserNewRank != loserRank:
            await loser.remove_roles(mainChannel.guild.get_role(loserRank))
            await loser.add_roles(mainChannel.guild.get_role(loserNewRank))
            await mainChannel.send(f"{loser.mention} is now {mainChannel.guild.get_role(loserNewRank).name}!")
        
        with open(DUELS_HISTORY_FILE) as f:
            history = json.load(f)
        
        history.append({
            "challenger": challenger.id,
            "challengerName": challenger.display_name,
            "opponent": opponent.id,
            "opponentName": opponent.display_name,
            "accepted": True,
            "winner": winner.id,
            "pointsWon": pointsWon,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        with open(DUELS_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
        
        await channel.delete()
    
    elif action == "duelRefused":
        await channel.send("Challenge refused!")
        log.debug(f"Challenge refused by {interaction.user.display_name} ({interaction.user.id})")
        await mainChannel.send(f"{interaction.user.mention} refused a challenge")
        with open(SCORES_FILE) as f:
            scores = json.load(f)
        
        if str(interaction.user.id) not in scores:
            scores[str(interaction.user.id)] = 0
        
        refuserRank = RANKS_BY_SCORE[scores[str(interaction.user.id)]]
        
        scores[str(interaction.user.id)] = max(scores[str(interaction.user.id)] - 2, 0)
        
        refuserNewRank = RANKS_BY_SCORE[scores[str(interaction.user.id)]]
        
        with open(SCORES_FILE, "w") as f:
            json.dump(scores, f, indent=4)
        
        if refuserNewRank == refuserRank == INITIATE:
            await interaction.user.add_roles(mainChannel.guild.get_role(refuserNewRank))
        elif refuserNewRank != refuserRank:
            await interaction.user.remove_roles(mainChannel.guild.get_role(refuserRank))
            await interaction.user.add_roles(mainChannel.guild.get_role(refuserNewRank))
            await mainChannel.send(f"{interaction.user.mention} is now {mainChannel.guild.get_role(refuserNewRank).name}!")
        
        with open(DUELS_HISTORY_FILE) as f:
            history = json.load(f)
        
        history.append({
            "challenger": challenger.id,
            "challengerName": challenger.display_name,
            "opponent": opponent.id,
            "opponentName": opponent.display_name,
            "accepted": False,
            "winner": challenger.id if opponent.id == interaction.user.id else opponent.id if challenger.id == interaction.user.id else None,
            "pointsWon": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        with open(DUELS_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
        
        await channel.delete()
    
    elif action == "duelCancelled":
        await channel.send("Challenge cancelled!")
        log.debug(f"Challenge cancelled by {interaction.user.display_name} ({interaction.user.id})")
        await mainChannel.send(f"{interaction.user.mention} cancelled a challenge")
        
        await channel.delete()


class DuelButton(discord.ui.Button):
    """Handling all duel buttons."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        await buttonHandling(self, interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Duels(bot))
