import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot_plugin_stealer.core.events.emoji_delivery import send_qq_image_as_sticker
from astrbot_plugin_stealer.core.events.event_handler import EventHandler
from astrbot_plugin_stealer.core.events.platform_detector import PlatformDetector


def event_for_segments(segments):
    return SimpleNamespace(
        get_platform_name=lambda: "milky",
        message_obj=SimpleNamespace(
            raw_message={
                "event_type": "message_receive",
                "data": {"segments": segments},
            }
        ),
    )


@pytest.mark.parametrize("subtype,expected", [("sticker", True), ("normal", False)])
def test_milky_sticker_detection(subtype, expected):
    segments = [
        {
            "type": "image",
            "data": {"sub_type": subtype, "temp_url": "https://example.com/a.gif"},
        }
    ]
    event = event_for_segments(segments)
    image = SimpleNamespace(file="https://example.com/a.gif", url="")
    assert (
        PlatformDetector().check_platform_emoji_metadata(image, event, img_index=0)
        is expected
    )


def test_multiple_images_keep_their_own_subtypes():
    segments = [
        {"type": "text", "data": {"text": "hello"}},
        {"type": "image", "data": {"sub_type": "normal"}},
        {"type": "image", "data": {"sub_type": "sticker"}},
    ]
    event = event_for_segments(segments)
    handler = EventHandler.__new__(EventHandler)
    handler._platform_detector = PlatformDetector()
    images, file_map = handler._extract_raw_image_data(event)
    assert len(images) == 2
    detector = PlatformDetector()
    image = SimpleNamespace(file="", url="")
    assert not detector.check_platform_emoji_metadata(
        image, event, img_index=0, image_segments=images, image_file_map=file_map
    )
    assert detector.check_platform_emoji_metadata(
        image, event, img_index=1, image_segments=images, image_file_map=file_map
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [True, False])
@pytest.mark.parametrize("force_gif", [True, False])
async def test_milky_sends_sticker_with_original_or_converted_bytes(
    tmp_path, group, force_gif
):
    path = tmp_path / "animated.gif"
    original = b"GIF89a-original-bytes"
    path.write_bytes(original)
    event = SimpleNamespace(
        get_platform_name=lambda: "milky",
        get_group_id=lambda: "300" if group else "",
        get_sender_id=lambda: "200",
        bot=SimpleNamespace(call_action=AsyncMock()),
    )
    plugin = SimpleNamespace(
        send_meme_as_qq_sticker=True,
        send_meme_as_gif=force_gif,
        image_render_service=SimpleNamespace(
            file_to_gif_base64=AsyncMock(return_value="Z2lm")
        ),
    )
    assert await send_qq_image_as_sticker(event, str(path), plugin=plugin)
    call = event.bot.call_action.call_args
    assert call.args == ("send_group_message" if group else "send_private_message",)
    assert call.kwargs["group_id" if group else "user_id"] == (300 if group else 200)
    image = call.kwargs["message"][0]["data"]
    assert image["sub_type"] == "sticker"
    assert image["uri"] == "base64://" + (
        "Z2lm" if force_gif else base64.b64encode(original).decode("ascii")
    )


@pytest.mark.asyncio
async def test_milky_disabled_and_failure_allow_fallback(tmp_path):
    path = tmp_path / "meme.png"
    path.write_bytes(b"image")
    event = SimpleNamespace(
        get_platform_name=lambda: "milky",
        get_group_id=lambda: "",
        get_sender_id=lambda: "200",
        bot=SimpleNamespace(call_action=AsyncMock(side_effect=RuntimeError())),
    )
    assert not await send_qq_image_as_sticker(
        event, str(path), plugin=SimpleNamespace(send_meme_as_qq_sticker=False)
    )
    event.bot.call_action.assert_not_awaited()
    assert not await send_qq_image_as_sticker(event, str(path))
