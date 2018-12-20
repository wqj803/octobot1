#  Drakkar-Software OctoBot
#  Copyright (c) Drakkar-Software, All rights reserved.
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3.0 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library.

import random
import time

from config import SIMULATOR_LAST_PRICES_TO_CHECK


def fill_limit_or_stop_order(limit_or_stop_order, min_price, max_price):
    last_prices = []
    limit_or_stop_order.created_time = time.time()
    for i in range(0, SIMULATOR_LAST_PRICES_TO_CHECK):
        last_prices.insert(i, {})
        last_prices[i]["price"] = random.uniform(min_price, max_price)
        last_prices[i]["timestamp"] = time.time()

    limit_or_stop_order.last_prices = last_prices
    limit_or_stop_order.update_order_status()


def fill_market_order(market_order, price):
    last_prices = [{
        "price": price
    }]

    market_order.last_prices = last_prices
    market_order.update_order_status()
