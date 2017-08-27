# -*- coding: utf-8 -*-

from telebot import types
import json
from db_model import Session, UserMap, UserState, UserAlert
from sqlalchemy.orm.exc import NoResultFound
import logging
import time
import datetime


def get_text(chat_id, language='ua', force=False, login=None):
    if force is False:
        try:
            session = Session()

            if login is None:
                login = session.query(UserState).filter(UserState.chat_id == chat_id).one().user.login

            user = session.query(UserMap).filter(UserMap.login == login).one()
            language = user.lang

            if language is None:
                return None

            session.close()
        except NoResultFound:
            logging.error('get_text NoResultFound')

    json_path = {'ua': 'localization/ua.json', 'ru': 'localization/ru.json'}
    path_lang = json_path.get(language)

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


def create_double_end_markup(values, double_one, double_two):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for value in values:
        markup.add(value)
    markup.add(double_one, double_two)
    return markup


def create_one_start_markup(values, first):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add(first)
    for i in range(0, len(values), 2):
        if len(values) % 2 != 0 and i == len(values)-1:
            markup.add(values[i])
        else:
            markup.add(values[i], values[i+1])
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


def is_time_format(input):
    try:
        time.strptime(input, '%H:%M')
        return True
    except ValueError:
        return False


def split_if_too_large(message):
    messages = []
    if len(message) > 4096:
        message = message.split(u'\n')
        for i in range(0, len(message), 90):
            messages.append(u'\n'.join(message[i: i + 90]))
    else:
        messages.append(message)
    return messages


# return datetime with last day of month
def month_end(any_day):
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)
    return next_month - datetime.timedelta(days=next_month.day)


def month_start(today):
    return today.replace(month=today.month+1, day=1)


def week_start(today):
    while today.weekday() != 0:
        today = today.replace(day=today.day+1)
    return today


def week_end(today):
    while today.weekday() != 6:
        today = today.replace(day=today.day+1)
    return today


def everyday(today):
    return today


def alerts_generator():
    date_types = {'everyday': everyday, 'week_start': week_start, 'week_end': week_end,
                  'month_start': month_start, 'month_end': month_end}

    while True:
        session = Session()
        alerts = session.query(UserAlert).all()
        session.close()

        today = datetime.datetime.today()

        yield [alert for alert in alerts if date_types[alert.alert_date](today).date() == today.date()]


