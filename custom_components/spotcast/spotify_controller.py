"""
Controller to interface with Spotify.
"""
from __future__ import annotations

import logging
import threading
import requests
import json

from .const import APP_SPOTIFY

from pychromecast.controllers import BaseController
from pychromecast.error import LaunchError

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
TYPE_GET_INFO = "getInfo"
TYPE_GET_INFO_RESPONSE = "getInfoResponse"
TYPE_ADD_USER = "addUser"
TYPE_ADD_USER_RESPONSE = "addUserResponse"
TYPE_ADD_USER_ERROR = "addUserError"


# pylint: disable=too-many-instance-attributes
class SpotifyController(BaseController):
    """Controller to interact with Spotify namespace."""

    def __init__(self, access_token=None, expires=None):
        super(SpotifyController, self).__init__(APP_NAMESPACE, APP_SPOTIFY)

        self.logger = logging.getLogger(__name__)
        self.session_started = False
        self.access_token = access_token
        self.expires = expires
        self.is_launched = False
        self.device = None
        self.credential_error = False
        self.waiting = threading.Event()

    def receive_message(self, _message, data: dict):
        """
        Handle the auth flow and active player selection.

        Called when a message is received.
        """
        if data["type"] == TYPE_GET_INFO_RESPONSE:
            self.device = data["payload"]["deviceID"]
            self.client = data["payload"]["clientID"]
            headers = {
                'authority': 'spclient.wg.spotify.com',
                'authorization': 'Bearer {}'.format(self.access_token),
                'content-type': 'text/plain;charset=UTF-8'
            }

            request_body = json.dumps({'clientId': self.client, 'deviceId': self.device})

            response = requests.post('https://spclient.wg.spotify.com/device-auth/v1/refresh', headers=headers, data=request_body)
            json_resp = response.json()
            self.send_message({
                "type": TYPE_ADD_USER,
                "payload": {
                    "blob": json_resp["accessToken"],
                    "tokenType": "accesstoken"
                }
            })
        if data["type"] == TYPE_ADD_USER_RESPONSE:
            self.is_launched = True
            self.waiting.set()

        if data["type"] == TYPE_ADD_USER_ERROR:
            self.device = None
            self.credential_error = True
            self.waiting.set()
        return True

    def launch_app(self, timeout=10):
        """
        Launch Spotify application.

        Will raise a LaunchError exception if there is no response from the
        Spotify app within timeout seconds.
        """

        if self.access_token is None or self.expires is None:
            raise ValueError("access_token and expires cannot be empty")

        def callback():
            """Callback function"""
            self.send_message({"type": TYPE_GET_INFO, "payload": {}})

        self.device = None
        self.credential_error = False
        self.waiting.clear()
        self.launch(callback_function=callback)

        counter = 0
        while counter < (timeout + 1):
            if self.is_launched:
                return
            self.waiting.wait(1)
            counter += 1

        if not self.is_launched:
            # raise LaunchError(
            #     "Timeout when waiting for status response from Spotify app"
            # )
            self.logger.warning("Timeout when waiting for status response from Spotify app")

    # pylint: disable=too-many-locals
    def quick_play(self, **kwargs):
        """
        Launches the spotify controller and returns when it's ready.
        To actually play media, another application using spotify connect is required.
        """
        self.access_token = kwargs["access_token"]
        self.expires = kwargs["expires"]

        self.launch_app(timeout=20)
