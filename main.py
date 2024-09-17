import pickle
import time

import discord
from discord.ext import tasks
from discord.guild import Guild

import os
from dotenv import load_dotenv

load_dotenv()
my_token = os.getenv('discord_token')

delay_seconds = 30
matus_user_id = 0

#flag if commands have been pushed to servers
synced = 0

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.guilds = True

#bot = commands.Bot(command_prefix='/', intents=intents)

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

#open database
with open('servers.dump', 'rb') as f:
  servers = pickle.load(f)
server_data = {}


@tasks.loop(seconds=delay_seconds)
async def log_users():

  for server in bot.guilds:
    server_data = servers.get(server.id, {})
    timestamp = round(time.time())
    for member in server.members:
      if member.status == discord.Status.online \
      and not member.bot:
        server_data[member.id] = timestamp
    servers[server.id] = server_data

  with open('servers.dump', 'wb') as f:
    pickle.dump(servers, f)

@tasks.loop(seconds=5)
async def sync_commands():
  global synced
  if synced == 0:
    await tree.sync()
    synced = 1
    print('commands synced')
 
#list all offline users
@tree.command(
  name='last',
  description='List all offline users',
  guild=discord.Object(id=1222889416339751014)
)
async def last(interaction: discord.Interaction):
  server_data = servers.get(interaction.guild_id, {})
  response = ''
  
  #for offline users return their times and times
  for member in interaction.guild.members[:30]:
    if member.status == discord.Status.offline \
    and not member.bot:
      if len(response) > 0:
        response += '\n'

      if member.id in server_data:
        response += member.name + ' as ' + member.display_name + \
          ' was last seen on ' +\
          format_timestamp(servers[interaction.guild_id][member.id])
      else:
        response += member.name + ' as ' + member.display_name + ' was never seen'

  await interaction.response.send_message(response)


#reply with time of specified user
@tree.command(name='lastseen', description='When was user last seen')
async def lastseen(interaction: discord.Interaction, mention: str):
  server_data = servers.get(interaction.guild_id, {})
  id = int(mention.replace("<", "").replace(">", "").\
    replace("!", "").replace("@", "").replace("&", ""))
  #replace(/[<@!>]/g, '')
  member = await bot.fetch_user(id)

  member_time = time.time()
  if member.id in server_data:
    member_time = server_data[member.id]

  if member.bot:
    text = 'Bots are not tracked'
  elif member.id not in server_data:
    text = 'User not logged.'
  elif time.time() - member_time < delay_seconds:
    text = member.name + ' is online'
  else:
    text = member.name +" was last seen on " + \
    format_timestamp(member_time)
  await interaction.response.send_message(text)


#finish this command - add conversions
@tree.command(name='alloffline', description='See times of all offline users')
async def alloffline(ctx):
  server_data = servers.get(ctx.guild.id, {})
  print(server_data)


def format_timestamp(timestamp):
  return f"<t:{timestamp}:f>"


#sync command tree, when added to server
@bot.event
async def on_guild_join(guild: Guild):
  print('Added to server ' + str(guild.name))
  await tree.sync(guild=discord.Object(id=guild.id))
  await bot.change_presence(status=discord.Status.online)

@bot.event
async def on_guild_remove(guild: Guild):
  print('Removed from server ' + str(guild.name))

@bot.event
async def on_ready():
  print("Used on " + str(len(bot.guilds)) + " servers.")

  log_users.start()
  sync_commands.start()
  print("ready")


# @bot.event
# async def on_message(message):
#   print("incoming mesasge")
#   print(message.author)
#   if message.author != bot.user:
#     print(message.content)
#     #if message.content.startswith("/"):
#     match message.content[1:]:
#       case "ping":
#         await message.channel.send("Pong!")

bot.run(my_token)
