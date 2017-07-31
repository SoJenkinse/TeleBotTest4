# -*- coding: utf-8 -*-

import inspect
import sys
import time

from settings import *
from utils import create_markup, get_text

import telebot
import flask
import redis
from telebot import types

bot = telebot.TeleBot(TOKEN)
server = flask.Flask('localhost')
r_server = redis.Redis('localhost')

start = time.time()


@bot.message_handler(commands=['start'])
def process_start(message):
    chat_id = message.chat.id
    message_text = u'Добрый день! \n'
    message_text += u'Я DWBot. Помогу вам найти ответы по основным показателям вашего бизнеса. \n\n'
    message_text += u'Вход <логин> <пароль> - команда для начала работы \n\n'
    message_text += u'Наши контакты: \n'
    message_text += u'Тел: +38 (050) 337-73-53 \n'
    message_text += u'http://datawiz.io/uk/ \n'
    bot.send_message(chat_id, message_text)


@bot.message_handler(func= lambda m: m.text[:4] == u'Вход')
def process_login(message):
    chat_id = message.chat.id

    # create values for new markup
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add(u'Русский', u'Украинский')

    msg = bot.send_message(chat_id, u'Добро пожаловать! Выберите язык', reply_markup=markup)
    bot.register_next_step_handler(msg, process_language)
    save_state(chat_id)


def process_language(message):
    chat_id = message.chat.id
    text = get_text()

    # create new markup, types
    markup = create_markup(text[u'types_values'])
    msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
    bot.register_next_step_handler(msg, process_type)
    save_state(chat_id)


def process_type(message):
    text = get_text()
    to_main_menu(message, text[u"main_menu"])


def process_main_menu(message):
    text = get_text()
    chat_id = message.chat.id

    if message.text == text[u'shops']:
        shops = [text[u'all_shops_sum']]
        markup = create_markup(shops)
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_shop)

    if message.text == text[u'categories']:
        categories = [text[u'all_categories']] + [u'cat1', u'cat2', u'cat3']
        markup = create_markup(categories)
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_category)

    if message.text == text[u'period']:
        markup = create_markup(text[u'period_values'])
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_period)

    if message.text == text[u'choose_period']:
        to_main_menu(message)

    if message.text == text[u'visualization']:
        markup = create_markup(text[u'visualization_values'])
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_visualization)

    if message.text == text[u'reset']:
        # to types markup
        markup = create_markup(text[u'types_values'])
        msg = bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)

    if message.text == text[u'exit']:
        markup = types.ReplyKeyboardRemove()
        bot.send_message(chat_id, text[u'you_leave'], reply_markup=markup)

    # query handler
    if message.text == text[u'OK']:
        markup = create_markup(text[u'types_values'])

        msg = bot.send_message(chat_id, u'some text', reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)
    save_state(chat_id)


def process_shop(message):
    to_main_menu(message)


def process_category(message):
    to_main_menu(message)


def process_period(message):
    to_main_menu(message)


def process_visualization(message):
    to_main_menu(message)


def to_main_menu(message, msg_text=None):
    chat_id = message.chat.id

    if msg_text is None:
        msg_text = message.text

    text = get_text()

    markup = create_markup(text[u'main_menu_values'])
    msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_main_menu)
    save_state(chat_id)


def load_state():
    # get all process functions in module and create dict {string_func, func}
    fset = [obj for name, obj in inspect.getmembers(sys.modules[__name__]) if inspect.isfunction(obj)]
    fset = [obj for obj in fset if 'process' in str(obj)]
    fset_string = [str(obj).split()[1] for obj in fset]
    fdict = {key: value for key, value in zip(fset_string, fset)}

    print(fdict.keys())

    if r_server.exists('pre_message_subscribers_next_step'):
        pre_message_sub = r_server.hgetall('pre_message_subscribers_next_step')
    else:
        pre_message_sub = {}

    # handle pre_message_sub, transform strings to correct values
    for key in pre_message_sub:
        if isinstance(key, str):
            pre_message_sub[int(key)] = pre_message_sub.pop(key)
            func_string = pre_message_sub[int(key)]
            func_string = func_string.split(' ')[1]
            pre_message_sub[int(key)] = [fdict[func_string]]
    bot.pre_message_subscribers_next_step = pre_message_sub
    show_state('LOAD')


def save_state(chat_id):
    value = bot.pre_message_subscribers_next_step[chat_id]

    # only one function can be located in pre_message_subscribers_next_step
    if len(value) > 1:
        value = value[0]
        bot.pre_message_subscribers_next_step[chat_id] = [value]

    r_server.hset('pre_message_subscribers_next_step', chat_id, value)


def show_state(text):
    print(text, bot.pre_message_subscribers_next_step)


def clear_state():
    bot.pre_message_subscribers_next_step = {}
    r_server.delete('pre_message_subscribers_next_step')


def delete_state(chat_id):
    bot.pre_message_subscribers_next_step[chat_id] = []

# clear_state()
load_state()
bot.polling(none_stop=True)