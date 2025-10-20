"""
이 모듈은 네이버의 스트리밍 서비스인 Chzzk를 위한 Streamlink 플러그인을 제공합니다.

토큰 기반 인증 및 주기적인 재생 목록 새로고침을 관리하기 위해 사용자 정의 HLS 스트림 처리 클래스를 정의합니다.
이 플러그인은 Chzzk의 내부 API에서 스트림 정보를 추출하여 Streamlink에서 사용할 수 있도록 합니다.
"""
import logging
import re
import time
from typing import Any, Dict, Tuple, Union, TypedDict, Optional, List
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from streamlink.exceptions import StreamError
from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.stream.hls import (
    HLSStream,
    HLSStreamReader,
    HLSStreamWorker,
    parse_m3u8,
)

log = logging.getLogger(__name__)


class ChzzkHLSStreamWorker(HLSStreamWorker):
    """Chzzk를 위한 사용자 정의 HLS 스트림 워커입니다.

    이 워커는 재시도 메커니즘을 사용하여 HLS 재생 목록 가져오기를 처리합니다. 4xx 오류가 발생하면
    부모 스트림에서 재생 목록 새로고침을 트리거하여 새 토큰을 가져옵니다.
    """

    stream: "ChzzkHLSStream"

    def _fetch_playlist(self) -> Any:
        """실패 시 재시도와 함께 HLS 재생 목록을 가져옵니다.

        반환값:
            가져온 재생 목록 콘텐츠.

        오류 발생:
            StreamError: 재시도 후에도 재생 목록을 가져올 수 없는 경우.
        """
        for attempt in range(2):  # 실패 전 한 번 재시도
            try:
                return super()._fetch_playlist()
            except StreamError as err:
                if err.response is not None and err.response.status_code >= 400:
                    self.stream.refresh_playlist()
                    log.debug(f"오류 발생 시 채널 재생 목록 강제 새로고침: {err}")
                else:
                    log.debug(f"복구할 수 없는 오류 발생: {err}")
                    raise err
        raise StreamError("재시도 후 재생 목록을 가져오는 데 실패했습니다")


class ChzzkHLSStreamReader(HLSStreamReader):
    """사용자 정의 워커를 사용하는 Chzzk용 사용자 정의 HLS 스트림 리더입니다."""

    __worker__ = ChzzkHLSStreamWorker


