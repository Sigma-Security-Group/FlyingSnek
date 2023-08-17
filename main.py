import os, discord, asyncio

from logger import Logger
log = Logger()

import platform  # Set appropriate event loop policy to avoid runtime errors on windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from discord.ext import commands  # type: ignore

if not os.path.exists("./secret.py"):
    log.info("Creating a secret.py file!")
    with open("secret.py", "w") as f:
        f.write(  # Write secret.py template
            "TOKEN = \"{BOT_TOKEN_HERE}\""
        )
    exit()

import secret

from constants import *

if not os.path.exists("./data"):
    log.info("Creating a data directory!")
    os.mkdir("data")

COGS = [cog[:-3] for cog in os.listdir("cogs/") if cog.endswith(".py")]
# COGS = ["schedule"]  # DEBUG: Faster startup
cogsReady = {cog: False for cog in COGS}

INTENTS = discord.Intents.all()

class FriendlySnek(commands.Bot):
    """Friendly Snek bot."""
    def __init__(self, *, intents: discord.Intents) -> None:
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            activity=discord.Activity(  # 🐍
                type=discord.ActivityType.watching,
                name="the skies"
            ),
            status="online"
        )

    async def setup_hook(self) -> None:
        for cog in COGS:
            await client.load_extension(f"cogs.{cog}")
        self.tree.copy_global_to(guild=GUILD)  # This copies the global commands over to your guild.
        await self.tree.sync(guild=GUILD)

client = FriendlySnek(intents=INTENTS)
client.ready = False

@client.event
async def on_ready() -> None:
    while not all(cogsReady.values()):
        await asyncio.sleep(1)
    client.ready = True

    log.info(f"Bot Ready! Logged in as {client.user}.")
    
    ########################################################################################
    # For deleting all duel channels                                                       #
    # /!\ Only uncomment this if you know what you're doing                                #
    for channel in client.get_guild(GUILD_ID).channels:                                    #
        if channel.category_id == DUELS_CATEGORY.id and channel.id != THE_CHALLENGE_ROOM:  #
            await log.debug(f"Deleting channel {channel.name} ({channel.id})")             #
    ########################################################################################


@client.event
async def on_message(message: discord.Message) -> None:
    """On message client event."""
    if message.author.id == FLYING_SNEK:  # Ignore messages from itself
        return

    if message.guild is None or message.guild.id != GUILD_ID:  # Ignore messages that were not sent on the correct server
        return

    # Execute commands
    if message.content.startswith(COMMAND_PREFIX):
        log.debug(f"{message.author.display_name} ({message.author}) > {message.content}")
        message.content = message.content.lower()
        await client.process_commands(message)


@client.event
async def on_error(event, *args, **kwargs) -> None:
    """  """
    log.exception(f"An error occured! {event}")


@client.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    """  """
    errorType = type(error)
    if errorType is commands.errors.MissingRequiredArgument:
        await ctx.send_help(ctx.command)
    elif errorType is not commands.CommandNotFound:
        log.exception(f"{ctx.author} | {error}")


@client.command()
async def reload(ctx: commands.Context) -> None:
    """ Reload bot cogs - Devs only. """
    log.info(f"{ctx.author.display_name} ({ctx.author}) Reloading bot cogs...")
    if ctx.author.id not in DEVELOPERS:
        return
    for cog in COGS:
        await client.reload_extension(f"cogs.{cog}")
    await client.tree.sync(guild=GUILD)
    await ctx.send("Cogs reloaded!")


@client.command()
async def stop(ctx: commands.Context) -> None:
    """ Stops bot - Devs only. """
    if ctx.author.id not in DEVELOPERS:
        return
    await client.close()


if __name__ == "__main__":
    try:
        client.run(secret.TOKEN)
        log.info("Bot stopped!")
    except Exception as e:
        log.exception(e)
