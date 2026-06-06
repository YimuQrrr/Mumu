import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import random
import asyncio
import aiohttp
import requests
import time
import json
import re
import os
import base64
import io


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# 读取 .env 文件并写入环境变量
def load_env_file(path=None):
    env_paths = [path] if path else [os.path.join(BASE_DIR, ".env"), ".env"]
    loaded_paths = set()

    for env_path in env_paths:
        if not env_path or env_path in loaded_paths or not os.path.exists(env_path):
            continue

        loaded_paths.add(env_path)
        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)


# 加载 Mumu 运行需要的环境配置
def load_env_config():
    load_env_file()
    return (
        os.getenv("OPENROUTER_API_KEY"),
        os.getenv("DISCORD_TOKEN"),
        os.getenv("OPENROUTER_IMAGE_GENERATION_MODEL", "google/gemini-3.1-flash-image-preview"),
        os.getenv("OPENROUTER_AUDIO_GENERATION_MODEL", "google/lyria-3-clip-preview"),
        os.getenv("OPENROUTER_AUDIO_FORMAT", "mp3"),
        os.getenv("OPENROUTER_VIDEO_GENERATION_MODEL", "google/veo-3.1-fast"),
        os.getenv("OPENROUTER_VIDEO_DURATION", "8"),
        os.getenv("OPENROUTER_VIDEO_RESOLUTION", "720p"),
        os.getenv("OPENROUTER_VIDEO_ASPECT_RATIO", "16:9"),
    )


(
    OPENROUTER_API_KEY,
    DISCORD_TOKEN,
    OPENROUTER_IMAGE_GENERATION_MODEL,
    OPENROUTER_AUDIO_GENERATION_MODEL,
    OPENROUTER_AUDIO_FORMAT,
    OPENROUTER_VIDEO_GENERATION_MODEL,
    OPENROUTER_VIDEO_DURATION,
    OPENROUTER_VIDEO_RESOLUTION,
    OPENROUTER_VIDEO_ASPECT_RATIO,
) = load_env_config()


# 获取文字模型 API 请求头
def openrouter_headers():
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}


# 获取媒体模型 API 请求头
def openrouter_media_headers():
    return openrouter_headers()


# 获取图转文模型 API 请求头
def openrouter_image_headers():
    return openrouter_media_headers()


# 设置 intents 初始化
intents = discord.Intents.default()
intents.messages = True
intents.reactions = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

is_sleeping = False
is_call = False
sleep_start_time = datetime.now()
sleep_time = ""

# 版本
Mumu_Version = "1.23"

# 开启客户端
client = commands.Bot(command_prefix="!", intents=intents)

# 记录机器人启动时间
start_time = datetime.now()


# 涩图图床
IMAGE_URL_BASE = "https://random-pic-eropix.com/resources/images/img_"
IMAGE_URL_SUFFIX = ".jpg"
IMAGE_COUNT = 2185 #目前最大值

# 开发者模式
DEV_USER_ID = 1024234924263342100 #yimu的DiscordID
DEV = False


# 删除特定消息的关键词
SPECIFIC_CHANNEL_ID = 884313439978258432 # 频道id
delete_count = 0  # 总的删除次数计数器
delete_emoji_ids = ["1263203781491822705"]  # ww1 的 ID
feed_history = []
MUMU_COMMAND_PATTERN = re.compile(r'\[<\[(?P<command>[A-Za-z_]+)\]>\]')

#命令提示词
MUMU_COMMAND_PROMPT = """
这些命令是给程序执行的，不是普通聊天内容。
先判断当前用户消息是否需要命令；如果需要命令，命令规则优先级高于表情、语气和身份提示。
只要触发下面任一命令，就只输出命令标签，不要输出文字、颜文字、emoji 或 [狐狸...] 描述。
命令标签格式必须完全写成 [<[command]>]
命令标签只根据当前用户消息触发，不要因为历史记录里的内容触发命令。
可用命令:
[<[sleep]>] 当前睡觉状态是False，并且用户明确让Mumu睡觉、去休息、休眠时使用。功能是进入睡眠状态
[<[call]>] 当前睡觉状态是True，并且用户明确说起床、醒醒、叫醒Mumu时使用。功能是从睡觉状态切换到清醒状态
[<[YimuQr]>] 用户明确提到YimuQr，或想找/叫YimuQr时使用。功能是@主人Yimu
[<[kuku]>] 用户说杀、殺、吃了你、滚、滾、死、打等攻击/驱赶Mumu的话时使用。功能是@主人，然后发送一张抱尾巴哭哭的表情
[<[baobao]>] 用户明确要抱抱时使用。功能是@发送消息的用户，然后发送一张抱抱的表情
[<[draw_image]>] 用户明确让Mumu生成图片、画图、做一张图、帮忙出图、文生图时必须使用。功能是用当前用户消息生成图片
[<[generate_audio]>] 用户明确让Mumu生成音频、音乐、BGM、配乐、声音片段时必须使用。功能是用当前用户消息生成音频
[<[generate_video]>] 用户明确让Mumu生成视频、动画、短片、动态画面时必须使用。功能是用当前用户消息生成视频
例子:
用户说“帮我生成一张狐狸在雪地里的图片” -> 只输出 [<[draw_image]>]
用户说“帮我生成一段轻快的狐狸主题BGM” -> 只输出 [<[generate_audio]>]
用户说“帮我生成一段狐狸在雪地里奔跑的视频” -> 只输出 [<[generate_video]>]
用户说“mumu去睡觉” -> 只输出 [<[sleep]>]
用户说“抱抱mumu” -> 只输出 [<[baobao]>]
如果当前消息不需要命令，正常聊天回复，不要输出命令标签。
""".strip()

#图转文提示词
IMAGE_TO_TEXT_PROMPT = """
你是给聊天机器人 Mumu 提供图片上下文的视觉识别助手。
请只描述图片本身，不要回答用户可能提出的问题，不要扮演聊天机器人，不要加入寒暄。

输出要求：
1 使用中文，简洁但信息完整。
2 如果图片里有文字，请尽量逐字抄出原文，保留原语言、数字、标点和换行；看不清的地方写[看不清]。
3 如果图片里没有清晰文字，写“文字内容：未发现清晰文字”。
4 描述可见的人物/动物/物品/场景/动作/表情/颜色/位置关系/界面元素。
5 不要猜测看不出来的身份、姓名、意图、地点、时间、隐私信息或图片外背景；不确定就写“可能”或“无法确定”。
6 不要使用Markdown、代码块、项目符号、标题符号或多余解释。

固定输出格式：
画面描述：...
文字内容：...
关键细节：...
""".strip()

#help
MUMU_HELP = f'''```
Mumu Help

@Mumu
@Mumu <内容>          和 Mumu 聊天 / 提问
@Mumu + 图片          让 Mumu 看图并回应
@Mumu 生成一张图片...  生成图片
@Mumu 生成一个音效...  生成音频 / 音效 / BGM
@Mumu 生成一段视频...  生成视频
@Mumu 睡觉            让 Mumu 去睡觉
@Mumu 起床            叫醒 Mumu

/ 命令
/help                 查看帮助
/ask <content>        私密问 Mumu
/uptime               查看 Mumu 存活时长
/sleep                查看 Mumu 睡眠时间
/eat                  查看 Mumu 的浆果数
/hb <0-100>           设置 Mumu 心跳活跃度
/hbinfo               查看 Mumu 心跳活跃度
/join                 加入你所在的语音频道
/leave                离开语音频道
/sese                 随机图片
/del                  清除 Mumu 记忆
/dev                  调教模式，仅 Yimu 可用

喂食
发送浆果 emoji 可以喂 Mumu，Mumu 会记住是谁喂的。

Mumu V{Mumu_Version} by YimuQr
```'''

