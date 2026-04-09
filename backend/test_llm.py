"""历史兼容云端 LLM 冒烟脚本，不是 v1.1.1 的默认主链路。"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("LLM_API_KEY", "")
base_url = os.getenv("LLM_BASE_URL", "")
model = (
    os.getenv("LLM_MODEL", "").strip()
    or os.getenv("LLM_FALLBACK_MODEL", "").strip()
    or "qwen3.5-flash"
)

if not api_key:
    raise RuntimeError(
        "Missing LLM_API_KEY. `backend/test_llm.py` 只用于排查旧 OpenAI Compatible 云端链路，"
        "不是 v1.1.1 默认配置。只有在你明确要验证旧链路时，才需要填写 LLM_API_KEY。"
    )

client_kwargs = {"api_key": api_key}
if base_url:
    client_kwargs["base_url"] = base_url

client = OpenAI(**client_kwargs)

completion = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"},
    ]
)
print(completion.model_dump_json())
