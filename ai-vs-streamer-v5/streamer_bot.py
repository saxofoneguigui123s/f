"""Integracao com Streamer.bot / OBS - via websocket e HTTP."""

import json
import requests

class StreamerBotBridge:
    def __init__(self, streamerbot_url="ws://localhost:8080", obs_url="ws://localhost:4455"):
        self.streamerbot_url = streamerbot_url
        self.obs_url = obs_url
        self.obs_connected = False

    def send_streamerbot_action(self, action_name, args=None):
        payload = {"action": action_name, "args": args or {}}
        try:
            requests.post("http://localhost:2790/action", json=payload, timeout=2)
            return True
        except Exception:
            return False

    def set_obs_scene(self, scene_name):
        try:
            import websocket
            ws = websocket.create_connection(self.obs_url, timeout=2)
            ws.send(json.dumps({
                "op": 6,
                "d": {
                    "requestType": "SetCurrentProgramScene",
                    "requestData": {"sceneName": scene_name}
                }
            }))
            ws.close()
            self.obs_connected = True
            return True
        except Exception:
            self.obs_connected = False
            return False

    def update_obs_text(self, source_name, text):
        try:
            import websocket
            ws = websocket.create_connection(self.obs_url, timeout=2)
            ws.send(json.dumps({
                "op": 6,
                "d": {
                    "requestType": "SetInputSettings",
                    "requestData": {
                        "inputName": source_name,
                        "inputSettings": {"text": text}
                    }
                }
            }))
            ws.close()
            return True
        except Exception:
            return False
