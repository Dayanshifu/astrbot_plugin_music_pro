import os
import time
import aiohttp
import asyncio
import urllib.parse
from typing import Dict, Any, Optional, List
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path

from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import Plain, Record

class API:
    def __init__(self, api_url: str, session: aiohttp.ClientSession, apikey: str):
        self.session = session
        self.base_url = "https://music.pmhs.top"
        self.base_url_net = api_url.rstrip("/")
        self.apikey = apikey
        self.new_api_base = "https://api.nycnm.cn/API/diange.php"

    async def search_songs(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        params = {
            "msg": keyword,
            "apikey": self.apikey
        }
        async with self.session.get(self.new_api_base, params=params) as r:
            r.raise_for_status()
            data = await r.json()
        
        if not data.get("success"):
            return []
        
        converted_songs = []
        for i, song in enumerate(data.get("data", [])[:limit], 1):
            converted_song = {
                "id": int(song["id"]),
                "name": song["music_name"],
                "artists": [{"name": song["artist"]}],
                "album": {"name": "未知专辑"},
                "row_number": i,
                "original_id": song["id"],
                "is_163": False
            }
            converted_songs.append(converted_song)
        return converted_songs

    async def get_audio_url(self, song_id: str) -> Optional[str]:
        params = {
            "msg": "",
            "id": song_id,
            "apikey": self.apikey
        }
        async with self.session.get(self.new_api_base, params=params) as r:
            r.raise_for_status()
            data = await r.json()
        
        if data.get("success") and data.get("data", {}).get("music_link"):
            return data["data"]["music_link"]
        return None

    async def get_song_details_net(self, song_id: int) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url_net}/song/detail?ids={str(song_id)}"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
            return data["songs"][0] if data.get("songs") else None
            
    async def search_songs_net(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url_net}/search?keywords={urllib.parse.quote(keyword)}&limit={limit}&type=1"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
            return data.get("result", {}).get("songs", [])
            
    async def get_audio_url_net(self, song_id: int, quality: str) -> Optional[str]:
        qualities_to_try = list(dict.fromkeys([quality, "exhigh", "higher", "standard"]))
        for q in qualities_to_try:
            url = f"{self.base_url_net}/song/url/v1?id={str(song_id)}&level={q}"
            async with self.session.get(url) as r:
                r.raise_for_status()
                data = await r.json()
                audio_info = data.get("data", [{}])[0]
                if audio_info.get("url"):
                    return audio_info["url"]
        return None
        
    async def get_163_audio_url(self, song_id: int) -> Optional[str]:
        url = f"{self.base_url_net}/song/url?id={str(song_id)}"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
            audio_info = data.get("data", [{}])[0]
            if audio_info.get("url"):
                return audio_info["url"]
        return None
        
    async def download_image(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        async with self.session.get(url) as r:
            if r.status == 200:
                return await r.read()
        return None
        
    def format_163_song(self, song_data: dict, insert_index: int) -> dict:
        return {
            "id": song_data["id"],
            "name": song_data["name"],
            "artists": song_data["artists"],
            "album": {"name": song_data["album"]["name"]},
            "row_number": insert_index,
            "original_id": song_data["id"],
            "is_163": True
        }

@register(
    "astrbot_plugin_music_pro", 
    "Dayanshifu", 
    "高级点歌", 
    "1.0.3",
    "https://github.com/Dayanshifu/astrbot_plugin_music_pro"
)
class Main(Star):
    def __init__(self, context:Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        self.waiting_users: Dict[str, Dict[str, Any]] = {}
        self.song_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        self.api = API(self.config["api_url"], self.http_session, self.config["apikey"])
        self.apikey = self.config["apikey"]
        self.cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self):
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("Music plugin: Background cleanup task started.")

    async def terminate(self):
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                logger.info("Music plugin: Background cleanup task cancelled.")
        
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("Music plugin: HTTP session closed.")

    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            expired_sessions = []
            
            for session_id, user_session in self.waiting_users.items():
                if user_session['expire'] < now:
                    expired_sessions.append((session_id, user_session['key']))
            
            if expired_sessions:
                logger.info(f"Music plugin: Cleaning up {len(expired_sessions)} expired session(s).")
                for session_id, cache_key in expired_sessions:
                    if session_id in self.waiting_users:
                        del self.waiting_users[session_id]
                    if cache_key in self.song_cache:
                        del self.song_cache[cache_key]

    @filter.command("点歌", alias={"music", "唱歌", "唱"})
    async def cmd_handler(self, event: AstrMessageEvent, a1: str = "", a2: str = "", a3: str = "", a4: str = "", a5: str = "", a6: str = "", a7: str = "", a8: str = "", a9: str = "", a10: str = ""):
        if not a1.strip():
            await event.send(MessageChain([Plain("请告诉我想听什么歌喵~ 例如：点歌 青花")]))
            return
        await self.search_and_show(event,(a1.strip()+' '+a2.strip()+' '+a3.strip()+' '+a4.strip()+' '+a5.strip()+' '+a6.strip()+' '+a7.strip()+' '+a8.strip()+' '+a9.strip()+' '+a10.strip()).strip())

    @filter.regex(r"^\d+$", priority=999)
    async def number_selection_handler(self, event: AstrMessageEvent):
        session_id = event.get_session_id()
        if session_id not in self.waiting_users:
            return

        user_session = self.waiting_users[session_id]
        if time.time() > user_session["expire"]:
            return

        try:
            num = int(event.message_str.strip())
        except ValueError:
            return

        limit = self.config.get("search_limit", 10)
        if not (1 <= num <= limit + 1):
            return

        event.stop_event()
        await self.play_selected_song(event, user_session["key"], num)
        
        if session_id in self.waiting_users:
            del self.waiting_users[session_id]

    async def search_and_show_net(self, event: AstrMessageEvent, keyword: str, title: str=''):
        try:
            songs = await self.api.search_songs_net(keyword, 1)
        except Exception as e:
            logger.error(f"Netease Music plugin: API search failed. Error: {e!s}")
            await event.send(MessageChain([Plain(f"请求过于频繁，慢点啊喵！")]))
            return

        if not songs:
            await event.send(MessageChain([Plain(f"找不到「{title}」这首歌喵... ")]))
            return

        cache_key = f"{event.get_session_id()}_{int(time.time())}"
        self.song_cache[cache_key] = songs

        selected_song = songs[0]
        song_id = selected_song["id"]
        
        try:
            song_details = await self.api.get_song_details_net(song_id)
            if not song_details:
                raise ValueError("无法获取歌曲详细信息。")

            audio_url = await self.api.get_audio_url_net(song_id, self.config["quality"])
            if not audio_url:
                await event.send(MessageChain([Plain(f"喵~ 这首歌可能需要VIP或者没有版权，暂时不能为主人播放呢...")]))
                return

            title = song_details.get("name", "")
            artists = " / ".join(a["name"] for a in song_details.get("ar", []))
            album = song_details.get("al", {}).get("name", "未知专辑")
            cover_url = song_details.get("al", {}).get("picUrl", "")
            duration_ms = song_details.get("dt", 0)
            dur_str = f"{duration_ms//60000}:{(duration_ms%60000)//1000:02d}"

            await self._send_song_messages_net(event, 1, title, artists, album, dur_str, cover_url, audio_url)

        except Exception as e:
            logger.error(f"Netease Music plugin: Failed to play song {song_id}. Error: {e!s}")
            await event.send(MessageChain([Plain(f"呜...获取歌曲信息的时候失败了喵...")]))
        finally:
            if cache_key in self.song_cache:
                del self.song_cache[cache_key]

    async def _send_song_messages_net(self, event: AstrMessageEvent, num: int, title: str, artists: str, album: str, dur_str: str, cover_url: str, audio_url: str):
        try:
            await event.send(MessageChain([Record(file=audio_url)]))
        except Exception as e:
            logger.error(f"Music plugin: Failed to send audio. Error: {e!s}")
            await event.send(MessageChain([Plain("呜...播放歌曲的时候失败了喵...可能是音频格式不支持呢")]))
            
    async def search_and_show(self, event: AstrMessageEvent, keyword: str):
        if keyword=="兰州一中校歌":
            try:
                await event.send(MessageChain([Record(file=os.path.join(get_astrbot_plugin_path(), "astrbot_plugin_music_pro", "1.mp3"))]))
            except Exception as e:
                logger.error(f"Music plugin: Failed to send audio. Error: {e!s}")
                await event.send(MessageChain([Plain("呜...播放歌曲的时候失败了喵...可能是音频格式不支持呢")]))
            return
        if keyword=="皇后大道东":
            try:
                await event.send(MessageChain([Record(file=os.path.join(get_astrbot_plugin_path(), "astrbot_plugin_music_pro", "皇后大道东.mp3"))]))
            except Exception as e:
                logger.error(f"Music plugin: Failed to send audio. Error: {e!s}")
                await event.send(MessageChain([Plain("呜...播放歌曲的时候失败了喵...可能是音频格式不支持呢")]))
            return
            
        try:
            songs = await self.api.search_songs(keyword, self.config["search_limit"])
            netease_songs = await self.api.search_songs_net(keyword, 1)
        except Exception as e:
            logger.error(f"Music plugin: API search failed. Error: {e!s}")
            await event.send(MessageChain([Plain(f"呜喵...连接断了...请稍后再试喵？")]))
            return

        if not songs:
            await event.send(MessageChain([Plain(f"找不到「{keyword}」这首歌喵... ")]))
            return
        
        insert_netease_song = None
        if netease_songs and len(netease_songs) > 0:
            insert_netease_song = self.api.format_163_song(netease_songs[0], len(songs) + 1)
            songs.append(insert_netease_song)

        for idx, song in enumerate(songs, 1):
            song["row_number"] = idx

        cache_key = f"{event.get_session_id()}_{int(time.time())}"
        self.song_cache[cache_key] = songs

        response_lines = [f"找到了 {len(songs)} 首歌曲喵！请回复数字喵！"]
        for song in songs:
            row_num = song["row_number"]
            artists = " / ".join(a["name"] for a in song.get("artists", []))
            album = song.get("album", {}).get("name", "未知专辑")
            song_tag = "" if song.get("is_163", False) else ""
            response_lines.append(f"{row_num}. {song_tag}{song['name']} - {artists}")

        await event.send(MessageChain([Plain("\n".join(response_lines))]))
        self.waiting_users[event.get_session_id()] = {"key": cache_key, "expire": time.time() + 60}

    async def play_selected_song(self, event: AstrMessageEvent, cache_key: str, num: int):
        if cache_key not in self.song_cache:
            await event.send(MessageChain([Plain("超时喵！")]))
            return

        songs = self.song_cache[cache_key]
        if not (1 <= num <= len(songs)):
             await event.send(MessageChain([Plain("不对不对！请输入正确的数字喵！")]))
             return
             
        selected_song = songs[num - 1]
        original_id = selected_song["original_id"]
        
        try:
            if selected_song.get("is_163", False):
                audio_url = await self.api.get_163_audio_url(int(original_id))
            else:
                audio_url = await self.api.get_audio_url(original_id)
                
            if not audio_url:
                await event.send(MessageChain([Plain(f"喵~ 这首歌可能暂时不能播放呢...")]))
                return

            title = selected_song.get("name", "")
            artists = " / ".join(a["name"] for a in selected_song.get("artists", []))
            album = selected_song.get("album", {}).get("name", "未知专辑")

            await self._send_song_messages(event, num, title, artists, album, audio_url)

        except Exception as e:
            logger.error(f"Music plugin: Failed to play song {original_id}. Error: {e!s}")
            await event.send(MessageChain([Plain(f"失败了喵，错误原因：{str(e)[:20]}")]))
        finally:
            if cache_key in self.song_cache:
                del self.song_cache[cache_key]

    async def _send_song_messages(self, event: AstrMessageEvent, num: int, title: str, artists: str, album: str, audio_url: str):
        detail_text = f"收到！正在为你播放：{title} - {artists}"
        info_components = [Plain(detail_text)]

        await event.send(MessageChain(info_components))
        
        try:
            await event.send(MessageChain([Record(file=audio_url)]))
        except Exception as e:
            logger.error(f"播放普通歌曲失败，尝试网易云接口：{e!s}")
            await self.search_and_show_net(event, title+' '+artists, title=title)