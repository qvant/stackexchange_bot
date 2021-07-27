#!/bin/bash
export APP_HOME="/usr/app/stackexchange_bot"
cd $APP_HOME
sleep 65
python3 $APP_HOME/main.py & disown