class ChzzkHLSStream(HLSStream):
    """토큰 새로고침 기능이 있는 Chzzk용 사용자 정의 HLS 스트림입니다.

    이 클래스는 인증 토큰이 만료되기 전에 자동으로 새로고침하여 HLS 스트림 URL을 관리합니다.
    """

    __shortname__ = "hls-chzzk"
    __reader__ = ChzzkHLSStreamReader

    _REFRESH_BEFORE = 3 * 60 * 60  # 3시간

    def __init__(self, session, url: str, channel_id: str, *args, **kwargs) -> None:
        """ChzzkHLSStream을 초기화합니다.

        Args:
            session: Streamlink 세션 객체.
            url: HLS 스트림 URL.
            channel_id: Chzzk 채널 ID.
            *args: 기본 클래스를 위한 추가 인수.
            **kwargs: 기본 클래스를 위한 추가 키워드 인수.
        """
        super().__init__(session, url, *args, **kwargs)
        self._url = url
        self._channel_id = channel_id
        self._api = ChzzkAPI(session)
        self._expire = self._get_expire_time(url)

    def refresh_playlist(self) -> None:
        """새 토큰을 얻기 위해 스트림 URL을 새로고칩니다.

        이 메서드는 최신 라이브 세부 정보를 가져와 유효한 HLS 스트림을 찾고
        현재 스트림 URL을 새 토큰으로 업데이트합니다.

        오류 발생:
            StreamError: 새 스트림 URL을 얻을 수 없는 경우.
        """
        log.debug("새 토큰을 얻기 위해 스트림 URL을 새로고칩니다.")
        datatype, data = self._api.get_live_detail(self._channel_id)
        if datatype == "error":
            raise StreamError(data)
        if not data or len(data) < 2:
            raise StreamError("스트림 URL을 새로고치는 동안 오류가 발생했습니다.")
        media, status, *_ = data
        if status != "OPEN" or media is None:
            raise StreamError("스트림 URL을 새로고치는 동안 오류가 발생했습니다.")
        for media_info in media:
            if (
                len(media_info) >= 3
                and media_info[1] == "HLS"
                and media_info[0] == "HLS"
            ):
                media_path = self._update_domain(media_info[2])
                res = self._fetch_variant_playlist(self.session, media_path)
                m3u8 = parse_m3u8(res)
                for playlist in m3u8.playlists:
                    if playlist.stream_info:
                        new_url = self._update_domain(playlist.uri)
                        self._replace_token(new_url)
                        log.debug(f"스트림 URL을 {self._url}(으)로 새로고쳤습니다")
                        self._expire = self._get_expire_time(self._url)
                        return
        raise StreamError("새로고친 재생 목록에서 유효한 HLS 스트림을 찾을 수 없습니다.")

    def _update_domain(self, url: str) -> str:
        """필요한 경우 스트림 URL의 도메인을 업데이트합니다.

        Args:
            url: 업데이트할 URL.

        반환값:
            업데이트된 URL.
        """
        if "livecloud.pstatic.net" in url:
            return url.replace("livecloud.pstatic.net", "nlive-streaming.navercdn.com")
        return url

    def _replace_token(self, new_url: str) -> None:
        """현재 스트림 URL의 토큰을 새 토큰으로 바꿉니다.

        Args:
            new_url: 업데이트된 토큰을 포함하는 새 URL.
        """
        parsed_old = urlparse(self._url)
        parsed_new = urlparse(new_url)
        qs_old = parse_qs(parsed_old.query)
        qs_new = parse_qs(parsed_new.query)
        # 'hdnts' 매개변수를 새 토큰으로 교체
        if "hdnts" in qs_new:
            qs_old["hdnts"] = qs_new.get("hdnts")
        new_query = urlencode(qs_old, doseq=True)
        self._url = urlunparse(parsed_old._replace(query=new_query))

    def _get_expire_time(self, url: str) -> Optional[int]:
        """URL의 'exp' 매개변수에서 만료 시간을 추출합니다.

        Args:
            url: 'exp' 쿼리 매개변수가 있는 스트림 URL.

        반환값:
            정수 형태의 만료 타임스탬프, 찾을 수 없는 경우 None.
        """
        parsed_url = urlparse(url)
        qs = parse_qs(parsed_url.query)
        exp_values = qs.get("exp")
        if exp_values and exp_values[0].isdigit():
            return int(exp_values[0])
        return None

    def _should_refresh(self) -> bool:
        """스트림 URL을 새로고쳐야 하는지 결정합니다.

        반환값:
            토큰이 만료되기 직전이면 True, 그렇지 않으면 False.
        """
        return (
            self._expire is not None
            and time.time() >= self._expire - self._REFRESH_BEFORE
        )

    @property
    def url(self) -> str:
        if self._should_refresh():
            self.refresh_playlist()
        return self._url


class LiveDetail(TypedDict):
    status: str
    liveId: int
    liveTitle: Union[str, None]
    liveCategory: Union[str, None]
    adult: bool
    channel: str
    media: List[Dict[str, str]]