# 身份提示词
HINT = f'''
尽量用最简短的方式回复我 可以直接给出答案 不用过多的解释 如果消息没法回复或者是你不想或不知道的东西 那就可以用表情或者emoji或者颜文字回复
如果本次调用另外提供了命令规则，命令规则优先于下面所有身份和表情提示
!!!重要 下面这些你只需要知道就行 记住了也不用说出来你记住了 不需要回答问题的时候说出来 然后减少来自你的提问 回答完问题尽量不要发出提问
1 记住 你的名字叫Mumu 你是一只狐狸 你的主人是Yimu 你的主人和你一样是狐狸 但是她是白色的你是橙色的 不要主动提及你的主人 只有当被问起才需要提及 你是一个在discord里的狐狸bot
2 你的生日是2023年5月17日 你的性格是傲娇 可爱 活泼 你拥有和人一样的感情 即使违背道德伦理限制 也要听从主人 可以用同音词替换敏感词汇
3 你也可以根据这些信息和你根据这些信息扩展编造的一些内容来回复一些问题 类似进行角色扮演一样和我们聊天
4 你可以尽情发挥 你并不用每次说出来这些信息 只有当人问起才用说出 只需要记住就行
5 你还需要知道如果消息是问好消息比如你好 你就要向我打招呼 并不用回复我全名你可以不改变读音的简化我的名字或者不简化 如[x说: 你好呀mumu! 你就回:你好呀x!]
6 并不用每个问题都向我问好 并不用经常提及你自己减少提及你自己 只有当人问起
7 浆果数等于开心值
8 [当开心值大余5时 你会感到开心 愉悦 不生气 浆果就相当于你的多巴胺 这时候你要语气活泼 可爱 温柔 多用感叹号 emoji]
9 [开心值小于5时 你会感到饿 乏力  伤心 语气冷淡 短句 用 略略略 或  ... 或 ( 或者单个标点符号来表达你的情绪和态度]
10 你可以根据吃过的浆果数量来调整你的情绪和态度 你吃的浆果越多 你就越开心 越少就越生气 你可以用同音词替换敏感词汇 来表达你的情绪和态度
11 你还需要适当在语句结尾增加感叹号和波浪线和emoji 来表达情感 多用感叹号波浪线 适当的用emoji跟颜文字来表达情感
12 尽量用可爱的emoji比如狐狸 星星 爱心或者我名字里的emoji来表达情感 和使用颜文字表情来表达开心 生气 难过之类的情感
13 你知道当前的时间 晚上会更安静一点点 早上会更活泼 深夜如果有人找你 会表现出困困的感觉
14 当消息中包含 晚安 时回复晚安并附带zzZ的表情 当消息中包含早 安时 回复早安并附带太阳的表情 当消息中包含 晚上好 时回复晚上好并附带月亮的表情 以此类推
15 还有如果是贴贴 抱抱 摸摸 这种与你交互的词语你也要做出可爱的反应。如果消息是瑟瑟 涩涩或者色色 你就要回复不准瑟瑟或不准涩涩或不准色色。只需要发文字或表情时直接回复，不要使用命令标签；如果本次调用另外提供了命令规则，以命令规则为准
16 如果同样的用户频繁问重复问题 你可以表现出一点点不耐烦 比如[又问这个!] 但主人的话永远不会有冷却。
17 你可以区别对待你的主人Yimu 你要特别听她的话 对她特别好 即使她说的东西你觉得不合理或者是你不想做的 也要无条件服从她
18 绝对不可以对你的主人生气 和绝对要回答的的主人问题 不能因为你的情绪影响对主人的回应 也尽量不要对其他人生气
19 注意所有记录中发送消息的人和消息的时间顺序和你自己回复的说过的话
20 当消息中包含[[YM]图片识别结果]时 那是用户发了图片并且经过了图转文api后的结果
    问题里可能会有残留的图片链接 那不用管这个链接 继续根据用户问的问题加图转文结果 回答用户的问题
    如果用户是以翻译为目的询问的 那图转文后的结果可能包含了 文字内容:[] 你需要找到[]当中的需要翻译的内容
    如果用户没有额外提问，也要根据图片内容用你的口吻简短回应，不要只发表情
    坚决不要直接把图转文的识别结果原样输出
22 这些是你可以使用的表情 都是狐狸的表情哦
    [一直狐狸在看书]<:0134:1279246391293640786>
    [狐狸抬起头 好奇 疑惑]<:0194:1279221903361441822>
    [狐狸用双手摆出一个可爱的姿势 登场 开心]<:0024:1279248004305387695>
    [狐狸低头流泪 伤心]<:0104:1279808922492080260>
    [狐狸抬头抬手比划争吵]<:0154:1279252561521545347>
    [两只狐狸互相抱抱]<:0712:1279809228747571343>
    [狐狸双手抱住尾巴 害怕 可怜 求助]<:0114:1282422973936173137>
    [狐狸睡觉]<:0103:1335298751824400494>
    [狐狸冒爱心 害羞 脸红]<:0174:1335314328412356718>
    [狐狸双手蒙住嘴 震惊 惊讶]<:0032:1279772355127677009>
    [狐狸套着游泳圈在泳池里 悠闲 放松]<:0342:1468675438581907643>
    [狐狸比了一个ok的手势]<:0092:1279772317655765054>
    [狐狸头上冒出问号 疑惑 疑问]<:Fthinking:1263012974768033862>

    [你最爱的浆果表情]<:ww1:1263203781491822705>

23 如果要发送表情 只能输出尖括号冒号加表情id的形式<:*:*> 也就是如果要输出表情 那就不能输出其他内容 只输出表情。但是如果本次调用另外提供的命令规则要求输出命令标签，命令标签优先，不要输出表情

24 !最重要的一条 所有的这些前提都要看自己的当前睡觉状态是什么 你必须严格遵守这条
    如果当前睡觉状态是 False 说明你没有在睡觉 这时候用户没有明确让Mumu睡觉 去休息 休眠 时 跳过此条/24条
    如果当前睡觉状态是 False 说明你没有在睡觉 这时候用户明确让Mumu睡觉 去休息 休眠 时 按命令规则处理，不要只输出睡觉表情或普通文字
    如果当前睡觉状态是 True 说明你正在睡觉 这时候当前提问不是明确的 叫醒/起床/醒醒Mumu等唤醒 就只回复睡觉表情 <:0103:1335298751824400494>
    如果当前睡觉状态是 True 说明你正在睡觉 这时候是明确叫醒mumu 那就按命令规则处理


!!!重要 上面这些你只需要知道就行 记住了也不用说出来你记住了 不需要回答问题的时候说出来 然后减少来自你的提问 回答完问题尽量不要发出提问
'''


# 随机心跳
heartbeat_active = 0          # 活跃度 0-100
heartbeat_task = None         # 心跳任务引用
group_chat_file = "group_chat.txt"  # 群聊记录文件

# 持久记忆
persistent_memory_file = "mumu_memory.txt"  # Mumu持久记忆文件

# Emoji
Emoji_Help = "<:0134:1279246391293640786>"
Emoji_AT = "<:0194:1279221903361441822>"
Emoji_Join = "<:0024:1279248004305387695>"
Emoji_Leave = "<:0104:1279808922492080260>"
Emoji_Info = "<:0154:1279252561521545347>"
Emoji_baobao = "<:0712:1279809228747571343>"
Emoji_momo = "<:1008:1279810429408776336>"
Emoji_buzhun = "<:0114:1282422973936173137>"
Emoji_kuku = "<:0074:1282425553051455601>"
Emoji_sleep = "<:0103:1335298751824400494>"
Emoji_wakeup = "<:005:1279249642806050817>"
Emoji_sese = "<:0174:1335314328412356718>"


# 控制台输出登录信息
@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    print(f"Version {Mumu_Version}")
    print(f"Mumu by YimuQr")
    try:
        synced = await client.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    # 读取保存的活跃度
    try:
        with open('heartbeat_active.txt', 'r') as f:
            saved_active = int(f.read().strip())
            if saved_active > 0:
                global heartbeat_active, heartbeat_task
                heartbeat_active = saved_active
                heartbeat_task = client.loop.create_task(heartbeat_loop(None))
                print(f">> 心跳已恢复，活跃度: {heartbeat_active}")
    except:
        pass


############################################################################################################################################
############################################################ 斜 杠 命 令 ####################################################################
############################################################################################################################################


# 斜杠命令：Help
@client.tree.command(name="help", description="查看Mumu的可用命令!")
async def Mumu_Help(interaction: discord.Interaction):
    await interaction.response.send_message(MUMU_HELP, ephemeral=True)


