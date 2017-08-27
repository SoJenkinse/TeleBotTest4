# -*- coding: utf-8 -*-

from utils import create_one_start_markup

shops_string_dict = {'all': 'all_shops_sum', '-1': 'all_shops'}
shops_string_dict_rev = {'all_shops_sum': '-1', 'all_shops': '-1'}

language_values_dict = {'ua': [u'🇷🇺 Російська', u'🇺🇦 Українська'], 'ru': [u'🇷🇺 Русский', u'🇺🇦 Украинский']}
language_choosen = {u'🇺🇦 Українська': 'ua', u'🇺🇦 Украинский': 'ua',
                    u'🇷🇺 Російська': 'ru', u'🇷🇺 Русский': 'ru'}
language_adjective_choosen = {u'🇺🇦 Українська': u'українську', u'🇺🇦 Украинский': u'українську',
                                 u'🇷🇺 Російська': u'русский', u'🇷🇺 Русский': u'русский'}
language_to_system_default = {'ua': 'uk_UA.UTF-8', 'ru': 'ru_RU.UTF-8'}

visualization_unique_dict = {u"График": "line", u"Гистограмма": "bar",
                             u'Графік':'line', u'Гістограмма':'bar',
                             u'None': None}
page_increment = {u'prev': -1, u'next': 1}


# UTC default markup
utc_values = ['UTC+0']
for i in range(1, 13):
    utc_values.extend(['UTC-' + str(i), 'UTC+' + str(i)])
utc_markup = create_one_start_markup(utc_values[1:], first=utc_values[0])
