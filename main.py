import discord
from discord import app_commands
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

# -------------------------
# JSON 로딩
# -------------------------

def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

config = load_json(CONFIG_FILE, {
    "notify_channel": None,
    "NID_AUT": None,
    "NID_SES": None
})

state = load_json(STATE_FILE, {
    "last_live": {},
    "last_title": {},
    "last_category": {}
})

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

async def fetch_followings():
    global session

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

    url = "https://api.chzzk.naver.com/service/v1/channels/followings"

    try:
        async with session.get(
            url,
            params={
                "page": 0,
                "size": 505,
                "sortType": "FOLLOW",
                "subscription": "False",
                "followerCount": "False",
            },
            headers=headers,
            timeout=15
        ) as resp:

            print("API STATUS:", resp.status)

            if resp.status != 200:
                return None

            data = await resp.json()
            print("API CODE:", data.get("code"))

            if data.get("code") != 200:
                print("API ERROR:", data)
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

        if not config.get("notify_channel"):
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        following_list = await fetch_followings()

        if following_list is None:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        channel = client.get_channel(config["notify_channel"])
        if not channel:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        for item in following_list:

            channel_id = item["channelId"]
            channel_name = item["channel"]["channelName"]

            is_live = item.get("streamer", {}).get("openLive", False)
            title = item.get("liveInfo", {}).get("liveTitle")
            category = item.get("liveInfo").get("liveCategoryValue")

            was_live = state["last_live"].get(channel_id, False)
            old_title = state["last_title"].get(channel_id)
            old_category = state["last_category"].get(channel_id)

            print(channel_name, "LIVE:", is_live)

            # 방송 시작
            if is_live and not was_live:
                detail = await fetch_live_detail(channel_id)
                if not detail:
                    continue
                live_title = detail.get("liveTitle") or "제목 없음"
                category = detail.get("liveCategoryValue") or "없음"
                viewers = detail.get("concurrentUserCount", 0)
                tags = detail.get("tags") or []
                thumbnail = detail.get("liveImageUrl")
                # 썸네일 ( {type} 720 교체 )
                if thumbnail:
                    thumbnail = thumbnail.replace("{type}", "720")
                embed = discord.Embed(
                    title=live_title,
                    url=f"https://chzzk.naver.com/live/{channel_id}",
                    description=f"**{channel_name}** 님이 라이브 중입니다!",
                    color=65441
                )
                # Author
                embed.set_author(
                    name=channel_name,
                    url=f"https://chzzk.naver.com/{channel_id}",
                    icon_url=item["channel"].get("channelImageUrl")
                )
                # 카테고리
                embed.add_field(
                    name="카테고리",
                    value=category,
                    inline=True
                )
                # 시청자
                embed.add_field(
                    name="시청자",
                    value=f"{viewers:,}명",
                    inline=True
                )
                # 태그 (있을 때만)
                if tags:
                    embed.add_field(
                        name="태그",
                        value=", ".join(tags),
                        inline=False
                    )
                # 이미지
                if thumbnail:
                    embed.set_image(url=thumbnail)
                # Footer
                embed.set_footer(
                    text="Cheeeezzk"
                )
                embed.timestamp = discord.utils.utcnow()
                await channel.send(embed=embed)

            # 방송 종료
            if not is_live and was_live:
                await channel.send(f"⚫ {channel_name} 방송 종료")

            # 제목 변경
            if is_live and title and title != old_title:
                await channel.send(f"✏ {channel_name} 제목 변경: {title}")

            # 카테고리 변경
            if is_live and category and category != old_category:
                await channel.send(f"📂 {channel_name} 카테고리 변경: {category}")

            state["last_live"][channel_id] = is_live
            state["last_title"][channel_id] = title
            state["last_category"][channel_id] = category

        save_json(STATE_FILE, state)
        await asyncio.sleep(CHECK_INTERVAL)

# -------------------------
# 명령어
# -------------------------

@tree.command(name="setchannel", description="알림 받을 채널 설정")
async def setchannel(interaction: discord.Interaction):
    config["notify_channel"] = interaction.channel_id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("현재 채널 알림 채널 설정 완료", ephemeral=True)

@tree.command(name="login", description="NID_AUT와 NID_SES 입력")
async def login(interaction: discord.Interaction, nid_aut: str, nid_ses: str):
    config["NID_AUT"] = nid_aut
    config["NID_SES"] = nid_ses
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("로그인 정보 저장 완료", ephemeral=True)

# -------------------------

@client.event
async def on_ready():
    global session
    await tree.sync()
    session = aiohttp.ClientSession()
    print(f"Logged in as {client.user}")
    asyncio.create_task(check_loop())

@client.event
async def on_close():
    if session:
        await session.close()

client.run(TOKEN)