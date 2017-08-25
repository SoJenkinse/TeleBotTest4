# -*- coding: utf-8 -*-

from telebot import types
import json
from db_model import Session, UserMap, UserState
from sqlalchemy.orm.exc import NoResultFound
import logging

time_test = {}


def get_text(chat_id, language = 'ua', force = False, login=None):
    if force is False:
        try:
            session = Session()

            if login is None:
                login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login

            user = session.query(UserMap).filter(UserMap.login == login).one()
            language = user.lang
            session.close()
        except NoResultFound:
            logging.error('get_text NoResultFound')

        if language is None:
            return None
    if language == 'ua':
        path_lang = 'localization/ua.json'
    else:
        path_lang = 'localization/ru.json'

    with open(path_lang) as file_lang:
        text = file_lang.read()
    return json.loads(text)


# create markup from list
def create_markup(values, resize_keyboard=False):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=resize_keyboard)
    for i in range(0, len(values), 2):
        if len(values) % 2 != 0 and i == len(values)-1:
            markup.add(values[i])
        else:
            markup.add(values[i], values[i+1])
    return markup


def create_linear_markup(values):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for value in values:
        markup.add(value)
    return markup


def create_pagination_markup(values, text, chunk_len=50, page_number=0):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    values[1:] = sorted(values[1:])

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

