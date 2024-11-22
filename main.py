import dateparser
import pickle
import time

from datetime import datetime, timezone

import discord
from discord.ext import tasks
from discord.guild import Guild
from discord.errors import Forbidden


import os
from dotenv import load_dotenv

DISCORD_MESSAGE_LEN_LIMIT = 2000


# function to cut rows to Discord max message length, keeping rows complete
def cut_rows(text):
    text += '\n'
    if len(text) > DISCORD_MESSAGE_LEN_LIMIT:
        text = text[:DISCORD_MESSAGE_LEN_LIMIT]
    return text[:text.rfind('\n')]

load_dotenv()
bot_token = os.getenv('discord_token', None)

if not bot_token:
    message = (
        "Could not find the `bot_token` environment variable."
        "Make sure to add it to your `.env` file like this: `discord_token=value_of_your_bot_token`"
    )
    raise ValueError(message)

database_path = 'servers.dump'

delay_seconds = 30

#flag if commands have been pushed to servers
synced = 0

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True  #for on_message and /ending

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
async def log_members():
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
 

#shows threads that will be auto archived in next 24 hours
@tree.command(
    name = 'ending',
    description = 'List threads that will be auto archived in next 24 hours based last message'
)
async def ending(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)

    # Get the current time
    now = datetime.now()    #todo timezone needs to be taken into account

    # Create a list to hold threads that are about to archived
    threads_closing_soon = []

    # Get the current guild (server)
    guild = interaction.guild

    #count threads
    sum = 0
    for channel in guild.text_channels:   # type: ignore
      for thread in channel.threads:
        sum+=1
      
    update = 'Found ' + str(sum) + ' threads...'
    await interaction.edit_original_response(content=update)

    #process threads
    count = 0 
    for channel in guild.text_channels:   # type: ignore
        for thread in channel.threads:
            count +=1

            #show update every 10% of progress
            if ((count-1)/sum)*100%10 > ((count)/sum)*100%10:
                update = 'Processed ' + str(count) + ' of ' + str(sum) + ' threads.'
                await interaction.edit_original_response(content=update)

            if not thread.archived:
                # Fetch the last message in the channel
                message = [message async for message in thread.history(limit=1)][0]
                
                #calculate thread age
                last_message_minutes = int((datetime.now(timezone.utc) - message.created_at).total_seconds()/60)
                
                if last_message_minutes > (thread.auto_archive_duration - 1440) and last_message_minutes < thread.auto_archive_duration:
                    threads_closing_soon.append(thread.mention)

    threads_closing_soon.sort()
    response = '\n'.join(threads_closing_soon)
    
    if response == '':
        response = 'No threads about to be archived.'

    await interaction.edit_original_response(content=response)

def format_timestamp(timestamp):
    return f'<t:{timestamp}:R>'


async def get_channel_members(interaction:discord.Interaction) -> list[str]:
    channel = interaction.channel
    # Check if the channel is a text channel
    if isinstance(channel, discord.TextChannel):
        # Fetch all members in the guild, filter bots and readers
        members = list(member.mention for member in channel.guild.members if not member.bot and channel.permissions_for(member).read_messages)
    
    elif isinstance(channel, discord.Thread):
        thread_members = await channel.fetch_members()
        members = []
        for member in thread_members:
            id = member.id
            member = await bot.fetch_user(id)
            if not member.bot:
                members.append(member.mention)
    else:
        return []
    return members


#show who is here
@tree.command(
    name = 'here',
    description = 'List members of this channel or thread'
)
async def here(interaction: discord.Interaction):
    channel = interaction.channel

    # Check if the channel is a text channel
    if isinstance(channel, discord.TextChannel) \
        or isinstance(channel, discord.Thread):
      
        try:
            members = await get_channel_members(interaction=interaction)
        except Forbidden:
            await interaction.response.send_message('I do not have permission to access this channel or thread.', ephemeral=True)
            return
        except Exception as e:
            message = f'An error occurred while fetching members: {str(e)}'
            await interaction.response.send_message(message, ephemeral=True)
            return

    else:
        await interaction.response.send_message('This command can only be used in text channels or their threads.', ephemeral=True)
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


