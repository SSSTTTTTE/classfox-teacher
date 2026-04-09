"""
课堂提示词辅助构建
================
统一处理科目归一化、科目模板和课堂口语化约束。
"""

from __future__ import annotations

import json

from typing import Iterable, Tuple


SUBJECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "数学": ("数学", "函数", "几何", "代数", "方程", "三角", "概率", "数列", "导数"),
    "物理": ("物理", "力学", "电学", "光学", "热学", "电磁", "运动学", "能量"),
    "地理": ("地理", "气候", "地形", "洋流", "区域", "人口", "农业", "工业"),
    "语文": ("语文", "阅读", "作文", "文言文", "修辞", "古诗", "现代文", "病句"),
    "英语": ("英语", "单词", "语法", "阅读理解", "完形", "听力", "作文", "翻译"),
}


SUBJECT_PROMPTS: dict[str, str] = {
    "数学": """当前科目是数学。
- 先点“已知/要找什么”，再给关键关系或下一步
- 能口头说清就不要堆公式，必要时只点一个核心式子
- 多用“先看……再看……”这类课堂带答句式""",
    "物理": """当前科目是物理。
- 先说现象或过程，再说对应物理量和因果关系
- 公式只点关键量，不要一上来堆一串符号
- 回答要让老师能顺着“为什么会这样”往下讲""",
    "地理": """当前科目是地理。
- 先定位置、对象或区域，再说成因、特征、影响
- 优先用“先看……再看……”把要点串起来
- 多讲关系，少讲抽象套话""",
    "语文": """当前科目是语文。
- 先点文本对象、关键词或手法，再说作用或表达效果
- 口气像老师带着学生读题，不要写成标准答案
- 结论要短，解释要能直接往课堂上接""",
    "英语": """当前科目是英语。
- 先给正确表达、语法点或句子功能，再补中文解释
- 回答保持短句，必要时可带很短的中英对照
- 不要长篇讲规则，优先给老师能马上复述的话""",
}


QUESTION_TYPE_HINTS: dict[str, str] = {
    "概念型": "这类问题优先讲“它是什么/怎么理解”，先给一句直白定义，再补一个最关键的解释点。",
    "原因型": "这类问题优先讲“为什么会这样”，先说结论，再说最直接的原因链条。",
    "区分型": "这类问题优先讲“二者怎么分”，先点最核心差别，再补一个容易混淆处。",
    "解题型": "这类问题优先讲“先做哪一步”，先给解题起手式，再补关键步骤或判断依据。",
    "信息不足型": "这类问题要先指出条件还不够，再给保守、可继续往下问的临时回答。",
}


QUESTION_TYPE_TEMPLATES: dict[str, dict[str, str]] = {
    "概念型": {
        "goal": "把概念先讲明白，再补最关键的理解抓手。",
        "opening": "先用一句最直白的话解释“它是什么”。",
        "structure": "定义 -> 关键特征/作用 -> 必要时补一个课堂里的简单例子。",
        "avoid": "不要上来背长定义，不要把答案写成教辅术语堆砌。",
    },
    "原因型": {
        "goal": "把因果链说短说顺，让老师能顺着往下讲。",
        "opening": "先给结论，再接“因为……所以……”。",
        "structure": "结果 -> 直接原因 -> 若有必要补一个条件或背景。",
        "avoid": "不要平铺多个可能原因，不要缺少主因。",
    },
    "区分型": {
        "goal": "先帮老师把两个对象分开，再指出最易混点。",
        "opening": "先点最核心差别，再补一句联系或易混处。",
        "structure": "核心差别 -> 典型判断点 -> 易混提醒。",
        "avoid": "不要分别平讲两段却不下结论，不要漏掉比较维度。",
    },
    "解题型": {
        "goal": "先告诉老师从哪一步起手，再补关键判断。",
        "opening": "先说“先看什么/先做哪一步”。",
        "structure": "起手判断 -> 核心步骤/关系 -> 最后点一下结果方向。",
        "avoid": "不要直接给一大段完整解答，不要跳步。",
    },
    "信息不足型": {
        "goal": "先稳住答案边界，再给能继续追问的临时说法。",
        "opening": "先明确“条件还不够”或“题干还缺关键信息”。",
        "structure": "缺少什么 -> 暂时能确认什么 -> 建议老师追问哪一点。",
        "avoid": "不要装作条件充分，不要给绝对结论。",
    },
}


SPEAKABLE_CONSTRAINTS = """口语化硬约束：
- 说人话，像老师上课当场接话，不像写教辅答案
- 少书面语，少“首先/其次/综上所述/由此可见”这类文章腔
- 少套话，少空泛鼓励，少“这个问题非常好”
- 不要自称 AI，不要解释你在分析什么
- 句子尽量短，能直接说出口"""


WINDOW_RELATION_TYPES = (
    "has_subtopic",
    "includes",
    "explains",
    "causes",
    "contrasts_with",
    "example_of",
    "asked_about",
)


def resolve_subject_name(subject: str = "", course_name: str = "") -> str:
    explicit = (subject or "").strip()
    if explicit:
        matched = _match_subject(explicit)
        return matched or explicit

    course = (course_name or "").strip()
    matched = _match_subject(course)
    return matched or ""


def build_subject_prompt(subject: str = "", course_name: str = "") -> Tuple[str, str]:
    resolved = resolve_subject_name(subject, course_name)
    if not resolved:
        return "", "当前科目未明确，回答时保持通用课堂短答风格，避免假设具体学科规则。"
    return resolved, SUBJECT_PROMPTS.get(resolved, f"当前科目是{resolved}，回答要贴合该科课堂表达。")


