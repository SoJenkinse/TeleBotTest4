from telebot import types
import json


def get_text(language='RU'):
    if language == 'UA':
        path_lang = 'localization/ua.json'
    else:
        path_lang = 'localization/ru.json'

    with open(path_lang) as file_lang:
        text = file_lang.read()
    return json.loads(text)


# create markup from list
def create_markup(values):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for i in range(0, len(values), 2):
        if len(values) % 2 != 0 and i == len(values)-1:
            markup.add(values[i])
        else:
            markup.add(values[i], values[i+1])
    return markup


def create_pagination_markup(values, text, chunk_len=50, page_number=0):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)

    if len(values) > chunk_len:
        values = [values[x:x + chunk_len] for x in range(0, len(values), chunk_len)]
        count_pages = len(values)
        values = values[page_number]
        if page_number != 0: values += [text[u'prev']]
        if page_number < count_pages-1: values += [text[u'next']]

    for i in range(0, len(values), 2):
        if len(values) % 2 != 0 and i == len(values) - 1:
            markup.add(values[i])
        else:
            markup.add(values[i], values[i + 1])
    return markup