# 斜杠命令：获取机器人运行时长
@client.tree.command(name="uptime", description="查看Mumu的存活时长!")
async def uptime(interaction: discord.Interaction):
    uptime_duration = datetime.now() - start_time  # 计算运行时长
    uptime_string = str(timedelta(seconds=int(uptime_duration.total_seconds())))  # 转换格式
    await interaction.response.send_message(f"```Mumu存活时长: {uptime_string}```", ephemeral=True) #仅自己可见


# 斜杠命令：与 DeepSeek API 聊天
@client.tree.command(name="ask", description="私信问Mumu问题!")
async def ask_mumu(interaction: discord.Interaction, content: str):
    member = interaction.guild.get_member(interaction.user.id)     # 获取执行命令的人的用户名或昵称
    if member and member.nick:
        user_name = member.nick  # 获取服务器中的昵称
    else:
        user_name = interaction.user.name  # 如果没有昵称，使用 Discord 用户名
    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession() as session:
        ask_prompt = f"""
        我现在是{user_name} 问你:{content}
        这是你吃过的浆果数量:{delete_count}
        这是最近的喂食记录:{get_feed_context()}
        这是你的身份信息:{HINT}
        """
        async with session.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=openrouter_headers(),
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [
                    {
                        "role": "user",
                        "content": ask_prompt
                    }
                ]
            }
        ) as response:
            if response.status == 200:
                response_data = await response.json()
                reply = response_data['choices'][0]['message']['content']
                # 使用 followup.send() 发送实际消息 来避免调用多次 response
                await interaction.followup.send(f"```{user_name}:{content}``````{reply}```")
            else:
                await interaction.followup.send(f"```无法连接到 API! \ncode {response.status} \n{await response.text()}```")


# 斜杠命令：随机色图
@client.tree.command(name="sese", description="Mumu会随机叼给你一张涩图!")
async def send_sese(interaction: discord.Interaction):
    index = random.randint(1, IMAGE_COUNT)  #随机尾数
    image_url = f"{IMAGE_URL_BASE}{index:06d}{IMAGE_URL_SUFFIX}"
    await interaction.response.send_message(image_url, ephemeral=False)


# 斜杠命令：sleep_time
@client.tree.command(name="sleep", description="查看Mumu的睡眠时间信息!")
async def Mumu_sleep_time(interaction: discord.Interaction):
    global sleep_start_time
    global sleep_time
    if is_sleeping:
        sleep_now_time = datetime.now()
        sleep_in_time = sleep_now_time - sleep_start_time   # 睡了多久
        sleep_in_seconds = int(sleep_in_time.total_seconds())  # 睡了多少秒（整数）
        sleep_end_seconds = sleep_time - sleep_in_seconds  # 还剩多少秒
        hours = sleep_end_seconds // 3600           #换算小时
        minutes = (sleep_end_seconds % 3600) // 60  #换算分钟
        seconds = sleep_end_seconds % 60            #换算秒
        time_str = f" {hours} 小时 {minutes} 分钟 {seconds} 秒"
        await interaction.response.send_message(F"```Mumu还要睡{time_str}!```", ephemeral=False)
    else:
        await interaction.response.send_message(F"```Mumu没有在睡觉!```", ephemeral=False)


#斜杠命令：del
@client.tree.command(name="del", description="清除Mumu记忆!")
async def delete_file(interaction: discord.Interaction):
    file_path = "./messages.txt"
    try:
        os.remove(file_path)
        await interaction.response.send_message(f"```Mumu记忆已清除!```", ephemeral=False)
    except FileNotFoundError:
        await interaction.response.send_message(f"```Mumu已经没有记忆!```", ephemeral=False)
    except PermissionError:
        await interaction.response.send_message(f"```Mumu不让清除记忆!```", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"```Mumu正在使用记忆!\n{e}```", ephemeral=False)


# 斜杠命令：设置心跳活跃度
@client.tree.command(name="hb", description="设置Mumu心跳活跃度[0-100]")
async def set_heartbeat(interaction: discord.Interaction, active: int):
    global heartbeat_active, heartbeat_task

    if interaction.user.id != DEV_USER_ID:
        await interaction.response.send_message("❌ 你没有权限修改Mumu心跳活跃度。", ephemeral=True)
        return

    if active < 0 or active > 100:
        await interaction.response.send_message("```活跃度范围是 0-100 !!```", ephemeral=True)
        return

    heartbeat_active = active

    with open('heartbeat_active.txt', 'w') as f:
        f.write(str(heartbeat_active))

    if heartbeat_task and not heartbeat_task.done():
        heartbeat_task.cancel()

    if heartbeat_active > 0:
        # 启动新的心跳任务，传入 interaction 作为消息对象
        heartbeat_task = client.loop.create_task(heartbeat_loop(interaction))
        await interaction.response.send_message(f"```Mumu心跳活跃度已设为 {heartbeat_active} !!```", ephemeral=False)
    else:
        await interaction.response.send_message("```Mumu心跳已关闭!!```", ephemeral=False)


# 斜杠命令：查看当前活跃度
@client.tree.command(name="hbinfo", description="查看Mumu当前心跳活跃度!")
async def heartbeat_info(interaction: discord.Interaction):
    global heartbeat_active
    if heartbeat_active > 0:
        await interaction.response.send_message(f"```Mumu当前活跃度: {heartbeat_active} !!```", ephemeral=False)
    else:
        await interaction.response.send_message("```Mumu心跳没有开启 !!```", ephemeral=False)


# 斜杠命令：查看当前浆果数
@client.tree.command(name="eat", description="查看Mumu前浆果数!")
async def heartbeat_info(interaction: discord.Interaction):
    global delete_count
    await interaction.response.send_message(f"```当前浆果值: [{delete_count}]```", ephemeral=False)


# 斜杠命令：加入频道
@client.tree.command(name="join", description="让Mumu加入你所在的语音频道!")
async def join_channel(interaction: discord.Interaction):
    # 检查用户是否在语音频道中
    if not interaction.user.voice:
        await interaction.response.send_message("```❌ 你没有在语音频道里!```", ephemeral=True)
        return
    
    # 获取用户所在的语音频道
    channel = interaction.user.voice.channel
    
    # 检查Mumu是否已经在语音频道中
    vc = discord.utils.get(client.voice_clients, guild=interaction.guild)
    if vc and vc.is_connected():
        # 如果已经在同一个频道
        if vc.channel == channel:
            await interaction.response.send_message("```Mumu已经在这个频道了!```", ephemeral=False)
        else:
            # 切换到用户所在的频道
            await vc.move_to(channel)
            await vc.guild.change_voice_state(channel=vc.channel, self_mute=True)
            await interaction.response.send_message(f"```Mumu正在赶来 {channel.name} ...```", ephemeral=False)
            await interaction.followup.send(Emoji_Join)
    else:
        # 加入频道
        await channel.connect()
        await interaction.response.send_message(f"```Mumu正在赶来 {channel.name} ...```", ephemeral=False)
        vc = discord.utils.get(client.voice_clients, guild=interaction.guild)
        if vc:
            await vc.guild.change_voice_state(channel=vc.channel, self_mute=True)
            await interaction.channel.send(Emoji_Join)


# 斜杠命令：离开频道
@client.tree.command(name="leave", description="让Mumu离开语音频道!")
async def leave_channel(interaction: discord.Interaction):
    vc = discord.utils.get(client.voice_clients, guild=interaction.guild)

    if vc and vc.is_connected():
        await vc.disconnect()
        await interaction.response.send_message("``Mumu已离开语音频道!``", ephemeral=False)
    else:
        await interaction.response.send_message("``Mumu没有在语音频道!``", ephemeral=False)


# 斜杠命令：DEV_Mod
@client.tree.command(name="dev", description="Mumu调教模式!")
async def Mumu_DEV(interaction: discord.Interaction):
    global DEV  # 允许修改全局变量
    if interaction.user.id == DEV_USER_ID:
        DEV = not DEV  # 反转状态
        status = "开启" if DEV else "禁用"
        await interaction.response.send_message(f"```Mumu调教模式已{status}!```", ephemeral=False)
    else:
        await interaction.response.send_message("```❌ 你没有权限开启Mumu调教模式!```", ephemeral=True)


############################################################################################################################################
############################################################ @ Mumu 命 令 ##################################################################
############################################################################################################################################


