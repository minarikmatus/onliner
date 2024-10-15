# onliner
Discord bot watching members when they were last seen online.

## Commands

`/ending` shows threads that will be auto archived in next 24 hours

`/last` shows server members that are not online with time when they were last online

`/lastseen @mention` shows time when specific member was last seen online

`/since TIMESTAMP` shows members in current channel or thread that could or couldn't see the content since TIMESTAMP


## SETUP

install required packages

    pip3 install -r requirements.txt

.env file contents:

    discord_token = 'SET_YOUR_TOKEN'

## START

    python3 main.py
