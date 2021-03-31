import json
import sys

import requests

def customizer_on_OK():

    bot_name = 'Snowcast'
    emoji_id = ':snowflake:'
    #Generating random hex color code
    hex_number = '#00ff00'

    return bot_name, emoji_id, hex_number


def send_slack_notifier(url, message, title,):
    bot_name, emoji_id, hex_number = customizer_on_OK()

    slack_data = {
        "username": bot_name,
        "icon_emoji": emoji_id,
        "channel": "#snowcast",
        "attachments": [
            {
                "color": "#9733EE",
                "fields": [
                    {
                        "title": title,
                        "value": message,
                        "short": "false",
                    }
                ]
            }
        ]
    }
    byte_length = str(sys.getsizeof(slack_data))
    headers = {'Content-Type': "application/json", 'Content-Length': byte_length}
    response = requests.post(url, data=json.dumps(slack_data), headers=headers)
    if response.status_code != 200:
        raise Exception(response.status_code, response.text)