# -*- coding: utf-8 -*-

import json
from datetime import datetime, timedelta
from db_model import UserMap, Session
from utils import get_text


import redis
from dwapi import datawiz
import pandas as pd
import os.path

import matplotlib
matplotlib.use("agg")  # switch to png mode

r_server = redis.Redis('localhost')


class Query:
    def __init__(self, chat_id):
        session = Session()
        user = session.query(UserMap).filter(UserMap.chat_id == chat_id).one()
        session.close()

        self.dw = datawiz.DW(user.login, user.password)
        self.chat_id = chat_id

        self.query_type = 'all'
        self.shop = 'all'
        self.category = self.dw.get_client_info()['root_category']
        self.date_from = self.dw.get_client_info()['date_from']
        self.date_to = self.dw.get_client_info()['date_to']

    def set_info(self, query_type, shop, category, date_from, date_to):
        self.query_type = query_type
        self.shop = shop
        self.category = category
        self.date_from = date_from
        self.date_to = date_to

    def set_default_info(self):
        self.query_type = 'all'
        self.shop = 'all'
        self.category = self.dw.get_client_info()['root_category']
        self.date_from = self.dw.get_client_info()['date_from']
        self.date_to = self.dw.get_client_info()['date_to']

    def set_info_cache(self):
        self.query_type = r_server.hget(self.chat_id, 'type')
        self.shop = r_server.hget(self.chat_id, 'shop')
        self.category = int(r_server.hget(self.chat_id, 'category'))

        date_from = r_server.hget(self.chat_id, 'date_from')
        date_to = r_server.hget(self.chat_id, 'date_to')

        mask = "%Y-%m-%d %H:%M:%S"
        self.date_from = datetime.strptime(date_from, mask)
        self.date_to = datetime.strptime(date_to, mask)

    def make_query(self):
        query_type = self.query_type
        if query_type == 'all':
            query_type = ['turnover', 'qty', 'profit', 'receipts_qty']

        shop = self.shop
        if shop == 'all':
            shop = self.get_shops_id()
        else:
            shop = [int(shop)]

        date_from = self.date_from
        date_to = self.date_to
        category = self.category

        frame = self.dw.get_categories_sale(by=query_type,
                                           shops=shop,
                                           date_from=date_from,
                                           date_to=date_to,
                                           categories=int(category),
                                           view_type='raw'
                                           )
        if frame.empty is True:
            return None
        del frame['category'], frame['name']
        return frame

    def get_shops(self):
        return sorted(self.dw.get_client_info()['shops'].values())

    def get_shops_id(self):
        return self.dw.get_client_info()['shops'].keys()

    def name_shop2id(self, name):
        shops = self.dw.get_client_info()['shops']
        shops = {int(value): key for key, value in shops.iteritems()}
        return shops[name]

    def id_shop2name(self, id):
        shops = self.dw.get_client_info()['shops']
        return shops[id]

    # get list of categories
    def get_categories(self):
        list_len = r_server.llen('category#' + str(self.chat_id))
        return sorted(r_server.lrange('category#' + str(self.chat_id), 0, list_len))

    def show_query(self):
        print('QUERY', self.query_type, self.shop, self.category, self.date_from, self.date_to)

    def type_translate(self, type_string):
        text = get_text(self.chat_id)
        type_map = {'turnover': text['types_values'][0],
                    'qty': text['types_values'][1],
                    'profit': text['types_values'][2],
                    'receipts_qty': text['types_values'][3]
                    }
        return type_map[type_string]

if __name__ == '__main__':
    pass
    # login = raw_input('login: ')
    # password = raw_input('password: ')
    # query = Query(login, password)
    # root_category = query.dw.get_client_info()['root_category']
    # query.set_info('all',
    #                     641,
    #                     root_category,
    #                     datetime(2015,9,10),
    #                     datetime(2015,10,10))
    # result = query.make_query()
    # print('r-1',result)
    #
    # query.set_info('all',
    #                     'all',
    #                     root_category,
    #                     datetime(2015,9,10),
    #                     datetime(2015,10,10))
    # result = query.make_query()
    # print('r-2',result)
    #
    # query.set_info('turnover',
    #                     641,
    #                     root_category,
    #                     datetime(2015,9,10),
    #                     datetime(2015,10,10))
    # result = query.make_query()
    # print('r-3',result)
