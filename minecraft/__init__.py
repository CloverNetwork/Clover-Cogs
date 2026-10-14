from .minecraft import MinecraftStatus


async def setup(bot):
    await bot.add_cog(MinecraftStatus(bot))
