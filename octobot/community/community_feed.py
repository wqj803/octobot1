#  This file is part of OctoBot (https://github.com/Drakkar-Software/OctoBot)
#  Copyright (c) 2021 Drakkar-Software, All rights reserved.
#
#  OctoBot is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either
#  version 3.0 of the License, or (at your option) any later version.
#
#  OctoBot is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  General Public License for more details.
#
#  You should have received a copy of the GNU General Public
#  License along with OctoBot. If not, see <https://www.gnu.org/licenses/>.
import copy

import websockets
import asyncio
import enum
import json
import distutils.version as loose_version


import octobot_commons.logging as bot_logging
import octobot_commons.errors as commons_errors
import octobot_commons.enums as commons_enums
import octobot_commons.authentication as authentication
import octobot.constants as constants


class COMMANDS(enum.Enum):
    SUBSCRIBE = "subscribe"
    MESSAGE = "message"


class CHANNELS(enum.Enum):
    MESSAGE = "Spree::MessageChannel"


class CommunityFeed:
    INIT_TIMEOUT = 60

    def __init__(self, feed_url, authenticator):
        self.logger: bot_logging.BotLogger = bot_logging.get_logger(
            self.__class__.__name__
        )
        self.feed_url = feed_url
        self.should_stop = False
        self.websocket_connection = None
        self.consumer_task = None
        self.lock = asyncio.Lock()
        self.authenticator = authenticator
        self.feed_callbacks = {}
        self._identifier_by_stream_id = {}

    async def start(self):
        await self._ensure_connection()
        if self.consumer_task is None or self.consumer_task.done():
            self.consumer_task = asyncio.create_task(self.start_consumer("default_path"))

    async def stop(self):
        self.should_stop = True
        await self.websocket_connection.close()
        self.consumer_task.cancel()

    async def start_consumer(self, path):
        while not self.should_stop:
            await self._ensure_connection()
            async for message in self.websocket_connection:
                try:
                    await self.consume(message)
                except Exception as e:
                    self.logger.exception(e, True, f"Error while consuming feed: {e}")

    async def consume(self, message):
        parsed_message = json.loads(message)["message"]
        try:
            self._ensure_supported(parsed_message)
            for callback in self._get_callbacks(parsed_message):
                await callback(parsed_message)
        except commons_errors.UnsupportedError as e:
            self.logger.error(f"Unsupported message: {e}")

    def _ensure_supported(self, parsed_message):
        if loose_version.LooseVersion(parsed_message[commons_enums.CommunityFeedAttrs.VERSION.value]) \
                < loose_version.LooseVersion(constants.COMMUNITY_FEED_CURRENT_MINIMUM_VERSION):
            raise commons_errors.UnsupportedError(
                f"Minimum version: {constants.COMMUNITY_FEED_CURRENT_MINIMUM_VERSION}"
            )

    async def send(self, message, channel_type, identifier,
                   command=COMMANDS.MESSAGE.value, reconnect_if_necessary=True):
        if reconnect_if_necessary:
            await self._ensure_connection()
        await self.websocket_connection.send(self._build_ws_message(message, channel_type, command, identifier))

    def _build_ws_message(self, message, channel_type, command, identifier):
        return json.dumps({
            "command": command,
            "identifier": self._build_channel_identifier(),
            "data": self._build_data(channel_type, identifier, message)
        })

    def _build_data(self, channel_type, identifier, message):
        if message:
            return {
                "topic": channel_type,
                "feed_id": self._build_stream_id(identifier),
                "version": constants.COMMUNITY_FEED_CURRENT_MINIMUM_VERSION,
                "value": message,
            }
        return {}

    async def register_feed_callback(self, channel_type, callback, identifier=None):
        """
        Registers a feed callback
        """
        if identifier not in list(self._identifier_by_stream_id.values()):
            stream_id = await self._fetch_stream_identifier(identifier)
            self._identifier_by_stream_id[stream_id] = identifier
        try:
            self.feed_callbacks[channel_type][identifier].append(callback)
        except KeyError:
            if channel_type not in self.feed_callbacks:
                self.feed_callbacks[channel_type] = {}
            self.feed_callbacks[channel_type][identifier] = [callback]

    async def _fetch_stream_identifier(self, identifier):
        if identifier is None:
            return None
        params = {
            "slug": identifier
        }
        # TMP as long as endpoint is not available
        return 1
        # end TMP
        async with self.authenticator.get_aiohttp_session().get(constants.OCTOBOT_COMMUNITY_FETCH_FEED_IDENTIFIER_URL,
                                                                params=params) as resp:
            stream_id = await resp.json()
            return stream_id

    def _get_callbacks(self, parsed_message):
        channel_type = self._get_channel_type(parsed_message)
        for callback in self.feed_callbacks.get(channel_type, {}).get(None, ()):
            yield callback
        try:
            identifier = self._get_identifier(parsed_message)
        except KeyError:
            self.logger.debug(f"Unknown feed identifier: "
                              f"{parsed_message[commons_enums.CommunityFeedAttrs.STREAM_ID.value]}")
            return
        if identifier is None:
            # do not yield the same callback twice
            return
        for callback in self.feed_callbacks.get(channel_type, {}).get(identifier, ()):
            yield callback

    def _get_channel_type(self, message):
        return commons_enums.CommunityChannelTypes(message[commons_enums.CommunityFeedAttrs.CHANNEL_TYPE.value])

    def _get_identifier(self, message):
        return self._identifier_by_stream_id[message[commons_enums.CommunityFeedAttrs.STREAM_ID.value]]

    def _build_channel_identifier(self):
        return {
            "channel": CHANNELS.MESSAGE.value
        }

    def _build_stream_id(self, requested_identifier):
        for stream_id, identifier in self._identifier_by_stream_id.items():
            if requested_identifier == identifier:
                return identifier
        return None

    async def _subscribe(self):
        await self.send({}, None, None, command=COMMANDS.SUBSCRIBE.value)
        # waiting for subscription confirmation
        try:
            await asyncio.wait_for(self._get_subscribe_answer(), self.INIT_TIMEOUT)
        except asyncio.TimeoutError:
            raise authentication.AuthenticationError(f"Failed to subscribe to feed")

    async def _get_subscribe_answer(self):
        async for message in self.websocket_connection:
            self.logger.debug("Waiting for subscription confirmation...")
            resp = json.loads(message)
            # TODO handle subscribe errors
            if resp.get("type") and resp.get("type") == "confirm_subscription":
                return

    async def _ensure_connection(self):
        if not self.is_connected():
            async with self.lock:
                if not self.is_connected():
                    # (re)connect websocket
                    await self._connect()

    async def _connect(self):
        if self.authenticator.initialized_event is not None:
            await asyncio.wait_for(self.authenticator.initialized_event.wait(), self.INIT_TIMEOUT)
        if self.authenticator._auth_token is None:
            raise authentication.AuthenticationRequired("OctoBot Community authentication is required to "
                                                        "use community trading signals")
        headers = {"Authorization": f"Bearer {self.authenticator._auth_token}"}
        self.websocket_connection = await websockets.connect(self.feed_url, extra_headers=headers)
        await self._subscribe()
        self.logger.info("Connected to community feed")

    def is_connected(self):
        return self.websocket_connection is not None and self.websocket_connection.open