@dataclass
class ChzzkAPI:
    """Chzzk 플랫폼을 위한 API 클라이언트입니다."""

    session: Any
    _CHANNELS_LIVE_DETAIL_URL: str = (
        "https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
    )

    def _query_api(
        self, url: str, *schemas: validate.Schema
    ) -> Tuple[str, Union[Dict[str, Any], str]]:
        """Chzzk API에 쿼리를 수행합니다.

        Args:
            url: API 엔드포인트 URL.
            *schemas: 응답에 대한 유효성 검사 스키마.

        반환값:
            상태('success' 또는 'error')와 응답 데이터 또는 오류 메시지를 포함하는 튜플.
        """
        response = self.session.http.get(
            url,
            acceptable_status=(200, 404),
            headers={"Referer": "https://chzzk.naver.com/"},
            schema=validate.Schema(
                validate.parse_json(),
                validate.any(
                    validate.all(
                        {
                            "code": int,
                            "message": str,
                        },
                        validate.transform(lambda data: ("error", data["message"])),
                    ),
                    validate.all(
                        {
                            "code": 200,
                            "content": None,
                        },
                        validate.transform(lambda _: ("success", None)),
                    ),
                    validate.all(
                        {
                            "code": 200,
                            "content": dict,
                        },
                        validate.get("content"),
                        *schemas,
                        validate.transform(lambda data: ("success", data)),
                    ),
                ),
            ),
        )
        return response

    def get_live_detail(self, channel_id: str) -> Tuple[str, Union[LiveDetail, str]]:
        """주어진 채널의 라이브 스트림 세부 정보를 가져옵니다.

        Args:
            channel_id: 채널 ID.

        반환값:
            상태와 라이브 세부 정보 또는 오류 메시지를 포함하는 튜플.
        """
        return self._query_api(
            self._CHANNELS_LIVE_DETAIL_URL.format(channel_id=channel_id),
            {
                "status": str,
                "liveId": int,
                "liveTitle": validate.any(str, None),
                "liveCategory": validate.any(str, None),
                "adult": bool,
                "channel": validate.all(
                    {"channelName": str},
                    validate.get("channelName"),
                ),
                "livePlaybackJson": validate.none_or_all(
                    str,
                    validate.parse_json(),
                    {
                        "media": [
                            validate.all(
                                {
                                    "mediaId": str,
                                    "protocol": str,
                                    "path": validate.url(),
                                },
                                validate.union_get(
                                    "mediaId",
                                    "protocol",
                                    "path",
                                ),
                            ),
                        ],
                    },
                    validate.get("media"),
                ),
            },
            validate.union_get(
                "livePlaybackJson",
                "status",
                "liveId",
                "channel",
                "liveCategory",
                "liveTitle",
                "adult",
            ),
        )


@pluginmatcher(
    name="live",
    pattern=re.compile(
        r"https?://chzzk\.naver\.com/live/(?P<channel_id>[^/?]+)",
    ),
)
class Chzzk(Plugin):
    """Chzzk 라이브 스트림을 위한 Streamlink 플러그인입니다."""

    _STATUS_OPEN = "OPEN"

    def __init__(self, *args, **kwargs) -> None:
        """Chzzk 플러그인을 초기화합니다."""
        super().__init__(*args, **kwargs)
        self._api = ChzzkAPI(self.session)
        self.author: Optional[str] = None
        self.category: Optional[str] = None
        self.title: Optional[str] = None

    def _get_live(self, channel_id: str) -> Optional[Dict[str, HLSStream]]:
        """채널의 라이브 스트림을 검색합니다.

        Args:
            channel_id: 채널 ID.

        반환값:
            사용 가능한 HLS 스트림의 딕셔너리, 스트림을 사용할 수 없거나 오류가 발생하면 None.
        """
        datatype, data = self._api.get_live_detail(channel_id)
        if datatype == "error":
            log.error(data)
            return None
        if data is None:
            return None

        if len(data) < 7:
            log.error("API에서 불완전한 데이터를 받았습니다.")
            return None

        media, status, self.id, self.author, self.category, self.title, adult = data
        if status != self._STATUS_OPEN:
            log.error("스트림을 사용할 수 없습니다")
            return None
        if media is None:
            log.error(f"이 스트림은 {'성인 전용이거나' if adult else '사용할 수 없습니다'}")
            return None

        streams = {}
        for media_info in media:
            if (
                len(media_info) >= 3
                and media_info[1] == "HLS"
                and media_info[0] == "HLS"
            ):
                media_path = self._update_domain(media_info[2])
                hls_streams = ChzzkHLSStream.parse_variant_playlist(
                    self.session,
                    media_path,
                    channel_id=channel_id,
                )
                if hls_streams:
                    streams.update(hls_streams)
        if not streams:
            log.error("유효한 HLS 스트림을 찾을 수 없습니다.")
            return None
        return streams

    def _update_domain(self, url: str) -> str:
        """필요한 경우 스트림 URL의 도메인을 업데이트합니다.

        Args:
            url: 업데이트할 URL.

        반환값:
            업데이트된 URL.
        """
        if "livecloud.pstatic.net" in url:
            return url.replace("livecloud.pstatic.net", "nlive-streaming.navercdn.com")
        return url

    def _get_streams(self) -> Optional[Dict[str, HLSStream]]:
        """스트림을 발견하는 메인 메서드입니다.

        이 메서드는 Streamlink에 의해 호출되어 URL에 사용 가능한 스트림을 가져옵니다.

        반환값:
            스트림의 딕셔너리, 또는 None.
        """
        if self.matches["live"]:
            return self._get_live(self.match["channel_id"])
        return None


__plugin__ = Chzzk
