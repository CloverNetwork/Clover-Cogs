import base64
import io
import re
import time

import discord
from discord.ext import tasks
from mcstatus import JavaServer
from redbot.core import Config, commands
from redbot.core.bot import Red

MC_CODE_PATTERN = re.compile(r"§([0-9a-fk-or])")

MC_COLOR_TO_ANSI = {
    "0": "30", "1": "34", "2": "32", "3": "36",
    "4": "31", "5": "35", "6": "33", "7": "37",
    "8": "1;30", "9": "1;34", "a": "1;32", "b": "1;36",
    "c": "1;31", "d": "1;35", "e": "1;33", "f": "1;37",
}
MC_FORMAT_TO_ANSI = {
    "l": "1",
    "n": "4",
}


def strip_mc_codes(text):
    return MC_CODE_PATTERN.sub("", text or "")


def mc_codes_to_ansi(text):
    if not text:
        return ""
    result = ""
    active = []
    last_end = 0
    for match in MC_CODE_PATTERN.finditer(text):
        result += text[last_end:match.start()]
        code = match.group(1)
        if code == "r":
            active = []
            result += "[0m"
        elif code in MC_COLOR_TO_ANSI:
            active = [MC_COLOR_TO_ANSI[code]]
            result += f"[0;{active[0]}m"
        elif code in MC_FORMAT_TO_ANSI:
            active.append(MC_FORMAT_TO_ANSI[code])
            result += f"[{';'.join(active)}m"
        last_end = match.end()
    result += text[last_end:]
    result += "[0m"
    return result


class MinecraftStatus(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=194902351, force_registration=True)
        self.config.register_guild(
            address=None,
            channel_id=None,
            message_id=None,
            interval=300,
            last_updated=0,
        )
        self.status_loop.start()

    def cog_unload(self):
        self.status_loop.cancel()

    @tasks.loop(seconds=60)
    async def status_loop(self):
        now = time.time()
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if not data.get("address") or not data.get("channel_id"):
                continue
            if now - data.get("last_updated", 0) < data.get("interval", 300):
                continue
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            await self.update_status(guild)

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_red_ready()

    async def fetch_status(self, address):
        loop = self.bot.loop
        server = await loop.run_in_executor(None, JavaServer.lookup, address)
        return await server.async_status()

    async def build_status_embed(self, address):
        try:
            status = await self.fetch_status(address)
        except Exception:
            embed = discord.Embed(
                title=f"🔴 {address}",
                description="Could not reach this server.",
                color=discord.Color.red(),
            )
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="Last checked")
            return embed, None

        motd_ansi = mc_codes_to_ansi(status.motd.to_minecraft())
        players = status.players
        player_value = f"{players.online}/{players.max}"
        if players.sample:
            names = [strip_mc_codes(p.name) for p in players.sample]
            shown = names[:10]
            extra = len(names) - len(shown)
            names_text = ", ".join(shown)
            if extra > 0:
                names_text += f", +{extra} more"
            player_value += f"\n{names_text}"

        embed = discord.Embed(
            title=f"🟢 {address}",
            description=f"```ansi\n{motd_ansi}\n```",
            color=discord.Color.green(),
        )
        embed.add_field(name="Players", value=player_value, inline=True)
        embed.add_field(
            name="Version",
            value=f"{status.version.name} (protocol {status.version.protocol})",
            inline=True,
        )
        embed.add_field(name="Latency", value=f"{status.latency:.0f} ms", inline=True)
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Last updated")

        file = None
        if status.icon:
            try:
                b64data = status.icon.split(",", 1)[1] if "," in status.icon else status.icon
                icon_bytes = base64.b64decode(b64data)
                file = discord.File(io.BytesIO(icon_bytes), filename="icon.png")
                embed.set_thumbnail(url="attachment://icon.png")
            except Exception:
                file = None
        return embed, file

    async def update_status(self, guild):
        data = await self.config.guild(guild).all()
        address = data["address"]
        channel_id = data["channel_id"]
        if not address or not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return

        embed, file = await self.build_status_embed(address)
        message = None
        if data["message_id"]:
            try:
                message = await channel.fetch_message(data["message_id"])
            except (discord.NotFound, discord.Forbidden):
                message = None

        if message:
            try:
                await message.edit(embed=embed, attachments=[file] if file else [])
            except discord.HTTPException:
                message = None

        if not message:
            if file:
                message = await channel.send(embed=embed, file=file)
            else:
                message = await channel.send(embed=embed)
            await self.config.guild(guild).message_id.set(message.id)

        await self.config.guild(guild).last_updated.set(time.time())

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def mcserver(self, ctx):
        await ctx.send_help()

    @mcserver.command(name="address")
    @commands.admin_or_permissions(manage_guild=True)
    async def mcserver_address(self, ctx, address: str):
        await self.config.guild(ctx.guild).address.set(address)
        await ctx.send(f"Minecraft server address set to `{address}`.")

    @mcserver.command(name="channel")
    @commands.admin_or_permissions(manage_guild=True)
    async def mcserver_channel(self, ctx, channel: discord.TextChannel = None):
        address = await self.config.guild(ctx.guild).address()
        if not address:
            await ctx.send("Set a server address first with `[p]mcserver address <ip>`.")
            return
        channel = channel or ctx.channel
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.config.guild(ctx.guild).message_id.set(None)
        await ctx.send(f"Status updates will be posted in {channel.mention}.")
        await self.update_status(ctx.guild)

    @mcserver.command(name="interval")
    @commands.admin_or_permissions(manage_guild=True)
    async def mcserver_interval(self, ctx, seconds: int):
        if seconds < 60:
            await ctx.send("Interval must be at least 60 seconds.")
            return
        await self.config.guild(ctx.guild).interval.set(seconds)
        await ctx.send(f"Update interval set to {seconds} seconds.")

    @mcserver.command(name="refresh")
    @commands.admin_or_permissions(manage_guild=True)
    async def mcserver_refresh(self, ctx):
        address = await self.config.guild(ctx.guild).address()
        if not address:
            await ctx.send("Set a server address first with `[p]mcserver address <ip>`.")
            return
        await self.update_status(ctx.guild)
        await ctx.send("Status updated.")

    @mcserver.command(name="stop")
    @commands.admin_or_permissions(manage_guild=True)
    async def mcserver_stop(self, ctx):
        await self.config.guild(ctx.guild).channel_id.set(None)
        await self.config.guild(ctx.guild).message_id.set(None)
        await ctx.send("Automatic status updates have been disabled.")

    @mcserver.command(name="status")
    async def mcserver_status(self, ctx, address: str = None):
        address = address or await self.config.guild(ctx.guild).address()
        if not address:
            await ctx.send("No server address configured. Provide one or set it with `[p]mcserver address <ip>`.")
            return
        embed, file = await self.build_status_embed(address)
        if file:
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)
