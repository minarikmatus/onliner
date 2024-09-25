import dateparser
import pickle
#import re
import time

from datetime import datetime

import discord
from discord.ext import tasks
from discord.guild import Guild

import os
from dotenv import load_dotenv

DISCORD_MESSAGE_LEN_LIMIT = 2000


# function to cut riws to Discord max message length, keeping rows complete
def cut_rows(text):
  text += '\n'
  if len(text) > DISCORD_MESSAGE_LEN_LIMIT:
    text = text[:DISCORD_MESSAGE_LEN_LIMIT]
  return text[:text.rfind('\n')]

load_dotenv()
bot_token = os.getenv('discord_token', None)

if not bot_token:
  message = (
      "Couldn't find the `bot_token` environment variable."
      "Make sure to add it to your `.env` file like this: `discord_token=value_of_your_bot_token`"
  )
  raise ValueError(message)

database_path = 'servers.dump'

delay_seconds = 30
matus_user_id = 0

#flag if commands have been pushed to servers
synced = 0

intents = discord.Intents.default()
intents.guilds = True
#intents.message_content = True  #for on_message

#Privileged Intents (Needs to be enabled on developer portal of Discord)
intents.members = True
intents.presences = True

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

server_data = {}
servers = {}

#open database
if not os.path.exists(database_path):
  with open(database_path, 'wb') as f:
    pickle.dump(servers, f)

with open(database_path, 'rb') as f:
  servers = pickle.load(f)


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

  with open(database_path, 'wb') as f:
    pickle.dump(servers, f)


@tasks.loop(seconds=5)
async def sync_commands():
  global synced
  if synced == 0:
    await tree.sync()
    synced = 1
    print('commands synced')
 

def format_timestamp(timestamp):
  return f'<t:{timestamp}:f>'


async def get_channel_users(interaction:discord.Interaction) -> list[str]:
  channel = interaction.channel
  # Check if the channel is a text channel
  if isinstance(channel, discord.TextChannel):
    # Fetch all members in the guild, filter bots and readers
    members = list(member.display_name for member in channel.guild.members if not member.bot and channel.permissions_for(member).read_messages)
  
  elif isinstance(channel, discord.Thread):
    thread_members = await channel.fetch_members()
    members = []
    for member in thread_members:
      id = member.id
      member = await bot.fetch_user(id)
      if not member.bot:
        members.append(member.display_name)
  else:
    return []
  return members


#show who is here
@tree.command(
  name = 'here',
  description = 'List memebers of this channel or thread'
)
async def here(interaction: discord.Interaction):
  channel = interaction.channel

  # Check if the channel is a text channel
  if isinstance(channel, discord.TextChannel) \
    or isinstance(channel, discord.Thread):
   
    members = await get_channel_users(interaction=interaction)
    print(members)
  else:
    await interaction.response.send_message('This command can only be used in text channels and their threads.', ephemeral=True)
    return

  if len(members) > 0:
    members.sort()
    response = '\n'.join(members)
    response = cut_rows(response)
    await interaction.response.send_message(response, ephemeral=True)
  else: 
    #should only happen on debug
    response = 'No members fetched.'
    await interaction.response.send_message(response, ephemeral=True)


#list all offline users
@tree.command(
  name = 'last',
  description = 'List all offline users (that fit in one discord message)'
)
async def last(interaction: discord.Interaction, offset: int = 0):
  server_data = servers.get(interaction.guild_id, {})
  
  output_data = []
  #for offline users return their times and times
  for member in interaction.guild.members: # type: ignore
    if member.status == discord.Status.offline \
    and not member.bot:
      if member.id in server_data:
        output_data.append(
          member.display_name + ' (' + member.name + \
          ') was last seen on ' +\
          format_timestamp(servers[interaction.guild_id][member.id]) + '.'
        )
      else:
        output_data.append(
          member.display_name + ' (' + member.name + \
          ') was never seen.'
        )
        
  output_data.sort()
  response = '\n'.join(output_data[offset:])
  response = cut_rows(response)

  await interaction.response.send_message(response, ephemeral=True)


#reply with time of specified user
@tree.command(
  name = 'lastseen',
  description = 'When was user last seen online'
)
async def lastseen(interaction: discord.Interaction, mention: discord.Member):
  server_data = servers.get(interaction.guild_id, {})
  
  # try:
  #   id = int(re.sub('[<>&@!]', '', mention))
  # except Exception as e:
  #   text = 'User not found.'
  #   await interaction.response.send_message(text, ephemeral=True)
  #   return

  member_time = time.time()
  if mention.id in server_data:
    member_time = server_data[mention.id]

  if mention.bot:
    text = 'Bots are not watched.'
  elif mention.id not in server_data:
    text = mention.display_name + ' was never seen online.'
  elif time.time() - member_time < delay_seconds:
    text = mention.display_name + ' is online.'
  else:
    text = mention.display_name + ' was last seen on ' + \
    format_timestamp(member_time) + '.'
  await interaction.response.send_message(text, ephemeral=True)


#finish this command - add conversions
# @tree.command(
#   name='alloffline',
#   description='See times of all offline users'
# )
# async def alloffline(ctx):
#   server_data = servers.get(ctx.guild.id, {})
#   print(server_data)


#show users that were not able to see the messages after give time
@tree.command(
  name = 'since',
  description = 'When was user last seen online'
)
async def since(interaction: discord.Interaction, timestamp:str):
  time = dateparser.parse(timestamp)
  if time is None:
    response = 'Cound not parse the date.'
    await interaction.response.send_message(response, ephemeral=True)

  server_data = servers.get(interaction.guild_id, {})
  
  output_data = []
  guild_id = interaction.guild_id
  if guild_id is not None:
    guild = bot.get_guild(guild_id)

  if guild is None:
    response = 'Server ID not recevied.'
    await interaction.response.send_message(response, ephemeral=True)

  channel = interaction.channel
  if isinstance(channel, discord.Thread):
    thread_members = await channel.fetch_members()
    members = []
    for member in thread_members:
      id = member.id
      members.append(await bot.fetch_user(id))
  else:
    members = interaction.channel.members

  members = (member for member in members if member.bot is False)
  for member in members:
    
    if member.id not in server_data \
    or datetime.fromtimestamp(server_data[member.id]) < time: #type: ignore
      output_data.append(member.display_name) # type: ignore


  if len(output_data) > 0:
    output_data.sort()
    output_data.insert(1, 'Content did not see ' + str(len(output_data)) + ' members:')
    response = '\n'.join(output_data)
    response = cut_rows(response)
    await interaction.response.send_message(response, ephemeral=True)
  else: 
    #should only happen on debug
    response = 'No members fetched. Everyone has seen it.'
    await interaction.response.send_message(response, ephemeral=True)


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
  print('Used on ' + str(len(bot.guilds)) + ' servers.')

  log_users.start()
  sync_commands.start()
  print('ready')


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

bot.run(bot_token)