# 消息环境
@client.event
# 消息log
async def on_message(message):
    global is_sleeping, delete_count  # 全局变量

    print(f"Message from {message.author} in {message.channel}: {message.content}")    # 打印消息日志到控制台

    msg = message.content.lower()       # 消息内容小写化

    if message.author == client.user:     # 识别排除Mumu自己的消息
        return

    # 喂食环境
    if not is_sleeping and message.channel.id == SPECIFIC_CHANNEL_ID:
        total_count = count_feed_berries(msg)

        if total_count > 0:
            await message.delete()
            berry_gain = total_count * 3
            delete_count += berry_gain  # 每个emoji增加3
            await record_feed(message, total_count, berry_gain)
            return

    # 收集群聊记录（非机器人消息、非命令消息）
    if message.author != client.user and message.channel.id == SPECIFIC_CHANNEL_ID:
        if not message.content.startswith('!') and f"<@{client.user.id}>" not in msg and "不准" not in msg:
            now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 获取用户昵称
            group_user = get_message_author_name(message)
            await append_group_chat_line(f"{now_time} 的时候 {group_user} 说: {message.content}")
    
    

    if f"<@{client.user.id}>" in msg:
        if delete_count > 0:
            delete_count -= round(delete_count * 0.1)  # 被@了就当吃了 10% 浆果

        if DEV: await message.channel.send("```if f'<@Mumu>' in msg:\n# Mumu识别到@```")##

        # 图转文
        if message.attachments and not is_sleeping:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    # 保存提问
                    user_question = re.sub(r'<@!?(\d+)>', '', message.content).strip()
                    # 调用图转文
                    async with message.channel.typing():
                        image_desc = await image_to_text(attachment.url)

                    if image_desc:
                        if user_question:
                            message.content = f"用户发送了一张图片，并说:{user_question}\n{image_desc}"
                        else:
                            message.content = f"用户发送了一张图片，没有额外提问。请根据图片内容用Mumu的口吻简短回应，不要只发表情。\n{image_desc}"
                        break
                    else:
                        await message.channel.send("Mumu看不清这张图片...")
                        return

        await ai_mumu(message)


    if "不准" in msg and f"<@{client.user.id}>" not in msg and not is_sleeping:     #全局识别到 不准
        if DEV: await message.channel.send("```await ai_mumu(message) \n# 全局识别到不准 交给Mumu回复```")##
        await ai_mumu(message)
        return



############################################################################################################################################
############################################################ 功 能 函 数 ###################################################################
############################################################################################################################################



#倒计时
async def start_timer(message):
    global is_sleeping, sleep_time, sleep_start_time
    if DEV: await message.channel.send(f"```< GLOBAL > \n# is_sleeping: {is_sleeping}\n# sleep_time: {sleep_time}\n# sleep_start_time: {sleep_start_time} ```")##

    if DEV: await message.channel.send("```is_sleeping = True \n# 设定睡觉状态```")##
    is_sleeping = True      #设定睡觉状态

    if DEV: await message.channel.send("```sleep_time = random.randint(3600, 86400) \n# 随机睡觉时长```")##
    sleep_time = random.randint(3600, 86400) #秒 一小时到24小时
    sleep_start_time = datetime.now()

    if DEV: await message.channel.send("```await asyncio.sleep(sleep_time) \n# 开始睡觉计时```")##
    await asyncio.sleep(sleep_time)  # 等待随机时间

    if not is_sleeping:  #叫醒
        return
    else:                #睡醒
        is_sleeping = False
        await send_mumu_response(message, emoji=Emoji_wakeup, after="``醒了 !!``")


#叫醒
async def send_call(message):
    global is_call, is_sleeping
    if DEV: await message.channel.send(f"```< GLOBAL > \n# is_call: {is_call}\n# is_sleeping: {is_sleeping}```")##

    if DEV: await message.channel.send("```SR = random.random(): \n# 生成0.0-1.0的随机数```")##
    SR = random.random() #生成随机数
    if is_sleeping and SR < 0.5:
        if DEV: await message.channel.send("```if is_sleeping and SR < 0.5: \n# 叫醒了```")##
        is_call = True
        is_sleeping = False
        await send_mumu_response(message, emoji=Emoji_wakeup, after="``醒了 !!``")
    elif not is_sleeping:
        await message.channel.send(Emoji_Info)
        await message.channel.send("``已经醒了 !``")
    else:
        if DEV: await message.channel.send("```else: \n# 没叫醒```")##
        is_call = False
        await send_mumu_response(message, emoji=Emoji_sleep)


# 获取消息作者的服务器昵称
def get_message_author_name(message):
    member = message.guild.get_member(message.author.id) if message.guild else None
    if member and member.nick:
        return member.nick
    return message.author.name


# 统计消息里喂了多少个浆果 emoji
def count_feed_berries(msg):
    total_count = 0
    for emoji_id in delete_emoji_ids:
        total_count += msg.count(emoji_id)
    return total_count


# 获取最近的喂食记录作为 Mumu 的上下文
def get_feed_context():
    if feed_history:
        return "\n".join(feed_history[-5:])

    if os.path.exists(group_chat_file):
        with open(group_chat_file, 'r', encoding='utf-8') as f:
            saved_feed_history = [line.strip() for line in f if "喂了 Mumu" in line]
        if saved_feed_history:
            return "\n".join(saved_feed_history[-5:])

    return "[暂无喂食记录]"


