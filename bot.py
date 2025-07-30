from dotenv import load_dotenv
load_dotenv()

import os, json, asyncio, logging
from pathlib import Path
from typing import List
import git
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import Tool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import HumanMessage, AIMessage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# ---------- конфиг ----------
BOT_TOKEN      = os.getenv("BOT_TOKEN")
OPENAI_KEY     = os.getenv("OPENAI_API_KEY")
GIT_REPO_URL   = os.getenv("GIT_REPO_URL")
GIT_TOKEN      = os.getenv("GIT_TOKEN")
ALLOWED_USERS  = set(os.getenv("ALLOWED_USERS", "").split(","))

REPO_DIR = Path("repo")

# ---------- Git helper ----------
def init_repo():
    if not REPO_DIR.exists():
        repo = git.Repo.clone_from(
            GIT_REPO_URL.replace("https://", f"https://{GIT_TOKEN}@"),
            REPO_DIR
        )
    else:
        repo = git.Repo(REPO_DIR)
    return repo

repo = init_repo()

def save_history(user: str, messages: List[dict]):
    file = REPO_DIR / f"{user}.jsonl"
    with file.open("a", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    repo.index.add([str(file)])
    repo.index.commit(f"update {user}")
    origin = repo.remote(name="origin")
    origin.push()

def load_history(user: str) -> List[dict]:
    file = REPO_DIR / f"{user}.jsonl"
    if not file.exists():
        return []
    with file.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]

# ---------- LangChain ----------
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENAI_KEY,
    model="qwen/qwen3-coder:free",
    temperature=0
)

async def get_tools():
    # Пока пусто, добавляй MCP-сервера по аналогии
    client = MultiServerMCPClient({})
    mcp_tools = await client.get_tools()
    return mcp_tools

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты полезный русскоязычный ассистент."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad")
])

# ---------- aiogram ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    if msg.from_user.username not in ALLOWED_USERS:
        await msg.answer("Доступ запрещён.")
        return
    await msg.answer("Привет! Пиши, я рядом.")

@dp.message()
async def answer(msg: Message):
    user = msg.from_user.username
    if user not in ALLOWED_USERS:
        await msg.answer("Доступ запрещён.")
        return

    history_raw = load_history(user)
    history = [HumanMessage(m["content"]) if m["role"]=="user" else AIMessage(m["content"])
               for m in history_raw]

    tools = await get_tools()
    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

    # стримим
    answer_text = ""
    async for chunk in executor.astream({"input": msg.text, "history": history}):
        if chunk.get("output"):
            answer_text += chunk["output"]
    await msg.answer(answer_text)

    # сохраняем
    save_history(user, [{"role":"user","content":msg.text},
                        {"role":"assistant","content":answer_text}])

async def main():
    await dp.start_polling(bot)

PORT = int(os.getenv("PORT", 10000))   # Render injects PORT=10000

async def on_startup(app: web.Application):
    await bot.set_webhook(f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()

if __name__ == "__main__":
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/")
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)
