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

from config import MARKET_SEPARATOR


# Return currency, market
def split_symbol(symbol):
    splitted = symbol.split(MARKET_SEPARATOR)
    if len(splitted) > 1:
        return splitted[0], splitted[1]
    else:
        return symbol, None


# Return merged currency and market without /
def merge_symbol(symbol):
    return symbol.replace(MARKET_SEPARATOR, "")


# Merge currency and market
def merge_currencies(currency, market):
    return f"{currency}/{market}"
