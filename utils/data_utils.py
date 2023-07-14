import re
import os
import pandas as pd
import numpy as np
from datetime import datetime

def format_time(t):
    dt = datetime.strptime(t, "%I:%M:%S %p")
    hour = dt.strftime("%I").lstrip('0')
    return f"{hour}:{dt.strftime('%M:%S %p')}"

def get_right_date(str):
    return datetime.strftime(datetime.strptime(str, "%Y-%m-%d"), "%d/%m/%y")
def get_right_time(str):
    return format_time(datetime.strftime(datetime.strptime(str, "%H:%M:%S"), "%I:%M:%S %p"))

def obfuscate_phone_references(text, num_digits_to_obfuscate=4):
    # Matches @ followed by any number of digits
    pattern = re.compile(r'@(\d+)')

    def obfuscate_match(match):
        phone_num = match.group(1)  # Get the entire match
        # Replace the last num_digits_to_obfuscate digits with "x"
        return "@" + phone_num[:-num_digits_to_obfuscate] + "x" * num_digits_to_obfuscate

    obfuscated_text = pattern.sub(obfuscate_match, text)
    return obfuscated_text

def get_messages_from_whatsapp_export(path):
    messages = []
    current_message = None
    prev_sender = None
    with open(path, 'r', encoding="utf-8") as f:
        for line in f:
            match = re.match(r'\u200e?\[(\d{2}/\d{2}/\d{2}, \d{1,2}:\d{2}:\d{2} (?:AM|PM))\] (.*?): (.*)', line)
            if match:
                # Save the previous message if exists
                if current_message:
                    messages.append(current_message)
                    
                date, sender, message = match.groups()
                media_match = re.match(r'‎<attached: (.*?)>', message)
                

                if media_match:
                    media_file = media_match.group(1)
                    current_message = {'date': date, 'sender': sender, 'message': message, 'media_file': media_file, 'new_sender': sender != prev_sender }
                else:
                    current_message = {'date': date, 'sender': sender, 'message': message, 'media_file': None, 'new_sender': sender != prev_sender}
                prev_sender = sender
            else:
                # If the line doesn't start with a timestamp, it's a continuation of the previous message
                if current_message:
                    current_message['message'] += '\n' + line.strip()

        # Don't forget to add the last message
        if current_message:
            messages.append(current_message)

    return messages


def get_messages_from_extension_export(path):
    file = pd.read_csv(path, delimiter=';')
    # convert `QuotedMessageDate` tht are nan to empty string
    file['QuotedMessage'] = file['QuotedMessage'].replace(np.nan, '', regex=True)
    # make message body and quoted message as string
    file['MessageBody'] = file['MessageBody'].astype(str)
    file['QuotedMessageDate'] = file['QuotedMessageDate'].astype(str)
    file['QuotedMessageTime'] = file['QuotedMessageTime'].astype(str)
    return file


def get_chat_messages(whatsapp_export_path="data/_chat.txt", extension_export_path="data/The GenerativeAI Group.csv"):
    txt_index = 0


    txt_data = get_messages_from_whatsapp_export(whatsapp_export_path)
    csv_data = get_messages_from_extension_export(extension_export_path)

    messages = []
    for index, csv_row in csv_data.iterrows():
        if txt_index >= len(txt_data):
            break
        
        txt_data_row = txt_data[txt_index]
        
        csv_datetime = f"{get_right_date(csv_row['Date2'])}, {get_right_time(csv_row['Time'])}"
        txt_datetime = txt_data_row['date']
        csv_datetime_obj = datetime.strptime(csv_datetime, "%d/%m/%y, %I:%M:%S %p")
        txt_datetime_obj = datetime.strptime(txt_datetime, "%d/%m/%y, %I:%M:%S %p")

        while csv_datetime_obj > txt_datetime_obj:
            messages.append(
                {
                    'date': txt_data_row['date'],
                    'sender': txt_data_row['sender'],
                    'message': txt_data_row['message'],
                    'media_file': txt_data_row['media_file'],
                    'new_sender': False,
                    'quoted_message': None,
                    'quoted_message_time':None
                }
            )

            txt_index += 1  
            txt_data_row = txt_data[txt_index]
            txt_datetime = txt_data_row['date']
            txt_datetime_obj = datetime.strptime(txt_datetime, "%d/%m/%y, %I:%M:%S %p")

        if csv_datetime_obj < txt_datetime_obj:
            messages.append({
                'date': csv_datetime,
                'sender': csv_row['UserName'],
                'message': obfuscate_phone_references(csv_row['MessageBody']),
                'media_file': None,
                'new_sender': False,
                'quoted_message': csv_row['QuotedMessage'],
                'quoted_message_time': f"{get_right_date(csv_row['QuotedMessageDate'])}, {get_right_time(csv_row['QuotedMessageTime'])}" if csv_row['QuotedMessageDate']!='nan' else None
            })

        elif csv_datetime_obj == txt_datetime_obj:
            messages.append({
                'date': txt_data_row['date'],
                'sender': txt_data_row['sender'],
                'message': txt_data_row['message'],
                'media_file': txt_data_row['media_file'],
                'new_sender': False,
                'quoted_message': obfuscate_phone_references(csv_row['QuotedMessage']),
                'quoted_message_time': f"{get_right_date(csv_row['QuotedMessageDate'])}, {get_right_time(csv_row['QuotedMessageTime'])}" if csv_row['QuotedMessageDate']!='nan' else None

            })

            txt_index += 1
    
    #iterate over all messages and if the message has if the message contrains 'Nirant' , delete it
    def filterMessages(message):
        if 'joined using this group\'s invite link' in message['message']:
            return False
        if 'Nirant added ' in message['message']:
            return False
        if 'joined from the community' in message['message']:
            return False
        if 'This message was deleted.' in message['message']:
            return False
        if 'This message was deleted by admin' in message['message']:
            return False
        return True

    messages = list(filter(filterMessages, messages))

    # obfuscate all references to phone numbers in sender, message and quoted message
    for message in messages:
        message['message'] = obfuscate_phone_references(message['message'])
        message['sender'] = obfuscate_phone_references(str(message['sender']))
        if message['quoted_message']:
            message['quoted_message'] = obfuscate_phone_references(message['quoted_message'])
    

    # iterate over all messages and if the previous sender is same not same same current sender, set new_sender to true
    prev_sender = None
    for message in messages:
        
        if prev_sender is None:
            prev_sender = message['sender']
            continue

        if prev_sender == message['sender']:
            message['new_sender'] = False
        else:
            message['new_sender'] = True

        prev_sender = message['sender']

    return messages

if __name__ == '__main__':
    messages = get_chat_messages()
    # print the first 100 messages
    for message in messages[:100]:
        print(message)