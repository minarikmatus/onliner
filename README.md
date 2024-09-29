# onliner
Discord bot to watch users when they were last seen online.

## Commands

`/last` shows last online times of all server members which are not online 

`/lastseen @mention` shows time of specific user

`/since TIMESTAMP` shows users in current channel or thread that could or couldn't see the conent since TIMESTAMP


## SETUP

install required packages

    pip3 install -r requirements.txt

.env file contents:

    discord_token = 'SET_YOUR_TOKEN'

## START

    python3 main.py
