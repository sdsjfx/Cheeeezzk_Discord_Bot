# dev version _ V1.1.3 / edit _ 1

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

        # 누락된 키 자동 추가
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

def parse_kst_datetime(dt_str: str):
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=kst)

def to_unix_kst(dt_str: str):
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    dt = dt.replace(tzinfo=kst)
    return int(dt.timestamp())

config = load_json(CONFIG_FILE, {
    "notify_channel": None,
    "NID_AUT": None,
    "NID_SES": None
})

state = load_json(STATE_FILE, {
    "last_live": {},
    "last_title": {},
    "last_category": {},
    "last_tags": {}
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
for key in ["last_live", "last_title", "last_category", "last_tags"]:
    if key not in state or not isinstance(state[key], dict):
        state[key] = {}

# -------------------------
# Discord
# -------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

session = None  # 전역 세션 재사용

# -------------------------
# live-detail v2 호출
# -------------------------

async def fetch_live_detail(channel_id):
    global session

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
# followings 호출
# -------------------------

async def fetch_live_followings():
    global session

    if not config["NID_AUT"] or not config["NID_SES"]:
        print("로그인 정보 없음")
        return None

    headers = {
        "User-Agent": "Mozilla/5.0",
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
            print("API STATUS:", resp.status)

            if resp.status != 200:
                return None

            data = await resp.json()

            print("API CODE:", data.get("code"))

            if data.get("code") != 200:
                return None

            return data["content"]["followingList"]

    except Exception as e:
        print("FETCH ERROR:", e)
        return None

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

        channel = client.get_channel(config["notify_channel"])
        if not channel:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        current_live_ids = set()

        for item in live_list:
            channel_id = item["channelId"]
            if not item["channel"]["personalData"]["following"]["notification"]:
                current_live_ids.add(channel_id)
                continue
            channel_name = item["channel"]["channelName"]
            channel_icon = item["channel"].get("channelImageUrl")

            is_live = item.get("streamer", {}).get("openLive", False)
            was_live = state["last_live"].get(channel_id, False)
            

            # =========================
            # 🔴 이벤트 발생시에만 detail 호출
            # =========================
            detail = None
            if (is_live and not was_live) or (not is_live and was_live):
                detail = await fetch_live_detail(channel_id)
                if not detail:
                    continue

                title = detail.get("liveTitle")
                category = detail.get("liveCategoryValue") or "없음"
                tags = detail.get("tags")
                if not isinstance(tags, list):
                    tags = []
                thumbnail = detail.get("liveImageUrl")
                open_date_str = detail.get("openDate")
                close_date_str = detail.get("closeDate")

                if open_date_str and close_date_str:
                    opendate = parse_kst_datetime(open_date_str)
                    closedate = parse_kst_datetime(close_date_str)

                if thumbnail:
                    thumbnail = thumbnail.replace("{type}", "720")

                if open_date_str:
                    opendate = parse_kst_datetime(open_date_str)
                else:
                    opendate = None
            else:
                title = None
                category = None
                tags = []

            old_title = state["last_title"].get(channel_id)
            old_category = state["last_category"].get(channel_id)
            old_tags = state["last_tags"].get(channel_id, [])

            # =========================
            # 🟢 방송 시작
            # =========================
            if is_live and not was_live:
                open_ts = None
                if open_date_str:
                    open_ts = to_unix_kst(open_date_str)
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
                embed.add_field(
                    name="카테고리",
                    value=category,
                    inline=True
                    )
                if open_ts:
                    embed.add_field(
                        name="방송 시작 시간",
                        value=f"<t:{open_ts}:t>",
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="방송 시작 시간",
                        value="시간 정보 없음",
                        inline=True
                    )
                if tags:
                    embed.add_field(
                        name="태그",
                        value=", ".join(tags),
                        inline=False
                    )
                if thumbnail:
                    embed.set_image(url=thumbnail)
                embed.set_footer(text="Cheeeezzk")
                embed.timestamp = discord.utils.utcnow()

                await channel.send(embed=embed)
                print(f"**{channel_name}** 라이브 시작")

            # =========================
            # 🔵 방송 정보 변경
            # =========================
            changes = []

            if is_live:
                if title != old_title:
                    changes.append(("제목", old_title, title))

                if category != old_category:
                    changes.append(("카테고리", old_category, category))

                if sorted(old_tags) != sorted(tags):
                    changes.append(("태그",
                        ", ".join(old_tags),
                        ", ".join(tags)
                    ))

            if is_live and changes:

                embed = discord.Embed(
                    title=f"{channel_name}님의 방송 정보가 변경되었습니다!",
                    url=f"https://chzzk.naver.com/live/{channel_id}",
                    color=16776960
                )

                embed.set_author(
                    name=channel_name,
                    icon_url=channel_icon
                )

                for name, old, new in changes:
                    embed.add_field(
                        name=name,
                        value=f"```\n이전:\n{old or '없음'}\n현재:\n{new or '없음'}\n```",
                        inline=False
                    )

                embed.set_footer(text="Cheeeezzk")
                embed.timestamp = discord.utils.utcnow()

                await channel.send(embed=embed)
                print(f"**{channel_name}** 방송정보변경")

            # =========================
            # 상태 저장
            # =========================
            state["last_live"][channel_id] = is_live
            if title is not None:
                state["last_title"][channel_id] = title
            if category is not None:
                state["last_category"][channel_id] = category
            if tags:
                state["last_tags"][channel_id] = tags

        # =========================
        # ⚫ 방송 종료
        # =========================
        previous_live_ids = set(
        cid for cid, live in state["last_live"].items() if live
        )

        ended_streams = previous_live_ids - current_live_ids

        for channel_id in ended_streams:
        
            detail = await fetch_live_detail(channel_id)
            if not detail:
                continue

            channel_name = detail.get("channel", {}).get("channelName", "알 수 없음")
            open_date_str = detail.get("openDate")
            close_date_str = detail.get("closeDate")

            open_ts = None
            close_ts = None

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

            channel = client.get_channel(config["notify_channel"])
            if not channel:
                continue

            embed = discord.Embed(
                title=f"{channel_name}님의 방송이 종료되었습니다!",
                url=f"https://chzzk.naver.com/{channel_id}",
                description=f"**{channel_name}** 님이 라이브를 종료했습니다!",
                color=16718891
            )

            embed.add_field(
                name="방송 시간",
                value=value,
                inline=True
            )

            embed.add_field(
                name="업타임",
                value=uptime_str,
                inline=True
            )

            embed.set_footer(text="Cheeeezzk")
            embed.timestamp = discord.utils.utcnow()

            await channel.send(embed=embed)

            state["last_live"][channel_id] = False
        save_json(STATE_FILE,state)
        elapsed = (datetime.now() - loop_start).total_seconds()
        sleep_time = max(1, CHECK_INTERVAL - elapsed)
        await asyncio.sleep(sleep_time)

# -------------------------
# 명령어
# -------------------------

@tree.command(name="setchannel", description="현재 채널로 알림 채널이 설정됩니다.")
async def setchannel(interaction: discord.Interaction):
    config["notify_channel"] = interaction.channel_id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("현재 채널 알림 채널 설정 완료", ephemeral=True)

@tree.command(name="login", description="네이버 쿠키값(NID_AUT, NID_SES)을 입력받아 로그인을 합니다.")
async def login(interaction: discord.Interaction, nid_aut: str, nid_ses: str):
    await interaction.response.defer(ephemeral=True)
    config["NID_AUT"] = nid_aut.strip()
    config["NID_SES"] = nid_ses.strip()
    save_json(CONFIG_FILE, config)
    await interaction.followup.send(
        "로그인이 완료되었습니다.\n이제부터 팔로우 방송을 확인하여 알림을 보내줍니다.",
        ephemeral=True
    )

@tree.command(name="logout", description="/login으로 입력한 쿠키값을 초기화하여 로그아웃합니다.")
async def logout(interaction: discord.Interaction):
    config["NID_AUT"] = ""
    config["NID_SES"] = ""
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("로그아웃이 완료되었습니다.\n다시 로그인을 하기 전까지 알림이 전송되지 않습니다.", ephemeral=True)

@tree.command(name="help", description="명령어들의 자세한 사용법을 알려줍니다.")
async def help(interaction: discord.Interaction):
    await interaction.response.send_message("""### Cheeeezzk 디스코드 봇 명령어 사용법:
</setchannel:1476850149614555257> : 명령어를 친 채널에 알림을 보내줍니다.


</login:1476912741511073896> : 네이버 쿠키값을 입력받아 로그인을 합니다.
네이버 쿠키값 입력하는 방법:
1. 원하는 계정을 치지직에서 로그인한 후, F12를 눌러 개발자 도구를 엽니다.
2. 상단에 Application을 누른후, 좌측에 Cookies를 더블클릭한 후 아래에 뜨는 https:​//chzzk.naver.com 을 클릭합니다.
3. NID_AUT와 NID_SES을 /login 명령어에 각각 입력합니다.


</logout:1477662585028477120> : /login으로 입력받은 네이버 쿠키값을 초기화하여 로그아웃합니다.
다시 로그인을 하기 전까지 알림이 전송되지 않습니다.


</help:1477662585028477121> : 지금 이 메시지를 다시 봅니다.""", ephemeral=True)

# -------------------------

@client.event
async def on_ready():
    global session
    await tree.sync()
    session = aiohttp.ClientSession()
    print(f"Logged in as {client.user}")
    asyncio.create_task(check_loop())

@client.event
async def on_guild_join(guild):
	print(f"{guild} 서버에 초대됨")
	return

@client.event
async def on_guild_leave(guild):
	print(f"{guild} 서버에서 추방됨")
	return

client.run(TOKEN)