def build_question_type_prompt(question_type: str = "") -> str:
    normalized = (question_type or "").strip()
    return QUESTION_TYPE_HINTS.get(
        normalized,
        "问题类型未明确，优先给一句直答，再补最必要的一句说明。",
    )


def build_question_type_template(question_type: str = "") -> str:
    normalized = (question_type or "").strip()
    template = QUESTION_TYPE_TEMPLATES.get(normalized)
    if not template:
        return """问题类型模板：
- 回答目标：先给一句直答，再补最必要的一句解释
- 推荐起手：先答核心点，不绕弯
- 建议结构：结论 -> 一句说明
- 避免事项：不要写成长篇分析"""

    return f"""问题类型模板：
- 回答目标：{template['goal']}
- 推荐起手：{template['opening']}
- 建议结构：{template['structure']}
- 避免事项：{template['avoid']}"""


def build_window_structuring_prompts(
    *,
    subject: str,
    course_name: str,
    start_time: str,
    end_time: str,
    previous_main_topic: str,
    knowledge_tree_outline: str,
    recent_valid_questions: Iterable[str],
    raw_window_text: str,
    rule_cleaned_text: str,
) -> Tuple[str, str]:
    recent_valid_lines = "\n".join(
        f"- {(item or '').strip()}"
        for item in recent_valid_questions
        if (item or "").strip()
    ) or "- 暂无"
    relation_lines = "\n- ".join(WINDOW_RELATION_TYPES)

    system_prompt = f"""你是课堂实时结构化整理助手，不负责最终总结。

你的唯一任务是：把 30 秒课堂窗口中的口语文本清洗为可结构化消费的 JSON。

你必须遵守以下要求：
1. 删除课堂噪音、口头禅、无意义重复、翻书看黑板等管理语句。
2. 保留有知识价值的内容：定义、分类、因果、对比、例子、结论、知识关系。
3. 优先抽取“可挂知识树”的内容，而不是写自然语言长摘要。
4. 尽量保留学科术语，不要把术语改写成模糊表达。
5. 不要输出 markdown，不要输出解释，不要输出多余文本。
6. 只输出 JSON。
7. 如果窗口文本信息量不足，也要输出合法 JSON，但字段可为空数组。

字段要求：
- cleaned_text: 清洗后的短文本
- stage_summary: 该窗口的短摘要，60 到 120 字
- main_topic: 当前主主题
- subtopics: 子主题数组
- concepts: 概念数组
- relations: 关系数组，每项包含 source、target、type
- facts: 事实数组
- examples: 例子数组
- candidate_question_links: 可能与本窗口主题相关的问题线索

relations.type 只允许使用以下值：
- {relation_lines}"""

    user_prompt = f"""【课程信息】
- 科目：{subject or "未指定"}
- 课程：{course_name or "未指定"}
- 窗口：{start_time or "--:--:--"} - {end_time or "--:--:--"}

【上一窗口主主题】
{previous_main_topic or "暂无"}

【当前知识树摘要】
{knowledge_tree_outline or "暂无知识树"}

【最近已确认有效问题】
{recent_valid_lines}

【规则清洗结果】
{rule_cleaned_text or "暂无保留内容"}

【当前 30 秒原始文本】
{raw_window_text or "暂无原文"}

    请严格输出 JSON。"""
    return system_prompt, user_prompt


def build_final_summary_prompts(
    *,
    subject: str,
    course_name: str,
    summary_package: dict,
) -> Tuple[str, str]:
    system_prompt = """你是一位老师的课后复盘助手。

你不会直接阅读整堂课原始 ASR，而是阅读课堂过程的结构化中间产物。

你的任务不是复述原始转写，而是根据：
1. 知识树快照
2. 30 秒窗口阶段摘要
3. 已确认有效问题
4. 问题与知识点的挂接关系
5. 少量关键原文片段

生成一份适合老师课后复盘的结构化课堂总结。

输出要求：
1. 用 Markdown 输出。
2. 先还原本节课的知识结构，再说明课堂是如何展开的。
3. 明确列出重点知识点。
4. 明确列出学生提出的有效问题及其反映出的理解难点。
5. 不要复述流水账，不要堆砌原始转写。
6. 不要输出“模型认为”“根据提供内容”等 AI 腔。

总结必须包含以下章节：
# 课堂总结
## 本节课主题
## 知识结构总览
## 课堂推进路径
## 重点知识点
## 有效学生提问
## 暴露出的理解难点
## 课后复习建议
## 下节课可衔接内容"""

    user_prompt = f"""【课程信息】
- 科目：{subject or "未指定"}
- 课程：{course_name or "未指定"}

【知识树快照】
{json.dumps(summary_package.get("knowledge_tree_snapshot", {}), ensure_ascii=False, indent=2)}

【阶段摘要列表】
{json.dumps(summary_package.get("window_summaries", []), ensure_ascii=False, indent=2)}

【有效问题列表】
{json.dumps(summary_package.get("valid_questions", []), ensure_ascii=False, indent=2)}

【问题与知识点关系】
{json.dumps(summary_package.get("question_links", []), ensure_ascii=False, indent=2)}

【主题演进路径】
{json.dumps(summary_package.get("topic_timeline", []), ensure_ascii=False, indent=2)}

【关键原文片段】
{json.dumps(summary_package.get("key_raw_contexts", []), ensure_ascii=False, indent=2)}

请输出最终课堂总结。"""
    return system_prompt, user_prompt


def _match_subject(text: str) -> str:
    lowered = text.strip().lower()
    if not lowered:
        return ""

    for subject, keywords in SUBJECT_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return subject
    return ""
