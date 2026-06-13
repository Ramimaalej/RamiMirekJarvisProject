import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("voice_calls")


class LiveKitClient:
    def __init__(self, api_key: str = "", api_secret: str = "", host: str = ""):
        self._api_key = api_key or os.environ.get("LIVEKIT_API_KEY", "")
        self._secret = api_secret or os.environ.get("LIVEKIT_API_SECRET", "")
        self._host = host or os.environ.get("LIVEKIT_HOST", "")
        self._participant: Any = None
        self._room: Any = None
        self._on_audio_frame: Callable | None = None

    def _check_config(self):
        if not all([self._api_key, self._secret, self._host]):
            raise ValueError(
                "LiveKit credentials required — set LIVEKIT_API_KEY, "
                "LIVEKIT_API_SECRET, LIVEKIT_HOST env vars"
            )

    def create_room(self, room_name: str) -> dict[str, Any]:
        try:
            from livekit import api
        except ImportError:
            raise ImportError("livekit not installed — pip install livekit-api")

        self._check_config()
        lkapi = api.LiveKitAPI(
            host=self._host,
            api_key=self._api_key,
            api_secret=self._secret,
        )
        try:
            room = lkapi.rooms.create_room(api.models.CreateRoomRequest(name=room_name))
            return {
                "name": room.name,
                "sid": room.sid,
                "empty_timeout": room.empty_timeout,
                "max_participants": room.max_participants,
            }
        finally:
            lkapi.aclose()

    def list_rooms(self) -> list[dict[str, Any]]:
        try:
            from livekit import api
        except ImportError:
            raise ImportError("livekit not installed")

        self._check_config()
        lkapi = api.LiveKitAPI(
            host=self._host,
            api_key=self._api_key,
            api_secret=self._secret,
        )
        try:
            rooms = lkapi.rooms.list_rooms(api.models.ListRoomsRequest())
            return [
                {
                    "name": r.name,
                    "sid": r.sid,
                    "num_participants": r.num_participants,
                    "created_at": str(r.creation_time),
                }
                for r in rooms
            ]
        finally:
            lkapi.aclose()

    def generate_token(
        self, identity: str, room_name: str, can_publish: bool = True, can_subscribe: bool = True
    ) -> str:
        try:
            from livekit import api
        except ImportError:
            raise ImportError("livekit not installed")

        self._check_config()
        at = api.AccessToken(self._api_key, self._secret)
        at.identity = identity
        at.add_grant(
            room_join=True,
            room=room_name,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
        )
        return at.to_jwt()

    def connect_room(
        self,
        room_name: str,
        identity: str = "jarvis",
        on_audio_frame: Callable | None = None,
    ) -> dict[str, Any]:
        try:
            from livekit.rtc import Room, RoomEvent, AudioSource, AudioFrame
        except ImportError:
            raise ImportError(
                "livekit-rtc not installed — pip install livekit-rtc"
            )

        token = self.generate_token(identity=identity, room_name=room_name)
        room = Room()

        async def _connect():
            await room.connect(self._host, token)
            logger.info("Connected to LiveKit room: %s", room_name)

        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_connect())
        loop.close()

        self._room = room
        self._on_audio_frame = on_audio_frame

        def _on_track_subscribed(track, publication, participant):
            logger.info("Track subscribed: %s", track.kind)
            if track.kind == "audio" and on_audio_frame:
                @track.on("frame")
                def on_frame(frame, *args):
                    if on_audio_frame:
                        on_audio_frame(frame)

        room.on("track_subscribed", _on_track_subscribed)

        return {
            "name": room_name,
            "identity": identity,
            "connected": True,
            "participants": len(room.remote_participants),
        }

    def disconnect(self):
        if self._room:
            import asyncio
            async def _disc():
                await self._room.disconnect()
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_disc())
            loop.close()
            self._room = None
            logger.info("Disconnected from LiveKit room")


# ── Convenience ──────────────────────────────────────────────────────────

_client_cache: LiveKitClient | None = None


def _get_client() -> LiveKitClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = LiveKitClient()
    return _client_cache
