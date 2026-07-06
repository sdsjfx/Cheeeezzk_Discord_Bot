version = "dev\_version \_ V1.2.4"


import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import aiohttp
import json
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))
CM_CHECK_INTERVAL = int(os.getenv("CM_CHECK_INTERVAL", 300))

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"

kst = timezone(timedelta(hours=9))

# -------------------------
# JSON 로딩 및 함수
# -------------------------

def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for key in default:
            if key not in data:
                data[key] = default[key]

        return data

    except Exception as e:
        print(f"{path} 로딩 실패 → 초기화:", e)
        save_json(path, default)
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def to_unix_kst(dt_str: str):
    if "-" in dt_str:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    else:
        dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
    dt = dt.replace(tzinfo=kst)
    return int(dt.timestamp())


def extract_live_event_key(item, detail=None):
    if not isinstance(item, dict):
        return None

    candidates = []
    if detail and isinstance(detail, dict):
        candidates.append(detail.get("liveId"))
        live_info = detail.get("liveInfo")
        if isinstance(live_info, dict):
            candidates.append(live_info.get("liveId"))

    live_info = item.get("liveInfo")
    if isinstance(live_info, dict):
        candidates.append(live_info.get("liveId"))

    candidates.append(item.get("liveId"))

    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)

    return None


def build_action_view(channel_id, include_live=False, replay_url=None, replay_disabled=False):
    view = discord.ui.View(timeout=None)
    if include_live:
        view.add_item(
            discord.ui.Button(
                label="방송보기",
                url=f"https://chzzk.naver.com/live/{channel_id}",
                style=discord.ButtonStyle.link
            )
        )
    view.add_item(
        discord.ui.Button(
            label="다시보기",
            url=replay_url or f"https://chzzk.naver.com/{channel_id}",
            style=discord.ButtonStyle.link,
            disabled=replay_disabled
        )
    )
    view.add_item(
        discord.ui.Button(
            label="채널로 가기",
            url=f"https://chzzk.naver.com/{channel_id}",
            style=discord.ButtonStyle.link
        )
    )
    return view

config = load_json(CONFIG_FILE, {
    "notify_channel": None,
    "NID_AUT": None,
    "NID_SES": None
})

state = load_json(STATE_FILE, {
    "last_live": {},
    "last_title": {},
    "last_category": {},
    "last_tags": {},
    "last_live_event_id": {},
    "replay_tracking": {},
    "community_seen_comments": []
})

default_config = {
    "notify_channel": None,
    "NID_AUT": None,
    "NID_SES": None
}

# config.json 누락된 키 자동 생성 및 타입 보정
for key, value in default_config.items():
    if key not in config:
        config[key] = value
if not isinstance(config["notify_channel"], (int, type(None))):
    config["notify_channel"] = None
if not isinstance(config["NID_AUT"], (str, type(None))):
    config["NID_AUT"] = None
if not isinstance(config["NID_SES"], (str, type(None))):
    config["NID_SES"] = None

# state.json 누락된 키 자동 생성
for key in ["last_live", "last_title", "last_category", "last_tags", "last_live_event_id", "replay_tracking"]:
    if key not in state or not isinstance(state[key], dict):
        state[key] = {}
if "community_seen_comments" not in state or not isinstance(state["community_seen_comments"], list):
    state["community_seen_comments"] = []

# -------------------------
# Discord
# -------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

session = None

# -------------------------
# 계정 정보 호출
# -------------------------

async def login_account_info():
    global session

    if session is None or session.closed:
        session = aiohttp.ClientSession()

    url = "https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://chzzk.naver.com/",
        "Origin": "https://game.naver.com",
        "Cookie": f"NID_AUT={config['NID_AUT']}; NID_SES={config['NID_SES']}"
    }

    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return None

            data = await resp.json()
            if data.get("code") != 200:
                return None

            return data.get("content", {})
    except Exception as e:
        print("LOGIN ACCOUNT INFO ERROR:", e)
        return None

# -------------------------
# live-detail v2 호출
# -------------------------

