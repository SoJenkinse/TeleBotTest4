# -*- coding: utf-8 -*-

import json

from settings import *


import telebot
import flask
import redis
from telebot import types

bot = telebot.TeleBot(TOKEN)
server = flask.Flask('localhost')
r_server = redis.Redis('localhost')


def get_text(language='RU'):
    if language == 'UA':
        path_lang = 'localization/ua.json'
    else:
        path_lang = 'localization/ru.json'

    with open(path_lang) as file_lang:
        text = file_lang.read()
    return json.loads(text)


@bot.message_handler(commands=['start'])
def process_start(message):
    message_text = u'Добрый день! \n'
    message_text += u'Я DWBot. Помогу вам найти ответы по основным показателям вашего бизнеса. \n\n'
    message_text += u'Вход <логин> <пароль> - команда для начала работы \n\n'
    message_text += u'Наши контакты: \n'
    message_text += u'Тел: +38 (050) 337-73-53 \n'
    message_text += u'http://datawiz.io/uk/ \n'
    bot.send_message(message.chat.id, message_text)


@bot.message_handler(func= lambda m: m.text[:4] == u'Вход')
def process_login(message):
    chat_id = message.chat.id

    # create values for new markup
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add(u'Русский', u'Украинский')

    msg = bot.send_message(chat_id, u'Добро пожаловать! Выберите язык', reply_markup=markup)
    bot.register_next_step_handler(msg, process_language)


def process_language(message):
    text = get_text()
    # create new markup, types
    markup = create_markup(text[u'types_values'])
    msg = bot.send_message(message.chat.id, text[u'choose_type:'], reply_markup=markup)
    bot.register_next_step_handler(msg, process_type)


def process_type(message):
    text = get_text()
    to_main_menu(message, text[u"main_menu"])


def process_main_menu(message):
    text = get_text()
    chat_id = message.chat.id
    # create new markup
    if message.text == text[u'shops']:
        shops = [text[u'all_shops_sum']]
        markup = create_markup(shops)
        bot.send_message(message.chat.id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_shop)

    if message.text == text[u'categories']:
        # set cache if needed
        if r_server.exists('category#' + str(message.chat.id)) is False:
            bot.send_message(message.chat.id, text[u'wait_please'])

        categories = [text[u'all_categories']] + [u'cat1', u'cat2', u'cat3']
        markup = create_pagination_markup(categories,
                                          user,
                                          chunk_len=10,
                                          page_number=user.page_category)

        bot.send_message(message.chat.id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_category)

    if message.text == user.text[u'period']:
        markup = create_markup(user.text[u'period_values'])
        bot.send_message(message.chat.id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_period)

    if message.text == user.text[u'choose_period']:
        process_calendar(message)
        to_main_menu(message, user)

    if message.text == user.text[u'visualization']:
        markup = create_markup(user.text[u'visualization_values'])
        bot.send_message(message.chat.id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_visualization)

    if message.text == user.text[u'reset']:
        # to types markup
        markup = create_markup(user.text[u'types_values'])
        msg = bot.send_message(message.chat.id, message.text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)

    if message.text == user.text[u'exit']:
        markup = types.ReplyKeyboardRemove()
        bot.send_message(message.chat.id, user.text[u'you_leave'], reply_markup=markup)

    # query handler
    if message.text == user.text[u'OK']:
        if user.visualization == user.text[u'visualization_values'][0]:
            vis_type = 'line'
        elif user.visualization == user.text[u'visualization_values'][1]:
            vis_type = 'bar'
        elif user.visualization == user.text[u'visualization_values'][2]:
            vis_type = 'excel'
        else:
            vis_type = None

        if user.shops_type == user.text[u'all_shops']:
            user.make_total_query()
            user.make_total_visualization(vis_type=vis_type)
        else:
            user.make_query()
            user.make_visualization(vis_type=vis_type)

        if user.visualization is not None:
            send_visualization(user)

        text = user.create_message()

        # to types markup
        markup = create_markup(user.text[u'types_values'])

        # split too large message
        if len(text) > 3000:
            text = text.split(u'\n\n')
            text = [text[x] for x in range(0, len(text)) if text[x]]
            for elem in text:
                msg = bot.send_message(message.chat.id, elem, reply_markup=markup)
        else:
            msg = bot.send_message(message.chat.id, text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)
    save_state(chat_id)


def process_shop(message):
    user = users[message.chat.id]

    # pagination
    if message.text == user.text[u'next']:
        message.text = user.text[u'shops']
        user.page_shop += 1
        process_main_menu(message)
        return

    if message.text == user.text[u'prev']:
        user.page_shop -= 1
        message.text = user.text[u'shops']
        process_main_menu(message)
        return

    # get shop id
    # get dict of shops and inverse it for access by name
    shops_info = user.dw.get_client_info()['shops']
    shops_info = {value: key for key, value in shops_info.iteritems()}

    user.shops_type = message.text

    if message.text == user.text[u'all_shops'] or message.text == user.text[u'all_shops_sum']:
        user.shop = shops_info.values()
        r_server.set(str(message.chat.id) + 'shop', 'all')
    else:
        user.shop = shops_info[message.text]
        r_server.set(str(message.chat.id) + 'shop', shops_info[message.text])
    to_main_menu(message, user)


def process_category(message):
    to_main_menu(message)


def process_period(message):
    user = users[message.chat.id]
    to_main_menu(message, user)


def process_visualization(message):
    user = users[message.chat.id]
    user.visualization = message.text
    r_server.set(str(message.chat.id) + 'visualization', message.text)
    to_main_menu(message, user)


# create markup from list
def create_markup(values):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for i in range(0, len(values), 2):
        if len(values) % 2 != 0 and i == len(values)-1:
            markup.add(values[i])
        else:
            markup.add(values[i], values[i+1])
    return markup


def create_pagination_markup(values, user, chunk_len=50, page_number=0):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)

    if len(values) > chunk_len:
        values = [values[x:x + chunk_len] for x in range(0, len(values), chunk_len)]
        count_pages = len(values)
        values = values[page_number]
        if page_number != 0: values += [user.text[u'prev']]
        if page_number < count_pages-1: values += [user.text[u'next']]

    for i in range(0, len(values), 2):
        if len(values) % 2 != 0 and i == len(values) - 1:
            markup.add(values[i])
        else:
            markup.add(values[i], values[i + 1])
    return markup


def to_main_menu(message, msg_text=None):
    if msg_text is None:
        msg_text = message.text

    markup = create_markup(text[u'main_menu_values'])
    msg = bot.send_message(message.chat.id, msg_text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_main_menu)


load_state()
bot.polling(none_stop=True)