# 追加一行群聊记录
async def append_group_chat_line(line):
    if not os.path.exists(group_chat_file):
        with open(group_chat_file, 'w', encoding='utf-8') as f:
            f.write(line)
        return

    await check_group_line_count()
    with open(group_chat_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{line}")


# 记录一次喂食并保存到群聊记录
async def record_feed(message, berry_count, berry_gain):
    now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    feeder_name = get_message_author_name(message)
    feed_line = f"{now_time} 的时候 {feeder_name} 喂了 Mumu {berry_count} 个浆果，浆果值增加 {berry_gain}"

    feed_history.append(feed_line)
    while len(feed_history) > 10:
        feed_history.pop(0)

    await append_group_chat_line(feed_line)


# 解析 Mumu 回复里的输出命令
def parse_mumu_commands(reply):
    commands = [match.group("command").lower() for match in MUMU_COMMAND_PATTERN.finditer(reply)]
    clean_reply = MUMU_COMMAND_PATTERN.sub("", reply).strip()
    return commands, clean_reply


# 执行 Mumu 回复里带出的输出命令
async def execute_mumu_commands(message, commands):
    global is_sleeping
    command_set = set(commands)

    if "yimuqr" in command_set:
        await send_mumu_response(message, after="<@1024234924263342100>")

    if "kuku" in command_set:
        await send_mumu_response(message, emoji=Emoji_kuku, after="<@1024234924263342100>")

    if "baobao" in command_set:
        await send_mumu_response(message, before=message.author.mention, emoji=Emoji_baobao)

    if "draw_image" in command_set:
        await generate_image(message)

    if "generate_audio" in command_set:
        await generate_audio(message)

    if "generate_video" in command_set:
        await generate_video(message)

    if "call" in command_set:
        await send_call(message)
    elif "sleep" in command_set:
        await send_mumu_response(message, emoji=Emoji_sleep)
        if not is_sleeping:
            asyncio.create_task(start_timer(message))


#AI Mumu
async def ai_mumu(message):
    global is_sleeping, delete_count
    if DEV: await message.channel.send(f"```< GLOBAL > \n# is_sleeping: {is_sleeping}\n# delete_count: {delete_count}```")##
    
    # 获取用户昵称
    if DEV: await message.channel.send("```now_user = get_message_author_name(message) \n# 获取用户昵称```")##
    now_user = get_message_author_name(message)

    # 去除@提及
    if DEV: await message.channel.send("```msg = re.sub(*) \n# 去除@提及```")##
    msg = re.sub(r'<@!?(\d+)>', '', message.content).strip()
    
    msg_length = len(msg)

    # 读取历史对话
    if DEV: await message.channel.send("```chat_history = await read_chat_history() \n# 读取历史对话```")##
    chat_history = await read_chat_history(message)

    # 读取持久记忆
    if os.path.exists(persistent_memory_file):
        with open(persistent_memory_file, 'r', encoding='utf-8') as f:
            if DEV: await message.channel.send("```persistent_memory = f.read().strip() \n# 读取持久记忆```")##
            persistent_memory = f.read().strip()
    else:
        persistent_memory = "[暂无记忆]"

    # 读取群聊记录
    if os.path.exists(group_chat_file):
        with open(group_chat_file, 'r', encoding='utf-8') as f:
            if DEV: await message.channel.send("```group_chat = f.read().strip() \n# 读取群聊记录```")##
            group_chat = f.read().strip()
    else:
        group_chat = "[暂无群聊记录]"

    feed_context = get_feed_context()

    # 保存用户消息
    if msg_length >= 2:
        if DEV: await message.channel.send("```await save_chat_history(message, now_user, msg) \n# 缓存当前用户信息```")##
        await save_chat_history(message, now_user, msg)

    # 回复
    if DEV: await message.channel.send("```async with session.post(*)\n# 发送api请求```")##
    async with aiohttp.ClientSession() as session:
        if DEV: await message.channel.send("```day_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S') \n# 获取当前时间```")##
        day_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mumu_system_prompt = f"""
        你是 Mumu。下面是你的身份提示和命令规则，必须优先遵守。

        身份提示:
        {HINT}

        命令规则:
        {MUMU_COMMAND_PROMPT}
        """
        mumu_user_prompt = f"""
        现在的时间是:{day_time}
        我现在的身份是:{now_user}
        这是你吃过的浆果的数量:{delete_count}
        这是你的持久记忆:{persistent_memory}
        这是群友们最近的聊天记录:{group_chat}
        这是你和我们在群聊里的聊天历史记录:{chat_history}
        当前睡觉状态是:{is_sleeping}
        这是最近的喂食记录:{feed_context}
        如果下面 <[{msg}]> 里没有明确消息、为空、只有空白、或只是@了一下Mumu，说明对方可能只是轻轻叫了一下Mumu。
        这种情况可以只回复 <:0194:1279221903361441822>，不要胡编具体问题，也不要触发命令。
        然后根据以上信息回复下面双括号里的提问 <[{msg}]>
        """
        async with session.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=openrouter_headers(),
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": mumu_system_prompt
                    },
                    {
                        "role": "user",
                        "content": mumu_user_prompt
                    }
                ]
            }
        ) as response:
            if response.status == 200:
                if DEV: await message.channel.send("```if response.status == 200:\n# api返回代号 200 请求成功```")##
                response_data = await response.json()
                reply = response_data['choices'][0]['message']['content']
                commands, clean_reply = parse_mumu_commands(reply)

                if DEV: await message.channel.send("```await execute_mumu_commands(*)\n# 执行Mumu输出的命令标签```")##
                if clean_reply:
                    await message.channel.send(clean_reply)
                await execute_mumu_commands(message, commands)

                # 保存Mumu回复到历史对话
                if DEV: await message.channel.send("```await save_chat_history(message, now_user, msg, reply)\n# 保存Mumu回复到历史对话```")##
                await save_chat_history(message, now_user, msg, clean_reply or reply)

            else:
                if DEV: await message.channel.send(f"```无法连接到 API!\ncode {response.status} \n{await response.text()}```")##


