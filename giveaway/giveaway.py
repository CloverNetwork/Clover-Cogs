import random
import re
import time

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red

GIVEAWAY_EMOJI = "🎉"
DURATION_PATTERN = re.compile(
    r"^(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?$"
)


def parse_duration(duration: str):
    match = DURATION_PATTERN.fullmatch(duration.strip())
    if not match or not any(match.groupdict().values()):
        return None
    parts = {k: int(v) for k, v in match.groupdict().items() if v}
    seconds = (
        parts.get("days", 0) * 86400
        + parts.get("hours", 0) * 3600
        + parts.get("minutes", 0) * 60
        + parts.get("seconds", 0)
    )
    return seconds if seconds > 0 else None


class Giveaway(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1837412095, force_registration=True)
        self.config.register_guild(giveaways={})
        self.giveaway_loop.start()

    def cog_unload(self):
        self.giveaway_loop.cancel()

    @tasks.loop(seconds=15)
    async def giveaway_loop(self):
        now = time.time()
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            for message_id, info in data.get("giveaways", {}).items():
                if not info["ended"] and info["end_time"] <= now:
                    await self.end_giveaway(guild, int(message_id))

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_red_ready()

    def build_embed(self, prize, winners, end_time, host, ended=False, winner_mentions=None):
        if ended:
            embed = discord.Embed(
                title=f"🎉 Giveaway Ended: {prize}",
                description=(
                    f"Winners: {winner_mentions or 'No valid entries.'}\n"
                    f"Hosted by {host.mention}"
                ),
                color=discord.Color.red(),
            )
        else:
            embed = discord.Embed(
                title=f"🎉 Giveaway: {prize}",
                description=(
                    f"React with {GIVEAWAY_EMOJI} to enter!\n"
                    f"Winners: **{winners}**\n"
                    f"Ends: <t:{int(end_time)}:R>\n"
                    f"Hosted by {host.mention}"
                ),
                color=discord.Color.gold(),
            )
        return embed

    async def get_entrants(self, channel, message_id):
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return None, []
        for reaction in message.reactions:
            if str(reaction.emoji) == GIVEAWAY_EMOJI:
                return message, [user async for user in reaction.users() if not user.bot]
        return message, []

    async def end_giveaway(self, guild, message_id):
        async with self.config.guild(guild).giveaways() as giveaways:
            info = giveaways.get(str(message_id))
            if not info or info["ended"]:
                return
            info["ended"] = True

        channel = guild.get_channel(info["channel_id"])
        if channel is None:
            return

        message, entrants = await self.get_entrants(channel, message_id)
        host = guild.get_member(info["host_id"]) or guild.me
        winner_count = min(info["winners"], len(entrants))
        winners = random.sample(entrants, winner_count) if winner_count else []
        winner_mentions = ", ".join(w.mention for w in winners) if winners else None

        if message:
            embed = self.build_embed(
                info["prize"], info["winners"], info["end_time"], host,
                ended=True, winner_mentions=winner_mentions,
            )
            await message.edit(embed=embed)
            if winners:
                await channel.send(
                    f"🎉 Congratulations {winner_mentions}! You won **{info['prize']}**!",
                    reference=message,
                )
            else:
                await channel.send(f"No valid entries for **{info['prize']}**, no winner could be determined.")

        async with self.config.guild(guild).giveaways() as giveaways:
            if str(message_id) in giveaways:
                giveaways[str(message_id)]["winner_ids"] = [w.id for w in winners]

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def giveaway(self, ctx):
        await ctx.send_help()

    @giveaway.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send("Invalid duration. Use a format like `1d2h30m`, `45m`, or `30s`.")
            return
        if winners < 1:
            await ctx.send("Number of winners must be at least 1.")
            return

        end_time = time.time() + seconds
        embed = self.build_embed(prize, winners, end_time, ctx.author)
        message = await ctx.send(embed=embed)
        await message.add_reaction(GIVEAWAY_EMOJI)

        async with self.config.guild(ctx.guild).giveaways() as giveaways:
            giveaways[str(message.id)] = {
                "channel_id": ctx.channel.id,
                "host_id": ctx.author.id,
                "prize": prize,
                "winners": winners,
                "end_time": end_time,
                "ended": False,
                "winner_ids": [],
            }

    @giveaway.command(name="end")
    @commands.admin_or_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message_id: int):
        giveaways = await self.config.guild(ctx.guild).giveaways()
        info = giveaways.get(str(message_id))
        if not info:
            await ctx.send("No giveaway found with that message ID.")
            return
        if info["ended"]:
            await ctx.send("That giveaway has already ended.")
            return
        await self.end_giveaway(ctx.guild, message_id)
        await ctx.send("Giveaway ended.")

    @giveaway.command(name="reroll")
    @commands.admin_or_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx, message_id: int, winners: int = 1):
        giveaways = await self.config.guild(ctx.guild).giveaways()
        info = giveaways.get(str(message_id))
        if not info:
            await ctx.send("No giveaway found with that message ID.")
            return
        if not info["ended"]:
            await ctx.send("That giveaway has not ended yet.")
            return

        channel = ctx.guild.get_channel(info["channel_id"])
        if channel is None:
            await ctx.send("The original channel no longer exists.")
            return

        _, entrants = await self.get_entrants(channel, message_id)
        if not entrants:
            await ctx.send("There are no entrants to reroll from.")
            return

        winner_count = min(winners, len(entrants))
        new_winners = random.sample(entrants, winner_count)
        mentions = ", ".join(w.mention for w in new_winners)
        await ctx.send(f"🎉 New winner(s) for **{info['prize']}**: {mentions}!")

        async with self.config.guild(ctx.guild).giveaways() as giveaways:
            giveaways[str(message_id)]["winner_ids"] = [w.id for w in new_winners]

    @giveaway.command(name="list")
    async def giveaway_list(self, ctx):
        giveaways = await self.config.guild(ctx.guild).giveaways()
        active = {mid: info for mid, info in giveaways.items() if not info["ended"]}
        if not active:
            await ctx.send("There are no active giveaways in this server.")
            return

        embed = discord.Embed(title="Active Giveaways", color=discord.Color.gold())
        for message_id, info in active.items():
            channel = ctx.guild.get_channel(info["channel_id"])
            channel_mention = channel.mention if channel else "unknown channel"
            embed.add_field(
                name=info["prize"],
                value=f"Channel: {channel_mention}\nEnds: <t:{int(info['end_time'])}:R>\nMessage ID: {message_id}",
                inline=False,
            )
        await ctx.send(embed=embed)