async def fetch_live_detail(channel_id):
    global session

    if session is None or session.closed:
        session = aiohttp.ClientSession()

    url = f"https://api.chzzk.naver.com/service/v2/channels/{channel_id}/live-detail"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://chzzk.naver.com/",
        "Origin": "https://chzzk.naver.com",
        "Cookie": f"NID_AUT={config['NID_AUT']}; NID_SES={config['NID_SES']}"
    }

    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return None

            data = await resp.json()
            if data.get("code") != 200:
                return None

            return data.get("content", {})
    except Exception as e:
        print("LIVE DETAIL ERROR:", e)
        return None

# -------------------------
# followings/live 호출
# -------------------------

async def fetch_live_followings():
    global session

    if session is None or session.closed:
        session = aiohttp.ClientSession()

    if not config["NID_AUT"] or not config["NID_SES"]:
        print("로그인 정보 없음")
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://chzzk.naver.com/",
        "Origin": "https://chzzk.naver.com",
        "Cookie": f"NID_AUT={config['NID_AUT']}; NID_SES={config['NID_SES']}"
    }

    url = "https://api.chzzk.naver.com/service/v1/channels/followings/live"

    try:
        async with session.get(url, headers=headers, timeout=15) as resp:

            now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n----{now_time}----")
            print("LIVE API STATUS:", resp.status)

            if resp.status != 200:
                return None

            data = await resp.json()
            print("LIVE API CODE:", data.get("code"))

            if data.get("code") != 200:
                return None

            return data["content"]["followingList"]

    except Exception as e:
        print("LIVE FETCH ERROR:", e)
        return None


async def fetch_community_posts():
    global session

    if session is None or session.closed:
        session = aiohttp.ClientSession()

    if not config["NID_AUT"] or not config["NID_SES"]:
        print("로그인 정보 없음")
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://chzzk.naver.com/",
        "Origin": "https://chzzk.naver.com",
        "Cookie": f"NID_AUT={config['NID_AUT']}; NID_SES={config['NID_SES']}"
    }

    url = "https://api.chzzk.naver.com/service/v1/home/following/channel-post"

    try:
        async with session.get(url, headers=headers, timeout=15) as resp:

            now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n----{now_time}----")
            print("COMMUNITY API STATUS:", resp.status)

            if resp.status != 200:
                return None

            data = await resp.json()
            print("COMMUNITY API CODE:", data.get("code"))

            if data.get("code") != 200:
                return None

            return data.get("content", {}).get("channelPosts", [])

    except Exception as e:
        print("COMMUNITY FETCH ERROR:", e)
        return None


async def fetch_replay_videos(channel_id):
    global session

    if session is None or session.closed:
        session = aiohttp.ClientSession()

    if not config["NID_AUT"] or not config["NID_SES"]:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://chzzk.naver.com/",
        "Origin": "https://chzzk.naver.com",
        "Cookie": f"NID_AUT={config['NID_AUT']}; NID_SES={config['NID_SES']}"
    }

    url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}/videos?sortType=LATEST"

    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return []

            data = await resp.json()
            if data.get("code") != 200:
                return []

            return data.get("content", {}).get("data", [])
    except Exception as e:
        print("REPLAY FETCH ERROR:", e)
        return []

# -------------------------
# 체크 루프
# -------------------------