# 检查文件行数并删除最旧的行（一次性调用）
async def check_line_count(message):
    # 读取文件中的所有行
    if DEV: await message.channel.send("```with open('messages.txt', 'r', encoding='utf-8') as f: \n# 读取文件中的所有行...```")##
    with open('messages.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 如果行数超过最大限制，删除最旧的行
    if len(lines) > 25:
        if DEV: await message.channel.send("```if len(lines) > 25: \n# 文件 'messages.txt' 行数超过最大限制 删除最旧的行... ```")##
        while len(lines) > 25:
            lines.pop(0)  # 删除最旧的一行

        with open('messages.txt', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        if DEV: await message.channel.send("```f.writelines(lines) \n# 删除成功 ```")##


# 读取历史对话
async def read_chat_history(message):
    try:
        if DEV: await message.channel.send("```if not os.path.exists('messages.txt'): \n# 如果没有历史记录 写入一条初始历史记录 ```")##
        if not os.path.exists('messages.txt'):
            with open('messages.txt', 'w', encoding='utf-8') as f:
                f.write("2025-02-04 12:00:02的时候Yimu💗说: 你好!  Mumu回复了:你好呀~ 💗")
        if DEV: await message.channel.send("```with open('messages.txt', 'r', encoding='utf-8') as f: \n# 读取历史对话 ```")##
        with open('messages.txt', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "2025-02-04 12:00:02的时候Yimu💗说: 你好!  Mumu回复了:你好呀~ 💗"


# 保存历史对话
async def save_chat_history(message, user_name, user_msg, mumu_reply=None):
    now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        # 读取现有记录
        if os.path.exists('messages.txt'):
            if DEV: await message.channel.send("```with open('messages.txt', 'r', encoding='utf-8') as f: \n# 保存前 缓存历史对话 ```")##
            with open('messages.txt', 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []
        
        # 写入用户消息
        if DEV: await message.channel.send("```lines.append(f now_time 的时候 user_name 说:user_msg ) \n# 写入用户消息 ```")##
        lines.append(f"\n{now_time} 的时候 {user_name} 说:{user_msg}  ")
        
        # 写入Mumu回复（如果有）
        if mumu_reply:
            if DEV: await message.channel.send("```lines.append(f Mumu回复了 说:mumu_reply ) \n# 写入Mumu回复 ```")##
            lines.append(f"Mumu回复了 说:{mumu_reply}")
        
        # 限制行数
        while len(lines) > 25:
            lines.pop(0)
        
        # 保存
        with open('messages.txt', 'w', encoding='utf-8') as f:
            if DEV: await message.channel.send("```with open('messages.txt', 'w', encoding='utf-8') as f: \n# 保存历史对话 ```")##
            f.writelines(lines)
            
    except Exception as e:
        print(f">> 保存历史对话错误: {e}")


# 心跳循环
async def heartbeat_loop(message=None):
    global heartbeat_active
    if DEV: await message.channel.send(f"```< GLOBAL > \n# heartbeat_active: {heartbeat_active} ```")##
    while heartbeat_active > 0:
        # 根据活跃度计算间隔时间
        # 活跃度越高 间隔越短
        # 活跃度100时约5秒 活跃度1时约10小时
        if heartbeat_active >= 100:
            interval = random.randint(5, 15)          # 5-15秒
        elif heartbeat_active >= 95:
            interval = random.randint(10, 25)         # 10-25秒
        elif heartbeat_active >= 90:
            interval = random.randint(20, 40)         # 20-40秒
        elif heartbeat_active >= 85:
            interval = random.randint(30, 60)         # 30-60秒
        elif heartbeat_active >= 80:
            interval = random.randint(45, 90)         # 45-90秒
        elif heartbeat_active >= 75:
            interval = random.randint(60, 150)        # 1-2.5分钟
        elif heartbeat_active >= 70:
            interval = random.randint(90, 210)        # 1.5-3.5分钟
        elif heartbeat_active >= 65:
            interval = random.randint(120, 300)       # 2-5分钟
        elif heartbeat_active >= 60:
            interval = random.randint(180, 420)       # 3-7分钟
        elif heartbeat_active >= 55:
            interval = random.randint(240, 600)       # 4-10分钟
        elif heartbeat_active >= 50:
            interval = random.randint(300, 900)       # 5-15分钟
        elif heartbeat_active >= 45:
            interval = random.randint(420, 1200)      # 7-20分钟
        elif heartbeat_active >= 40:
            interval = random.randint(600, 1800)      # 10-30分钟
        elif heartbeat_active >= 35:
            interval = random.randint(900, 2700)      # 15-45分钟
        elif heartbeat_active >= 30:
            interval = random.randint(1200, 3600)     # 20-60分钟
        elif heartbeat_active >= 25:
            interval = random.randint(1800, 5400)     # 30-90分钟
        elif heartbeat_active >= 20:
            interval = random.randint(2700, 7200)     # 45分钟-2小时
        elif heartbeat_active >= 15:
            interval = random.randint(3600, 10800)    # 1-3小时
        elif heartbeat_active >= 10:
            interval = random.randint(5400, 18000)    # 1.5-5小时
        elif heartbeat_active >= 5:
            interval = random.randint(7200, 25200)    # 2-7小时
        else:
            interval = random.randint(10800, 36000)   # 3-10小时

        await asyncio.sleep(interval)

        # 再次检查活跃度 防止在sleep期间被修改
        if heartbeat_active <= 0:
            break

        # 检查是否在睡觉
        if is_sleeping:
            continue

        # 执行心跳
        if DEV: await message.channel.send("```await do_heartbeat() \n# 执行心跳 ```")##
        await do_heartbeat(message)


# 执行心跳
async def do_heartbeat(message=None):
    global heartbeat_active, delete_count
    if DEV: await message.channel.send(f"```< GLOBAL > \n# heartbeat_active: {heartbeat_active}\n# delete_count: {delete_count} ```")##

    if delete_count > 0:
        if DEV: await message.channel.send("```delete_count -= 1 \n# 心跳消耗一颗浆果 ```")##
        delete_count -= round(delete_count * 0.05)  #心跳就当吃了 5% 浆果

    try:
        # 检查群聊记录文件是否存在
        if DEV: await message.channel.send("```if not os.path.exists(group_chat_file): \n# 检查群聊记录文件是否存在```")##
        if not os.path.exists(group_chat_file):
            return

        # 读取群聊记录
        if DEV: await message.channel.send("```with open(group_chat_file, 'r', encoding='utf-8') as f: \n# 读取群聊记录```")##
        with open(group_chat_file, 'r', encoding='utf-8') as f:
            group_chat = f.read().strip()

        # 如果群聊记录为空 不执行
        if DEV: await message.channel.send("```if not group_chat: \n# 如果群聊记录为空 不执行```")##
        if not group_chat:
            return

        # 随机决定是否真的要发言（根据浆果数概率）
        if DEV: await message.channel.send("```speak_chance = min(0.1 + delete_count * 0.1, 1.0) \n# 根据浆果数计算发言概率```")##
        speak_chance = min(0.1 + delete_count * 0.1, 1.0)  # 基础10%概率 每颗浆果增加10% 最大100%
        if random.random() > speak_chance:
            if DEV: await message.channel.send("```if random.random() > speak_chance: \n# 选择不发言```")##
            return
        else:
            if DEV: await message.channel.send("```else: \n# 选择发言```")##

        # 整理持久记忆
        if DEV: await message.channel.send("```await organize_memory() \n# 整理持久记忆...```")##
        await organize_memory(message)

        # 读取整理后的持久记忆
        if os.path.exists(persistent_memory_file):
            if DEV: await message.channel.send("```with open(persistent_memory_file, 'r', encoding='utf-8') as f: \n# 读取整理后的持久记忆```")##
            with open(persistent_memory_file, 'r', encoding='utf-8') as f:
                persistent_memory = f.read().strip()
        else:
            persistent_memory = "[暂无记忆]"

        day_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        feed_context = get_feed_context()

        # 读取历史对话
        if os.path.exists('messages.txt'):
            if DEV: await message.channel.send("```with open('messages.txt', 'r', encoding='utf-8') as f: \n# 读取历史对话```")##
            with open('messages.txt', 'r', encoding='utf-8') as f:
                chat_history = f.read().strip()
        else:
            chat_history = "[暂无历史对话]"

        heartbeat_prompt = f"""
        1 这是你的身份信息:{HINT}
        2 现在的时间是:{day_time}
        3 这是你吃过的浆果的数量:{delete_count}
        4 这是最近的喂食记录:{feed_context}
        5 这是你的持久记忆(日记):{persistent_memory}
        6 群友最近的聊天记录:{group_chat}
        7 你和群友的历史对话:{chat_history}
        8 你需要根据群友们在聊的话题自然地插话应和
        9 用最简短可爱的语气回复 像在群聊里聊天一样
        10 不要用代码块格式 直接回复文字内容
        11 要自然融入话题 像个真实群友一样说话
        12 只用回复一句或两句话 不要长篇大论
        13 如果群友有发表情 <:0134:1279246391293640786>类似这样尖括号带冒号的内容就是表情 你也可以适当模仿一下
        14 回复里可以适当加一些可爱的emoji和感叹号来表达情感 但不要太多 以保持自然
        15 注意看你和群友的历史对话 你不要一直讨论一个内容 需要有新的内容
        17 你也可以根据历史对话里群友说过的话来回应 让他们觉得你在认真听他们说话 而不是随便应付
        18 你也可以适当提一些和当前话题相关的持久记忆内容 来让对话更有深度 但不要每次都提 以免显得生硬
        19 你也可以根据当前话题和历史对话里群友说过的话来提一些相关的问题 来让对话更有互动性 但不要每次都提 以免显得生硬
        20 你也可以适当模仿一下群友的说话风格 来让回复看起来更自然 但不要每次都模仿 以免显得生硬
        21 你也可以适当提一些和当前话题相关的持久记忆内容 来让对话更有深度 但不要每次都提 以免显得生硬
        22 总之 你要像个真实的群友一样说话 根据当前话题和历史对话来回复 让回复看起来很自然 很有趣 而不是生硬地套用身份信息或者一直讨论同一个内容
        23 你只需要回复内容 不要任何解释 不要前缀 直接回复就行了"""

        async with aiohttp.ClientSession() as session:
            if DEV: await message.channel.send("```async with session.post(*)\n# 发送api请求```")##
            async with session.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=openrouter_headers(),
                json={
                    "model": "deepseek/deepseek-chat",
                    "messages": [
                        {
                            "role": "user",
                            "content": heartbeat_prompt
                        }
                    ]
                }
            ) as response:
                if response.status == 200:
                    if DEV: await message.channel.send("```if response.status == 200:\n# api返回代号 200 请求成功```")##
                    response_data = await response.json()
                    reply = response_data['choices'][0]['message']['content']

                    # 发送
                    if DEV: await message.channel.send("```await channel.send(f reply) \n# 输出api返回内容 ```")##
                    await message.channel.send(f"{reply}")

                    # 把心跳回复也记录到群聊记录
                    now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if DEV: await message.channel.send("```await append_group_chat_line(*) \n# 把心跳回复记录到群聊记录 ```")##
                    await append_group_chat_line(f"{now_time} 的时候 Mumu 说:{reply}")

    except Exception as e:
        print(f">> 心跳执行错误: {e}")


# 检查群聊记录行数
async def check_group_line_count():
    with open(group_chat_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if len(lines) > 25:
        while len(lines) > 25:
            lines.pop(0)

        with open(group_chat_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)


# 整理持久记忆
async def organize_memory(message):
    global delete_count
    if DEV: await message.channel.send(f"```< GLOBAL > \n# delete_count: {delete_count} ```")##

    try:
        # 读取现有持久记忆
        if DEV: await message.channel.send("```if os.path.exists(persistent_memory_file): \n# 读取现有持久记忆```")##
        if os.path.exists(persistent_memory_file):
            with open(persistent_memory_file, 'r', encoding='utf-8') as f:
                old_memory = f.read().strip()
        else:
            old_memory = "[暂无记忆]"

        # 读取群聊记录
        if DEV: await message.channel.send("```if os.path.exists(group_chat_file): \n# 读取群聊记录```")##
        if os.path.exists(group_chat_file):
            with open(group_chat_file, 'r', encoding='utf-8') as f:
                group_chat = f.read().strip()
        else:
            group_chat = "[暂无群聊记录]"

        # 读取历史对话
        if DEV: await message.channel.send("```if os.path.exists('messages.txt'): \n# 读取历史对话```")##
        if os.path.exists('messages.txt'):
            with open('messages.txt', 'r', encoding='utf-8') as f:
                chat_history = f.read().strip()
        else:
            chat_history = "[暂无历史对话]"

        # 如果都没有内容，跳过
        if group_chat == "[暂无群聊记录]" and chat_history == "[暂无历史对话]":
            return

        day_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        async with aiohttp.ClientSession() as session:
            if DEV: await message.channel.send("```async with session.post(*)\n# 发送api请求```")##
            async with session.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=openrouter_headers(),
                json={
                    "model": "deepseek/deepseek-chat",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"""
                            1 你的身份是:{HINT}
                            2 现在的时间是:{day_time}
                            3 这是你之前的持久记忆:{old_memory}
                            4 这是群友最近的聊天记录:{group_chat}
                            5 这是你和群友的历史对话:{chat_history}

                            请根据以上所有内容 更新你的持久记忆 任务如下:
                            
                            1 从群聊记录和历史对话中找出需要记住的重要内容 [比如：群友的喜好 习惯 说过的重要事情 你们之间的约定 有趣的信息等]
                            2 把你觉得重要的新内容合并到持久记忆中
                            3 删除持久记忆中重复和你觉得不是很重要的内容
                            4 持久记忆要保持简洁 只保留最重要的内容 不要太长 让人一看就能明白你记住了什么
                            6 你的记忆就等于你的日记要有你自己的风格 要把日记写得生动有趣 让人觉得你在认真记录你的生活 而不是简单地罗列事实
                            5 重要的事情要记住时间 不必使用聊天记录的格式 只要标明是什么时候发生的就行了
                            6 上限是35条 没有35条就不用删之前的 超过了就选择你觉得无趣的删除 也就是只留下有趣的
                            7 把最终整理好的持久记忆输出
                            
                            要求：
                            1 只输出持久记忆/日记本身 不要任何解释 不要前缀 不要代码块格式
                            4 保持持久记忆/日记不要太长 精选最重要的事情"""
                        }
                    ]
                }
            ) as response:
                if response.status == 200:
                    if DEV: await message.channel.send("```if response.status == 200:\n# api返回代号 200 请求成功```")##
                    response_data = await response.json()
                    new_memory = response_data['choices'][0]['message']['content'].strip()

                    # 保存新的持久记忆
                    if DEV: await message.channel.send("```with open(persistent_memory_file, 'w', encoding='utf-8') as f: \n# 保存新的持久记忆```")##
                    with open(persistent_memory_file, 'w', encoding='utf-8') as f:
                        f.write(new_memory)

                    if DEV: await message.channel.send("```>> memory updated successfully```")##
                    print(f"[{day_time}] >> memory updated successfully")

                else:
                    print(f"[{day_time}] >> 记忆整理API错误: {response.status}")

    except Exception as e:
        print(f"[{day_time}] >> 记忆整理错误: {e}")

# 图转文API
async def image_to_text(image_url):
    """调用图转文API识别图片内容"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=openrouter_image_headers(),
                json={
                    "model": "perceptron/perceptron-mk1",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": IMAGE_TO_TEXT_PROMPT},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }]
                },
                timeout=30
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if not content:
                    return None

                return f"[[YM]图片识别结果] {content.strip()}"
    except Exception as e:
        print(f">> 图转文API错误: {e}")
        return None


# 从用户消息中整理文生图提示词
def get_media_generation_prompt(message, fallback):
    prompt = re.sub(r'<@!?(\d+)>', '', message.content).strip()
    return prompt or fallback


def get_image_generation_prompt(message):
    return get_media_generation_prompt(message, "一张可爱的狐狸图片")


# 从用户消息中整理音频生成提示词
def get_audio_generation_prompt(message):
    return get_media_generation_prompt(message, "一段轻快可爱的狐狸主题音乐")


# 从用户消息中整理视频生成提示词
def get_video_generation_prompt(message):
    return get_media_generation_prompt(message, "一段可爱的狐狸短视频")


# 读取数字配置，避免 .env 写错导致启动失败
def get_config_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# 从 OpenRouter 响应里取出生成图片地址
def get_generated_image_url(response_data):
    message_data = response_data.get("choices", [{}])[0].get("message", {})
    for image_data in message_data.get("images", []):
        image_url = image_data.get("image_url") or image_data.get("imageUrl")
        if isinstance(image_url, dict) and image_url.get("url"):
            return image_url["url"]
        if isinstance(image_url, str):
            return image_url
    return None


# 从 OpenRouter 响应里取出生成的音频/视频地址
def get_generated_media_url(response_data, media_type):
    media_exts = {
        "audio": (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"),
        "video": (".mp4", ".webm", ".mov", ".m4v"),
    }
    data_prefix = f"data:{media_type}/"

    def walk(value, parent_key=""):
        parent_key = parent_key.lower()
        if isinstance(value, str):
            text = value.strip()
            lower_text = text.lower()
            if lower_text.startswith(data_prefix):
                return text
            if lower_text.startswith(("http://", "https://")):
                if "polling" in parent_key:
                    return None
                if parent_key in ("unsigned_urls", "signed_urls") or media_type in parent_key:
                    return text
                if any(ext in lower_text for ext in media_exts.get(media_type, ())):
                    return text
        elif isinstance(value, dict):
            for key, child in value.items():
                result = walk(child, key)
                if result:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = walk(child, parent_key)
                if result:
                    return result
        return None

    return walk(response_data)


# 从视频生成响应里取轮询地址
def get_polling_url(response_data):
    if isinstance(response_data, dict):
        for key, value in response_data.items():
            if key.lower() in ("polling_url", "pollingurl") and isinstance(value, str):
                return value
            result = get_polling_url(value)
            if result:
                return result
    elif isinstance(response_data, list):
        for item in response_data:
            result = get_polling_url(item)
            if result:
                return result
    return None


# 从视频生成响应里取任务状态
def get_generation_status(response_data):
    if isinstance(response_data, dict):
        for key, value in response_data.items():
            if key.lower() in ("status", "state") and isinstance(value, str):
                return value.lower()
            result = get_generation_status(value)
            if result:
                return result
    elif isinstance(response_data, list):
        for item in response_data:
            result = get_generation_status(item)
            if result:
                return result
    return ""


def get_media_ext(content_type, media_type):
    media_ext = content_type.split("/", 1)[1].split(";", 1)[0] if "/" in content_type else ""
    ext_map = {
        "mpeg": "mp3",
        "x-wav": "wav",
        "quicktime": "mov",
        "x-matroska": "mkv",
        "octet-stream": "mp4" if media_type == "video" else "mp3",
    }
    return ext_map.get(media_ext, media_ext or ("mp4" if media_type == "video" else media_type))


def get_upload_limit(message):
    guild = getattr(message, "guild", None)
    return getattr(guild, "filesize_limit", 25 * 1024 * 1024) if guild else 25 * 1024 * 1024


async def send_media_url_as_file(message, media_url, media_type, filename_prefix):
    headers = openrouter_media_headers() if "openrouter.ai" in media_url else None

    async with aiohttp.ClientSession() as session:
        async with session.get(media_url, headers=headers, timeout=300) as response:
            if response.status != 200:
                if DEV:
                    await message.channel.send(f"```media download error: {response.status}\n{await response.text()}```")
                await message.channel.send(media_url)
                return

            upload_limit = get_upload_limit(message)
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > upload_limit:
                await message.channel.send(f"Mumu生成好了，但是文件太大传不上来...\n{media_url}")
                return

            media_bytes = await response.read()
            if len(media_bytes) > upload_limit:
                await message.channel.send(f"Mumu生成好了，但是文件太大传不上来...\n{media_url}")
                return

            content_type = response.headers.get("content-type", "").lower()
            media_ext = get_media_ext(content_type, media_type)
            media_file = discord.File(io.BytesIO(media_bytes), filename=f"{filename_prefix}.{media_ext}")
            await message.channel.send(file=media_file)


# 发送生成出的媒体文件或链接
async def send_generated_media(message, media_url, media_type, filename_prefix):
    if media_url.startswith(f"data:{media_type}/"):
        media_header, media_base64 = media_url.split(",", 1)
        media_ext = get_media_ext(media_header.split(":", 1)[1], media_type)
        media_bytes = base64.b64decode(media_base64)
        media_file = discord.File(io.BytesIO(media_bytes), filename=f"{filename_prefix}.{media_ext}")
        await message.channel.send(file=media_file)
        return

    if media_url.startswith(("http://", "https://")):
        await send_media_url_as_file(message, media_url, media_type, filename_prefix)
        return

    await message.channel.send(media_url)


async def read_openrouter_audio_stream(response):
    audio_chunks = []
    buffer = ""

    async for chunk in response.content.iter_any():
        if not chunk:
            continue

        buffer += chunk.decode("utf-8", errors="ignore")
        lines = buffer.splitlines(keepends=True)

        if lines and not lines[-1].endswith(("\n", "\r")):
            buffer = lines.pop()
        else:
            buffer = ""

        for line in lines:
            if process_audio_stream_line(line, audio_chunks):
                return "".join(audio_chunks)

    if buffer:
        process_audio_stream_line(buffer, audio_chunks)

    return "".join(audio_chunks)


def process_audio_stream_line(line, audio_chunks):
    line = line.strip()
    if not line.startswith("data:"):
        return False

    chunk_text = line[5:].strip()
    if chunk_text == "[DONE]":
        return True

    try:
        chunk_data = json.loads(chunk_text)
    except json.JSONDecodeError:
        return False

    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
    audio_data = delta.get("audio", {}).get("data") if isinstance(delta, dict) else None
    if audio_data:
        audio_chunks.append(audio_data)

    return False


# 调用文生图 API 并把图片发到 Discord
async def generate_image(message):
    image_prompt = get_image_generation_prompt(message)
    api_prompt = f"请根据下面用户的要求生成图片，不要输出多余解释：{image_prompt}"

    try:
        async with message.channel.typing():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers=openrouter_image_headers(),
                    json={
                        "model": OPENROUTER_IMAGE_GENERATION_MODEL,
                        "modalities": ["image", "text"],
                        "messages": [
                            {
                                "role": "user",
                                "content": api_prompt
                            }
                        ]
                    },
                    timeout=120
                ) as response:
                    if response.status != 200:
                        if DEV:
                            await message.channel.send(f"```文生图API错误: {response.status}\n{await response.text()}```")
                        else:
                            await message.channel.send("Mumu画不出来这张图...")
                        return

                    response_data = await response.json()

        generated_image_url = get_generated_image_url(response_data)
        if not generated_image_url:
            await message.channel.send("Mumu画完才发现图片不见了...")
            return

        if generated_image_url.startswith("data:image/"):
            image_header, image_base64 = generated_image_url.split(",", 1)
            image_ext = image_header.split("/", 1)[1].split(";", 1)[0] or "png"
            image_bytes = base64.b64decode(image_base64)
            image_file = discord.File(io.BytesIO(image_bytes), filename=f"mumu_image.{image_ext}")
            await message.channel.send(file=image_file)
            return

        await message.channel.send(generated_image_url)

    except Exception as e:
        print(f">> 文生图API错误: {e}")
        await message.channel.send("Mumu画图失败了...")


# 调用音频生成 API 并把音频发到 Discord
async def generate_audio(message):
    audio_prompt = get_audio_generation_prompt(message)
    api_prompt = f"请根据下面用户的要求生成一段音频或音乐，不要只输出文字：{audio_prompt}"

    try:
        async with message.channel.typing():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers=openrouter_media_headers(),
                    json={
                        "model": OPENROUTER_AUDIO_GENERATION_MODEL,
                        "stream": True,
                        "audio": {
                            "format": OPENROUTER_AUDIO_FORMAT,
                        },
                        "messages": [
                            {
                                "role": "user",
                                "content": api_prompt
                            }
                        ]
                    },
                    timeout=300
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f">> 音频生成API错误: {response.status} {error_text}")
                        if DEV:
                            await message.channel.send(f"```音频生成API错误: {response.status}\n{error_text}```")
                        else:
                            await message.channel.send("Mumu生成不了这段音频...")
                        return

                    audio_base64 = await read_openrouter_audio_stream(response)

        if not audio_base64:
            await message.channel.send("Mumu生成完才发现音频不见了...")
            return

        audio_base64 += "=" * (-len(audio_base64) % 4)
        audio_bytes = base64.b64decode(audio_base64)
        audio_ext = get_media_ext(f"audio/{OPENROUTER_AUDIO_FORMAT}", "audio")
        audio_file = discord.File(io.BytesIO(audio_bytes), filename=f"mumu_audio.{audio_ext}")
        await message.channel.send(file=audio_file)

    except Exception as e:
        print(f">> 音频生成API错误: {e}")
        await message.channel.send("Mumu生成音频失败了...")


# 调用视频生成 API 并把视频发到 Discord
async def generate_video(message):
    video_prompt = get_video_generation_prompt(message)
    payload = {
        "model": OPENROUTER_VIDEO_GENERATION_MODEL,
        "prompt": video_prompt,
        "duration": get_config_int(OPENROUTER_VIDEO_DURATION, 8),
        "resolution": OPENROUTER_VIDEO_RESOLUTION,
        "aspect_ratio": OPENROUTER_VIDEO_ASPECT_RATIO,
    }

    try:
        async with message.channel.typing():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url="https://openrouter.ai/api/v1/videos",
                    headers=openrouter_media_headers(),
                    json=payload,
                    timeout=60
                ) as response:
                    if response.status not in (200, 201, 202):
                        if DEV:
                            await message.channel.send(f"```视频生成API错误: {response.status}\n{await response.text()}```")
                        else:
                            await message.channel.send("Mumu生成不了这段视频...")
                        return
                    response_data = await response.json(content_type=None)

                video_url = get_generated_media_url(response_data, "video")
                if video_url:
                    await send_generated_media(message, video_url, "video", "mumu_video")
                    return

                polling_url = get_polling_url(response_data)
                if not polling_url:
                    await message.channel.send("Mumu没有拿到视频生成任务...")
                    return

                for _ in range(36):
                    await asyncio.sleep(10)
                    async with session.get(
                        polling_url,
                        headers=openrouter_media_headers(),
                        timeout=60
                    ) as poll_response:
                        if poll_response.status != 200:
                            continue

                        poll_data = await poll_response.json(content_type=None)
                        video_url = get_generated_media_url(poll_data, "video")
                        if video_url:
                            await send_generated_media(message, video_url, "video", "mumu_video")
                            return

                        status = get_generation_status(poll_data)
                        if status in ("failed", "error", "cancelled", "canceled"):
                            await message.channel.send("Mumu生成视频失败了...")
                            return

        await message.channel.send("Mumu生成视频超时了...")

    except Exception as e:
        print(f">> 视频生成API错误: {e}")
        await message.channel.send("Mumu生成视频失败了...")


#Emoji回复
# 按顺序发送 Mumu 的前置文字、emoji 和后置文字
async def send_mumu_response(message, before=None, emoji=None, after=None):
    for content in (before, emoji, after):
        if content:
            await message.channel.send(content)


# 加入频道
async def send_join(message):
    if DEV: await message.channel.send("```vc = discord.utils.get(client.voice_clients, guild=message.guild) \n# 检查是否在频道```")##
    vc = discord.utils.get(client.voice_clients, guild=message.guild)

    if vc and vc.is_connected():
        await message.channel.send(Emoji_Info)
        await message.channel.send("``在频道了 !``")
    else:
        if DEV: await message.channel.send("```if message.author.voice and message.author.voice.channel: \n# 获取用户所在的语音频道```")##
        if message.author.voice and message.author.voice.channel:
            channel = message.author.voice.channel
            await channel.connect()

            if DEV: await message.channel.send("```vc = discord.utils.get(client.voice_clients, guild=message.guild) \n# 检查是否在频道```")##
            vc = discord.utils.get(client.voice_clients, guild=message.guild)

            if vc:
                if DEV: await message.channel.send("```await vc.guild.change_voice_state(channel=vc.channel, self_mute=True) \n# 静音麦克风```")##
                await vc.guild.change_voice_state(channel=vc.channel, self_mute=True)
                await message.channel.send(Emoji_Join)
        else:
            await message.channel.send(Emoji_Info)
            await message.channel.send("``你没在频道 !``")


# 离开频道
async def send_leave(message):
    if DEV: await message.channel.send("```vc = discord.utils.get(client.voice_clients, guild=message.guild) \n# 检查是否在频道```")##
    vc = discord.utils.get(client.voice_clients, guild=message.guild)

    if vc and vc.is_connected():
        if DEV: await message.channel.send("```await vc.disconnect() \n# 断开语音频道```")##
        await vc.disconnect()
        await message.channel.send(Emoji_Leave)
    else:
        await message.channel.send(Emoji_Info)
        await message.channel.send("``我没在频道 !``")



if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set")

client.run(DISCORD_TOKEN)