#list all offline members
@tree.command(
    name = 'last',
    description = 'List all offline members (max 2000 characters)'
)
async def last(interaction: discord.Interaction, offset: int = 0):
    server_data = servers.get(interaction.guild_id, {})
    
    output_data = []
    output_data_never = []
    
    #for offline members return their times
    for member in sorted(interaction.guild.members, key=lambda m: m.display_name):   # type: ignore
        if member.status == discord.Status.offline \
        and not member.bot:
            if member.id in server_data:
                output_data.append(
                    member.mention + ' was last seen ' + \
                        format_timestamp(servers[interaction.guild_id][member.id]) + '.'
                )
            else:
                output_data_never.append(
                    member.mention + ' was never seen.'
                )
          
    output_data.extend(output_data_never)

    response = '\n'.join(output_data[offset:])
    response = cut_rows(response)

    await interaction.response.send_message(response, ephemeral=True)


#reply with time of specified member
@tree.command(
    name = 'lastseen',
    description = 'When was member last seen online'
)
async def lastseen(interaction: discord.Interaction, mention: discord.Member):
    server_data = servers.get(interaction.guild_id, {})
    
    member_time = time.time()
    if mention.id in server_data:
        member_time = server_data[mention.id]

    if mention.bot:
        text = 'Bots are not watched.'
    elif mention.id not in server_data:
        text = mention.mention + ' was never seen online.'
    elif time.time() - member_time < delay_seconds:
        text = mention.mention + ' is online.'
    else:
        text = mention.mention + ' was last seen ' + \
            format_timestamp(member_time) + '.'
    await interaction.response.send_message(text, ephemeral=True)


#show members that were not able to see the messages after given time
@tree.command(
    name = 'since',
    description = 'List members that were seen online since given time'
)
async def since(interaction: discord.Interaction, timestamp:str = ''):
    if timestamp == '':
        time = dateparser.parse('1 January 1970')
    else:
        time = dateparser.parse(timestamp)
    if time is None:
        response = 'Cound not parse the date.'
        await interaction.response.send_message(response, ephemeral=True)

    server_data = servers.get(interaction.guild_id, {})
  
    read_data = []
    unread_data = []

    guild_id = interaction.guild_id
    if guild_id is not None:
        guild = bot.get_guild(guild_id)

    if guild is None:
        response = 'Server ID not recevied.'
        await interaction.response.send_message(response, ephemeral=True)

    # get members of channel or thread
    channel = interaction.channel
    members = []
    if isinstance(channel, discord.TextChannel):  # Ensure it's a text channel
        members = channel.members  # Get the members in the channel
    elif isinstance(channel, discord.Thread):
      
        try:
            threadmembers = await channel.fetch_members()
        except Forbidden:
            await interaction.response.send_message('I do not have permission to access this channel or thread.', ephemeral=True)
            return
        except Exception as e:
            message = f'An error occurred while fetching members: {str(e)}'
            await interaction.response.send_message(message, ephemeral=True)
            return

        #get member objects from guild members
        for threadmember in threadmembers:
            if guild is not None:
                members.append(guild.get_member(threadmember.id))

    members = (member for member in members if member.bot is False)

    # split members to read and unread
    for member in members:
        if member.id not in server_data \
        or datetime.fromtimestamp(server_data[member.id]) < time: # type: ignore
            unread_data.append(member.mention)   # type: ignore
        else:
            read_data.append(member.mention)   # type: ignore

    # construct response
    if len(read_data) > 0:
        read_data.sort()
        read_data.insert(0, '**Content could see ' + str(len(read_data)) + ' members:**')
        response_read = '\n'.join(read_data)
        response_read = cut_rows(response_read)
    else: 
        #should only happen on debug
        response_read = '**Nobody could see the content.**'

    if len(unread_data) > 0:
        unread_data.sort()
        unread_data.insert(0, '**Content did not see ' + str(len(unread_data)) + ' members:**')
        response_unread = '\n'.join(unread_data)
        response_unread = cut_rows(response_unread)
    else: 
        #should only happen on debug
        response_unread = '**All could see the content.**'

    response = response_read + '\n\n' + response_unread
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

    log_members.start()
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