async def check_loop():
    await client.wait_until_ready()

    while not client.is_closed():
        loop_start = datetime.now()

        if not config.get("notify_channel"):
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        live_list = await fetch_live_followings()

        if live_list is None:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        disc_channel = client.get_channel(config["notify_channel"])
        if not disc_channel:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        now_ts = int(datetime.now().timestamp())
        replay_tracking = state.get("replay_tracking", {})
        for channel_id, tracker in list(replay_tracking.items()):
            expires_at = tracker.get("expires_at", 0)
            if expires_at <= now_ts:
                replay_tracking.pop(channel_id, None)
                continue

            if tracker.get("activated"):
                replay_tracking.pop(channel_id, None)
                continue

            if tracker.get("wait_until") and now_ts < tracker["wait_until"]:
                continue

            replay_videos = await fetch_replay_videos(channel_id)
            if not replay_videos:
                continue

            seen_ids = set(tracker.get("seen_video_ids", []))
            for item in replay_videos:
                if item.get("videoType") != "REPLAY":
                    continue

                video_No = item.get("videoNo")
                if not video_No or video_No in seen_ids:
                    continue

                replay_url = f"https://chzzk.naver.com/video/{video_No}"
                seen_ids.add(video_No)

                target_channel = None
                target_message = None
                message_id = tracker.get("message_id")
                if message_id:
                    try:
                        target_channel = client.get_channel(tracker.get("channel_id")) or disc_channel
                        if target_channel:
                            target_message = await target_channel.fetch_message(message_id)
                    except Exception as e:
                        print("REPLAY BUTTON UPDATE ERROR:", e)

                if target_message:
                    await target_message.edit(
                        view=build_action_view(channel_id, replay_url=replay_url, replay_disabled=False)
                    )
                print(f"**{channel_id}** 다시보기 버튼 활성화: {video_No}")

                tracker["activated"] = True
                tracker["replay_url"] = replay_url
                tracker["seen_video_ids"] = list(seen_ids)
                replay_tracking[channel_id] = tracker
                state["replay_tracking"] = replay_tracking
                save_json(STATE_FILE, state)
                break

            if not tracker.get("activated") and seen_ids != set(tracker.get("seen_video_ids", [])):
                tracker["seen_video_ids"] = list(seen_ids)
                replay_tracking[channel_id] = tracker
                state["replay_tracking"] = replay_tracking
                save_json(STATE_FILE, state)

        # 루프 시작 전 이전 방송 중 목록 확정
        previous_live_ids = set(
            cid for cid, live in state["last_live"].items() if live
        )

        current_live_ids = set()

        for item in live_list:
            channel_id = item["channelId"]
            notification = item["channel"]["personalData"]["following"]["notification"]

            # 알림 꺼진 스트리머는 current에만 추가하고 건너뜀
            if not notification:
                current_live_ids.add(channel_id)
                continue

            channel_name = item["channel"]["channelName"]
            channel_icon = item["channel"].get("channelImageUrl")
            live_info = item.get("liveInfo", {})

            title = live_info.get("liveTitle")
            category = live_info.get("liveCategoryValue") or "없음"

            was_live = state["last_live"].get(channel_id, False)
            current_live_ids.add(channel_id)

            # =========================
            # 🟢 방송 시작
            # =========================
            if not was_live:
                detail = await fetch_live_detail(channel_id)
                event_key = extract_live_event_key(item, detail)
                tags = []
                thumbnail = None
                open_ts = None

                if detail:
                    raw_tags = detail.get("tags")
                    tags = raw_tags if isinstance(raw_tags, list) else []
                    thumbnail = detail.get("liveImageUrl")
                    if thumbnail:
                        thumbnail = thumbnail.replace("{type}", "720")
                    open_date_str = detail.get("openDate")
                    if open_date_str:
                        open_ts = to_unix_kst(open_date_str)

                if event_key and state.get("last_live_event_id", {}).get(channel_id) == event_key:
                    state["last_live"][channel_id] = True
                    state["last_title"][channel_id] = title
                    state["last_category"][channel_id] = category
                    state["last_tags"][channel_id] = tags
                    state["last_live_event_id"][channel_id] = event_key
                    save_json(STATE_FILE, state)
                    continue

                embed = discord.Embed(
                    title=title,
                    url=f"https://chzzk.naver.com/live/{channel_id}",
                    description=f"**{channel_name}** 님이 라이브 중입니다!",
                    color=65441
                )
                embed.set_author(
                    name=channel_name,
                    url=f"https://chzzk.naver.com/{channel_id}",
                    icon_url=channel_icon
                )
                embed.add_field(name="카테고리", value=category, inline=True)
                if open_ts:
                    embed.add_field(name="방송 시작 시간", value=f"<t:{open_ts}:t>", inline=True)
                else:
                    embed.add_field(name="방송 시작 시간", value="시간 정보 없음", inline=True)
                if tags:
                    embed.add_field(name="태그", value=", ".join(tags), inline=False)
                if thumbnail:
                    embed.set_image(url=thumbnail)
                embed.set_footer(text="Cheeeezzk")
                embed.timestamp = discord.utils.utcnow()

                await disc_channel.send(embed=embed, view=build_action_view(channel_id, include_live=True))
                print(f"**{channel_name}** 라이브 시작")

                state["last_live"][channel_id] = True
                state["last_title"][channel_id] = title
                state["last_category"][channel_id] = category
                state["last_tags"][channel_id] = tags
                if event_key:
                    state["last_live_event_id"][channel_id] = event_key
                else:
                    state["last_live_event_id"].pop(channel_id, None)
                save_json(STATE_FILE, state)
                continue

            # =========================
            # 🔵 방송 정보 변경
            # =========================
            old_title = state["last_title"].get(channel_id)
            old_category = state["last_category"].get(channel_id)
            old_tags = state["last_tags"].get(channel_id, [])

            title_changed = title != old_title
            category_changed = category != old_category

            tags = old_tags
            if title_changed or category_changed:
                detail = await fetch_live_detail(channel_id)
                if detail:
                    raw_tags = detail.get("tags")
                    tags = raw_tags if isinstance(raw_tags, list) else []

            tags_changed = sorted(old_tags) != sorted(tags)

            changes = []
            if title_changed:
                changes.append(("제목", old_title, title))
            if category_changed:
                changes.append(("카테고리", old_category, category))
            if tags_changed:
                changes.append(("태그", ", ".join(old_tags), ", ".join(tags)))

            if changes:
                embed = discord.Embed(
                    title=f"{channel_name}님의 방송 정보가 변경되었습니다!",
                    url=f"https://chzzk.naver.com/live/{channel_id}",
                    color=16776960
                )
                embed.set_author(name=channel_name, icon_url=channel_icon)

                for name, old, new in changes:
                    embed.add_field(
                        name=name,
                        value=f"```\n이전:\n{old or '없음'}\n현재:\n{new or '없음'}\n```",
                        inline=False
                    )

                embed.set_footer(text="Cheeeezzk")
                embed.timestamp = discord.utils.utcnow()

                await disc_channel.send(embed=embed)
                print(f"**{channel_name}** 방송정보변경")

            state["last_live"][channel_id] = True
            state["last_title"][channel_id] = title
            state["last_category"][channel_id] = category
            state["last_tags"][channel_id] = tags

        # =========================
        # ⚫ 방송 종료
        # =========================
        ended_streams = previous_live_ids - current_live_ids

        for channel_id in ended_streams:
            detail = await fetch_live_detail(channel_id)

            if detail:
                channel_name = detail.get("channel", {}).get("channelName", "알 수 없음")
                channel_icon = detail.get("channel", {}).get("channelImageUrl")
                open_date_str = detail.get("openDate")
                close_date_str = detail.get("closeDate")

                if open_date_str and close_date_str:
                    open_ts = to_unix_kst(open_date_str)
                    close_ts = to_unix_kst(close_date_str)
                    uptime_seconds = close_ts - open_ts
                    hours, remainder = divmod(uptime_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    uptime_str = f"{hours}시간 {minutes}분 {seconds}초"
                    value = f"<t:{open_ts}:t> ~ <t:{close_ts}:t>"
                else:
                    uptime_str = "시간 정보 없음"
                    value = "시간 정보 없음"

                embed = discord.Embed(
                    title=f"{channel_name}님의 방송이 종료되었습니다!",
                    url=f"https://chzzk.naver.com/{channel_id}",
                    description=f"**{channel_name}** 님이 라이브를 종료했습니다!",
                    color=16718891
                )
                embed.set_author(
                    name=channel_name,
                    url=f"https://chzzk.naver.com/{channel_id}",
                    icon_url=channel_icon
                )
                embed.add_field(name="방송 시간", value=value, inline=True)
                embed.add_field(name="업타임", value=uptime_str, inline=True)
                embed.set_footer(text="Cheeeezzk")
                embed.timestamp = discord.utils.utcnow()

                initial_replay_url = None
                initial_replay_id = None
                replay_videos = await fetch_replay_videos(channel_id)
                if replay_videos:
                    for replay_item in replay_videos:
                        if replay_item.get("videoType") != "REPLAY":
                            continue
                        initial_replay_id = replay_item.get("videoId")
                        if initial_replay_id:
                            initial_replay_url = f"https://chzzk.naver.com/video/{initial_replay_id}"
                            break

                end_message = await disc_channel.send(
                    embed=embed,
                    view=build_action_view(channel_id, replay_url=None, replay_disabled=True)
                )
                print(f"**{channel_name}** 라이브 종료")

            state["last_live"][channel_id] = False
            state["last_live_event_id"].pop(channel_id, None)
            replay_wait_until = None
            if detail and open_date_str and close_date_str:
                try:
                    open_ts = to_unix_kst(open_date_str)
                    close_ts = to_unix_kst(close_date_str)
                    uptime_seconds = close_ts - open_ts
                    replay_wait_until = close_ts + 60
                    if uptime_seconds > 17 * 3600:
                        replay_wait_until = close_ts + 60
                    elif uptime_seconds > 0:
                        replay_wait_until = close_ts + 60
                except Exception:
                    replay_wait_until = None

            state["replay_tracking"][channel_id] = {
                "expires_at": int(datetime.now().timestamp()) + 20 * 60,
                "seen_video_ids": [initial_replay_id] if initial_replay_id else [],
                "message_id": end_message.id if 'end_message' in locals() else None,
                "channel_id": config["notify_channel"],
                "activated": False,
                "replay_url": None,
                "wait_until": replay_wait_until
            }

        save_json(STATE_FILE, state)
        elapsed = (datetime.now() - loop_start).total_seconds()
        sleep_time = max(1, CHECK_INTERVAL - elapsed)
        await asyncio.sleep(sleep_time)


async def community_loop():
    await client.wait_until_ready()

    while not client.is_closed():
        if not config.get("notify_channel"):
            await asyncio.sleep(CM_CHECK_INTERVAL)
            continue

        community_posts = await fetch_community_posts()
        if community_posts is None:
            await asyncio.sleep(CM_CHECK_INTERVAL)
            continue

        disc_channel = client.get_channel(config["notify_channel"])
        if not disc_channel:
            await asyncio.sleep(CM_CHECK_INTERVAL)
            continue

        new_comments = []
        for item in community_posts:
            comment = item.get("comment", {})
            comment_id = comment.get("commentId")
            if not comment_id or comment_id in state["community_seen_comments"]:
                continue
            new_comments.append(item)

        if new_comments:
            for item in reversed(new_comments):
                comment = item.get("comment", {})
                user = item.get("user", {})
                comment_id = comment.get("commentId")
                content = comment.get("content", "")
                created_date = comment.get("createdDate")
                nickname = user.get("userNickname", "알 수 없음")
                profile_image = user.get("profileImageUrl")
                object_id = comment.get("objectId")

                embed = discord.Embed(
                    title=f"커뮤니티 알림 - {nickname}",
                    description=content or "(내용 없음)",
                    color=3447003
                )
                if profile_image:
                    embed.set_thumbnail(url=profile_image)
                if created_date:
                    try:
                        timestamp = to_unix_kst(created_date)
                        embed.add_field(name="작성 시간", value=f"<t:{timestamp}:F>", inline=True)
                    except Exception:
                        embed.add_field(name="작성 시간", value=created_date, inline=True)
                if object_id:
                    embed.add_field(
                        name="게시물 링크",
                        value=f"https://chzzk.naver.com/{object_id}",
                        inline=False
                    )
                embed.set_footer(text="Cheeeezzk 커뮤니티")
                embed.timestamp = discord.utils.utcnow()

                await disc_channel.send(embed=embed)
                print(f"커뮤니티 새 글 알림: {comment_id} ({nickname})")

                state["community_seen_comments"].append(comment_id)

            save_json(STATE_FILE, state)

        await asyncio.sleep(CM_CHECK_INTERVAL)

# -------------------------
# 명령어
# -------------------------

@tree.command(name="채널설정", description="현재 채널로 알림 채널이 설정됩니다.")
async def setchannel(interaction: discord.Interaction):
    config["notify_channel"] = interaction.channel_id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("현재 채널 알림 채널 설정 완료", ephemeral=True)

@tree.command(name="로그인", description="네이버 쿠키값을 입력받아 로그인을 합니다.")
async def login(interaction: discord.Interaction, nid_aut: str, nid_ses: str):
    await interaction.response.defer(ephemeral=True)
    config["NID_AUT"] = nid_aut.strip()
    config["NID_SES"] = nid_ses.strip()
    save_json(CONFIG_FILE, config)
    await interaction.followup.send(
        "로그인이 완료되었습니다.\n이제부터 팔로우 방송을 확인하여 알림을 보내줍니다.",
        ephemeral=True
    )

@tree.command(name="정보", description="로그인 정보와 현재 디스코드 봇의 버전을 확인합니다.")
async def info(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # 쿠키가 아예 없는 경우
    if not config.get("NID_AUT") or not config.get("NID_SES"):
        embed = discord.Embed(
            title="Cheeeezzk 정보",
            color=16718891
        )
        embed.add_field(name="로그인 상태", value="로그인되지 않음", inline=False)
        embed.add_field(name="버전", value=version, inline=False)
        embed.set_footer(text="Cheeeezzk")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    content = await login_account_info()

    if not content or not content.get("loggedIn"):
        embed = discord.Embed(
            title="Cheeeezzk 정보",
            color=16718891
        )
        embed.add_field(name="로그인 상태", value="로그인되지 않음\n(쿠키가 만료되었을 수 있습니다)", inline=False)
        embed.add_field(name="버전", value=version, inline=False)
        embed.set_footer(text="Cheeeezzk")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    nickname = content.get("nickname", "알 수 없음")
    profile_image = content.get("profileImageUrl")

    embed = discord.Embed(
        title="Cheeeezzk 정보",
        color=65441
    )
    embed.add_field(name="로그인 상태", value="로그인됨", inline=False)
    embed.add_field(name="닉네임", value=nickname, inline=False)
    embed.add_field(name="버전", value=version, inline=False)
    if profile_image:
        embed.set_thumbnail(url=profile_image)
    embed.set_footer(text="Cheeeezzk")

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="로그아웃", description="현재 로그인 되어있는 계정을 로그아웃합니다.")
async def logout(interaction: discord.Interaction):
    config["NID_AUT"] = None
    config["NID_SES"] = None
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("로그아웃이 완료되었습니다.\n다시 로그인을 하기 전까지 알림이 전송되지 않습니다.", ephemeral=True)

@tree.command(name="도움말", description="명령어들의 자세한 사용법을 알려줍니다.")
async def help(interaction: discord.Interaction):
    await interaction.response.send_message("""### Cheeeezzk 디스코드 봇 명령어 사용법:
</채널설정:1483808551423049844> : 명령어를 친 채널에 알림을 보내줍니다.


</로그인:1483808551423049845> : 네이버 쿠키값을 입력받아 로그인을 합니다.
네이버 쿠키값 입력하는 방법:
1. 원하는 계정을 치지직에서 로그인한 후, F12를 눌러 개발자 도구를 엽니다.
2. 상단에 Application을 누른후, 좌측에 Cookies를 더블클릭한 후 아래에 뜨는 https:​//chzzk.naver.com 을 클릭합니다.
3. NID_AUT와 NID_SES을 /로그인 명령어에 각각 입력합니다.


</로그아웃:1483808551423049847> : /로그인 으로 입력받은 네이버 쿠키값을 초기화하여 로그아웃합니다.
다시 로그인을 하기 전까지 알림이 전송되지 않습니다.

</정보:1483808551423049846> : 로그인한 계정을 보여줍니다.

</도움말:1483808551913787392> : 지금 이 메시지를 다시 봅니다.""", ephemeral=True)

# -------------------------

@client.event
async def on_ready():
    global session
    await tree.sync()
    session = aiohttp.ClientSession()
    print(f"Logged in as {client.user}")
    asyncio.create_task(check_loop())
    asyncio.create_task(community_loop())

@client.event
async def on_guild_join(guild):
    print(f"{guild} 서버에 초대됨")
    return

@client.event
async def on_guild_leave(guild):
    print(f"{guild} 서버에서 추방됨")
    return

client.run(TOKEN)