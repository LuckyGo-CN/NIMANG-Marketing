from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("NIMANG_DB", DATA_DIR / "experiment.db"))
ADMIN_KEY = os.environ.get("NIMANG_ADMIN_KEY", "nimang-admin")

BATCHES = {
    "practice_a": {
        "label": "练习任务A",
        "required": ["01", "02", "03"],
        "duration": 5 * 60,
        "order_count": 3,
        "rule": "legacy",
        "feedback": "practice_a",
        "reveal_delay": 0,
    },
    "practice_b": {
        "label": "练习任务B",
        "required": ["04"],
        "duration": 5 * 60,
        "order_count": 3,
        "rule": "recent",
        "feedback": "practice_b",
        "reveal_delay": 0,
    },
    "round_1": {
        "label": "团队推广任务A",
        "required": ["01", "02", "03"],
        "duration": 15 * 60,
        "order_count": 9,
        "rule": "legacy",
        "feedback": "formal",
        "reveal_delay": 0,
    },
    "round_2": {
        "label": "团队推广任务B",
        "required": ["01", "02", "03", "04"],
        "duration": 15 * 60,
        "order_count": 9,
        "rule": "recent",
        "feedback": "formal",
        "reveal_delay": 5 * 60,
    },
}

TEAM_CODES = tuple(f"G{index}" for index in range(1, 101))
MEMBER_NAMES = {member: f"推广专员{member}" for member in ("01", "02", "03", "04")}
VALID_OPTIONS = {
    "gender": ["不限", "女性", "男性"],
    "age": ["18-24岁", "25-34岁", "35岁以上"],
    "account_type": ["头部达人", "腰部达人", "素人博主"],
    "format_type": ["图文描述", "视频展示", "直播销售"],
}

LEGACY_RULES = {
    "家居日用类": {
        "gender": {"不限": 90, "女性": 60, "男性": 30},
        "age": {"25-34岁": 90, "18-24岁": 60, "35岁以上": 30},
        "account_type": {"素人博主": 90, "腰部达人": 60, "头部达人": 30},
        "format_type": {"直播销售": 90, "视频展示": 60, "图文描述": 30},
    },
    "美妆护肤类": {
        "gender": {"女性": 90, "不限": 60, "男性": 30},
        "age": {"25-34岁": 90, "35岁以上": 60, "18-24岁": 30},
        "account_type": {"头部达人": 90, "腰部达人": 60, "素人博主": 30},
        "format_type": {"视频展示": 90, "直播销售": 60, "图文描述": 30},
    },
    "运动户外类": {
        "gender": {"不限": 90, "女性": 60, "男性": 60},
        "age": {"18-24岁": 90, "25-34岁": 60, "35岁以上": 30},
        "account_type": {"腰部达人": 90, "素人博主": 60, "头部达人": 30},
        "format_type": {"图文描述": 90, "视频展示": 60, "直播销售": 30},
    },
}

RECENT_RULES = json.loads(json.dumps(LEGACY_RULES, ensure_ascii=False))
RECENT_RULES["家居日用类"]["format_type"] = {"图文描述": 90, "直播销售": 60, "视频展示": 30}
RECENT_RULES["美妆护肤类"]["account_type"] = {"素人博主": 90, "头部达人": 60, "腰部达人": 30}
RECENT_RULES["运动户外类"]["age"] = {"25-34岁": 90, "18-24岁": 60, "35岁以上": 30}

LEGACY_FEEDBACK = {
    "家居日用类": [
        "家居日用类产品覆盖较广泛的生活使用场景，不同性别用户均可能产生购买需求，因此面向“不限”性别推广时受众覆盖更充分。",
        "25-34岁用户对居家生活品质、空间布置和日常实用内容关注度更高，相关内容更容易带来互动和转化。",
        "素人博主的日常生活分享更容易呈现家居产品的真实使用场景，有助于提升用户信任感和购买意愿。",
        "直播销售能够实时展示家居产品的使用方式、尺寸细节和搭配效果，更容易促成用户即时咨询和下单转化。",
    ],
    "美妆护肤类": [
        "女性用户对美妆护肤类内容的关注度和互动意愿更高，相关推广更容易触达核心消费人群。",
        "25-34岁用户通常具有较稳定的护肤需求和消费能力，对功效型护肤和品质化美妆内容更为敏感。",
        "头部达人在美妆护肤领域具有更强的曝光能力和种草影响力，更容易快速建立产品认知和口碑热度。",
        "视频展示更适合呈现产品质地、使用过程和即时效果，能够提升用户对产品功效的直观感知。",
    ],
    "运动户外类": [
        "运动户外类产品使用场景广泛，不同性别用户均存在需求，因此面向“不限”性别推广时覆盖更充分。",
        "18-24岁用户对运动、出行和户外体验类内容兴趣更高，更容易被轻量化和体验感强的内容吸引。",
        "腰部达人兼具一定影响力和垂直内容经验，能够在运动户外场景中自然传递产品功能和使用体验。",
        "图文描述适合清晰呈现功能参数、使用场景和细节对比，有助于用户在决策前充分了解产品信息。",
    ],
}

RECENT_TRENDS = {
    "家居日用类": {
        "dimension": "format_type",
        "text": "在家居日用类产品中，图文描述类内容的推广效果有所提升，相比直播销售更有助于用户了解产品细节和真实使用场景。",
    },
    "美妆护肤类": {
        "dimension": "account_type",
        "text": "在美妆护肤类产品中，素人博主的推广效果有所提升，相比头部达人更容易增强用户信任感和真实种草感。",
    },
    "运动户外类": {
        "dimension": "age",
        "text": "在运动户外类产品中，25-34岁用户的互动和转化表现有所提升，相比18-24岁用户逐渐成为更值得关注的目标群体。",
    },
}

PRODUCT_SETS = {
    "01": [
        ("嘉禾家居", "香薰扩香石", "家居日用类", 39, "tea-cup.svg"),
        ("竹影生活", "桌面多功能收纳盒", "家居日用类", 49, "storage-cabinet.svg"),
        ("沐光家居", "北欧阅读落地灯", "家居日用类", 249, "floor-lamp.svg"),
        ("颜栖美研", "丝绒哑光口红", "美妆护肤类", 119, "lipstick.svg"),
        ("澄净实验室", "氨基酸洁面乳", "美妆护肤类", 89, "cleanser.svg"),
        ("晴肌研究所", "清透防晒霜", "美妆护肤类", 98, "sunscreen.svg"),
        ("途野运动", "碳素羽毛球拍", "运动户外类", 159, "badminton-racket.svg"),
        ("峰行装备", "铝合金登山杖", "运动户外类", 129, "trekking-poles.svg"),
        ("山止户外", "轻量徒步双肩包", "运动户外类", 219, "hiking-backpack.svg"),
    ],
    "02": [
        ("禾木日常", "釉彩马克杯", "家居日用类", 45, "tea-cup.svg"),
        ("简仓生活", "抽屉式桌面收纳柜", "家居日用类", 59, "storage-cabinet.svg"),
        ("一隅照明", "可调光客厅立灯", "家居日用类", 269, "floor-lamp.svg"),
        ("绯色美研", "水润柔雾唇膏", "美妆护肤类", 129, "lipstick.svg"),
        ("初澈护肤", "温和净澈洁面乳", "美妆护肤类", 79, "cleanser.svg"),
        ("日光序", "轻薄隔离防晒乳", "美妆护肤类", 109, "sunscreen.svg"),
        ("燃点体育", "轻量进阶羽毛球拍", "运动户外类", 179, "badminton-racket.svg"),
        ("远峰户外", "伸缩碳钢登山杖", "运动户外类", 149, "trekking-poles.svg"),
        ("越岭装备", "防泼水徒步背包", "运动户外类", 239, "hiking-backpack.svg"),
    ],
    "03": [
        ("白屿生活", "陶瓷咖啡杯", "家居日用类", 42, "tea-cup.svg"),
        ("叠序家居", "模块化桌面整理箱", "家居日用类", 55, "storage-cabinet.svg"),
        ("微昼照明", "极简卧室落地灯", "家居日用类", 229, "floor-lamp.svg"),
        ("棠妆", "滋润显色口红", "美妆护肤类", 109, "lipstick.svg"),
        ("净颜社", "泡沫洁面慕斯", "美妆护肤类", 85, "cleanser.svg"),
        ("轻岚护肤", "高倍清爽防晒霜", "美妆护肤类", 115, "sunscreen.svg"),
        ("凌风运动", "高弹训练羽毛球拍", "运动户外类", 169, "badminton-racket.svg"),
        ("石径装备", "减震徒步登山杖", "运动户外类", 139, "trekking-poles.svg"),
        ("野渡户外", "多仓轻量登山包", "运动户外类", 229, "hiking-backpack.svg"),
    ],
    "04": [
        ("清和日用", "轻量随行茶杯", "家居日用类", 48, "tea-cup.svg"),
        ("方寸家居", "分层桌面储物柜", "家居日用类", 62, "storage-cabinet.svg"),
        ("暖线照明", "现代氛围落地灯", "家居日用类", 259, "floor-lamp.svg"),
        ("雾桃美妆", "轻盈奶霜唇膏", "美妆护肤类", 125, "lipstick.svg"),
        ("研净实验室", "低敏氨基酸洁面", "美妆护肤类", 92, "cleanser.svg"),
        ("晴空肌研", "水感防晒精华", "美妆护肤类", 118, "sunscreen.svg"),
        ("越界运动", "全碳进攻羽毛球拍", "运动户外类", 189, "badminton-racket.svg"),
        ("逐峰户外", "折叠铝合金登山杖", "运动户外类", 145, "trekking-poles.svg"),
        ("向野装备", "透气徒步双肩包", "运动户外类", 249, "hiking-backpack.svg"),
    ],
}

PRACTICE_INDEXES = [1, 4, 8]

WORKFLOWS = {
    "legacy": [
        ("practice_a", "练习任务A", "完成系统操作练习并查看反馈", "task", "practice_a"),
        ("round1_arrangement", "任务安排确认A", "确认相关任务安排", "survey", "round1_arrangement"),
        ("round1_task", "团队推广任务A", "与团队成员共同处理正式订单", "task", "round_1"),
        ("round2_arrangement", "任务安排确认B", "确认相关任务安排", "survey", "round2_arrangement"),
        ("round2_task", "团队推广任务B", "与团队成员共同处理正式订单", "task", "round_2"),
        ("performance", "绩效结果", "查看练习与团队任务的个人、团队绩效", "performance", "performance"),
    ],
    "new": [
        ("practice_b", "练习任务B", "完成系统操作练习并查看反馈", "task", "practice_b"),
        ("recent_trend", "近期趋势理解", "确认对近期平台趋势的理解", "survey", "recent_trend"),
        ("wait_for_team", "等待加入团队", "等待操作助手指示", "waiting", "wait_for_team"),
        ("round2_arrangement", "任务安排确认B", "确认相关任务安排", "survey", "round2_arrangement"),
        ("round2_task", "团队推广任务B", "与团队成员共同处理正式订单", "task", "round_2"),
        ("performance", "绩效结果", "查看练习与团队任务的个人、团队绩效", "performance", "performance"),
    ],
}

TASK_STEP_BATCH = {
    "practice_a": "practice_a",
    "practice_b": "practice_b",
    "round1_task": "round_1",
    "round2_task": "round_2",
}

SURVEY_REQUIRED = {
    "round1_arrangement": {
        *(f"gender.{category}" for category in ("home", "beauty", "outdoor")),
        *(f"age.{category}" for category in ("home", "beauty", "outdoor")),
        *(f"account.{category}" for category in ("home", "beauty", "outdoor")),
        *(f"format.{category}" for category in ("home", "beauty", "outdoor")),
    },
    "round2_arrangement": {"identity", "pay_relation", *(f"fairness.{index}" for index in range(1, 7))},
    "recent_trend": {"home_format", "beauty_account", "outdoor_age"},
}


def now_ts() -> float:
    return time.time()


def iso_time(timestamp: float | None = None) -> str:
    value = timestamp if timestamp is not None else now_ts()
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_code TEXT NOT NULL,
                team_code TEXT NOT NULL,
                member_id TEXT NOT NULL,
                role TEXT NOT NULL,
                participant_uid TEXT NOT NULL UNIQUE,
                token TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                UNIQUE(scene_code, team_code, member_id)
            );
            CREATE TABLE IF NOT EXISTS workflow_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                step_key TEXT NOT NULL,
                completed_at REAL NOT NULL,
                UNIQUE(account_id, step_key)
            );
            CREATE TABLE IF NOT EXISTS questionnaire_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                role TEXT NOT NULL,
                participant_uid TEXT NOT NULL,
                module_name TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer TEXT NOT NULL,
                page_start_time TEXT NOT NULL,
                submit_time TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                UNIQUE(account_id, module_name, question_id)
            );
            CREATE TABLE IF NOT EXISTS team_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_code TEXT NOT NULL,
                team_code TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                started_at REAL,
                end_at REAL,
                performance_at REAL,
                UNIQUE(team_code, batch_id)
            );
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES team_sessions(id) ON DELETE CASCADE,
                member_id TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                joined_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                UNIQUE(session_id, member_id)
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES team_sessions(id) ON DELETE CASCADE,
                member_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                brand TEXT NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                price INTEGER NOT NULL,
                gender TEXT NOT NULL,
                age TEXT NOT NULL,
                account_type TEXT NOT NULL,
                format_type TEXT NOT NULL,
                reason_text TEXT NOT NULL,
                dimension_scores TEXT NOT NULL,
                success_rate INTEGER NOT NULL,
                submitted_at REAL NOT NULL,
                UNIQUE(session_id, member_id, order_id)
            );
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                member_id TEXT,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                occurred_at REAL NOT NULL
            );
            """
        )
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('scene_code', 'S01')")


def get_setting(db: sqlite3.Connection, key: str) -> str:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def normalize_team(value: str) -> str:
    cleaned = re.sub(r"\s+", "", str(value).upper())
    match = re.fullmatch(r"G([1-9]|[1-9][0-9]|100)", cleaned)
    return cleaned if match else ""


def normalize_member(value: str) -> str:
    cleaned = re.sub(r"\s+", "", str(value))
    match = re.fullmatch(r"推广专员(0[1-4])", cleaned)
    return match.group(1) if match else ""


def order_rows(member_id: str, batch_id: str) -> list[dict]:
    products = PRODUCT_SETS[member_id]
    indexes = PRACTICE_INDEXES if BATCHES[batch_id]["order_count"] == 3 else list(range(9))
    rows = []
    prefix = "PRACTICE" if batch_id.startswith("practice") else ("R1" if batch_id == "round_1" else "R2")
    for display_index, product_index in enumerate(indexes, start=1):
        brand, name, category, price, image = products[product_index]
        order_id = f"{prefix}-{member_id}-{display_index:02d}"
        if batch_id.startswith("practice"):
            order_id = f"PRACTICE-{display_index:02d}"
        rows.append(
            {
                "id": order_id,
                "index": display_index,
                "brand": brand,
                "name": name,
                "category": category,
                "price": price,
                "image": f"/assets/products/{Path(image).with_suffix('.png').name}",
            }
        )
    return rows


def get_context(db: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT p.id participant_id, p.member_id, p.token, s.*
        FROM participants p
        JOIN team_sessions s ON s.id = p.session_id
        WHERE p.token = ?
        """,
        (token,),
    ).fetchone()


def log_event(db: sqlite3.Connection, session_id: int | None, member_id: str | None, action: str, details: dict) -> None:
    db.execute(
        "INSERT INTO event_logs(session_id, member_id, action, details, occurred_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, member_id, action, json.dumps(details, ensure_ascii=False), now_ts()),
    )


def login_participant(team_code: str, member_id: str, batch_id: str) -> dict:
    team_code = normalize_team(team_code)
    member_id = normalize_member(member_id)
    if team_code not in TEAM_CODES:
        raise ValueError("请输入有效团队编号（G1-G100）。")
    if not member_id:
        raise ValueError("请输入有效员工身份，例如 推广专员01。")
    if batch_id not in BATCHES:
        raise ValueError("请选择有效任务批次。")
    config = BATCHES[batch_id]
    if member_id not in config["required"]:
        allowed = "、".join(MEMBER_NAMES[item] for item in config["required"])
        raise ValueError(f"当前成员身份不能进入该任务批次。允许身份：{allowed}。")

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        session = db.execute(
            "SELECT * FROM team_sessions WHERE team_code = ? AND batch_id = ?",
            (team_code, batch_id),
        ).fetchone()
        if not session:
            scene_code = get_setting(db, "scene_code") or "S01"
            cursor = db.execute(
                "INSERT INTO team_sessions(scene_code, team_code, batch_id, created_at) VALUES (?, ?, ?, ?)",
                (scene_code, team_code, batch_id, now_ts()),
            )
            session = db.execute("SELECT * FROM team_sessions WHERE id = ?", (cursor.lastrowid,)).fetchone()

        participant = db.execute(
            "SELECT * FROM participants WHERE session_id = ? AND member_id = ?",
            (session["id"], member_id),
        ).fetchone()
        if participant:
            token = participant["token"]
            db.execute("UPDATE participants SET last_seen = ? WHERE id = ?", (now_ts(), participant["id"]))
        else:
            token = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO participants(session_id, member_id, token, joined_at, last_seen) VALUES (?, ?, ?, ?, ?)",
                (session["id"], member_id, token, now_ts(), now_ts()),
            )
            log_event(db, session["id"], member_id, "login", {"team_code": team_code, "batch_id": batch_id})

        joined = db.execute(
            "SELECT COUNT(*) count FROM participants WHERE session_id = ? AND member_id IN ({})".format(
                ",".join("?" for _ in config["required"])
            ),
            (session["id"], *config["required"]),
        ).fetchone()["count"]
        session = db.execute("SELECT * FROM team_sessions WHERE id = ?", (session["id"],)).fetchone()
        if not session["started_at"] and joined >= len(config["required"]):
            started_at = now_ts()
            end_at = started_at + config["duration"]
            performance_at = end_at + config["reveal_delay"]
            db.execute(
                "UPDATE team_sessions SET started_at = ?, end_at = ?, performance_at = ? WHERE id = ?",
                (started_at, end_at, performance_at, session["id"]),
            )
            log_event(db, session["id"], None, "task_started", {"batch_id": batch_id, "joined": joined})
        db.commit()
    return {"token": token}


def account_context(db: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM accounts WHERE token = ?", (token,)).fetchone()


def role_for(member_id: str) -> str:
    return "new" if member_id == "04" else "legacy"


def participant_uid(scene_code: str, team_code: str, member_id: str) -> str:
    return f"{scene_code}-{team_code}-{member_id}"


def login_account(team_code: str, member_value: str) -> dict:
    team_code = normalize_team(team_code)
    member_id = normalize_member(member_value)
    if not team_code:
        raise ValueError("请输入有效团队编号（G1-G100）。")
    if not member_id:
        raise ValueError("请选择有效员工身份。")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        scene_code = get_setting(db, "scene_code") or "S01"
        account = db.execute(
            "SELECT * FROM accounts WHERE scene_code = ? AND team_code = ? AND member_id = ?",
            (scene_code, team_code, member_id),
        ).fetchone()
        if account:
            token = account["token"]
            db.execute("UPDATE accounts SET last_seen = ? WHERE id = ?", (now_ts(), account["id"]))
        else:
            token = secrets.token_urlsafe(32)
            db.execute(
                """
                INSERT INTO accounts(scene_code, team_code, member_id, role, participant_uid, token, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_code, team_code, member_id, role_for(member_id),
                    participant_uid(scene_code, team_code, member_id), token, now_ts(), now_ts(),
                ),
            )
        db.commit()
    return {"success": True, "token": token}


def completed_steps(db: sqlite3.Connection, account_id: int) -> set[str]:
    return {
        row["step_key"]
        for row in db.execute("SELECT step_key FROM workflow_progress WHERE account_id = ?", (account_id,)).fetchall()
    }


def maybe_release_new_member(db: sqlite3.Connection, account: sqlite3.Row) -> None:
    if account["member_id"] != "04":
        return
    old_members = db.execute(
        """
        SELECT a.member_id,
               EXISTS(SELECT 1 FROM workflow_progress w WHERE w.account_id = a.id AND w.step_key = 'round1_task') done
        FROM accounts a
        WHERE a.scene_code = ? AND a.team_code = ? AND a.member_id IN ('01', '02', '03')
        """,
        (account["scene_code"], account["team_code"]),
    ).fetchall()
    if len(old_members) == 3 and all(row["done"] for row in old_members):
        db.execute(
            "INSERT OR IGNORE INTO workflow_progress(account_id, step_key, completed_at) VALUES (?, 'wait_for_team', ?)",
            (account["id"], now_ts()),
        )


def workflow_state(db: sqlite3.Connection, account: sqlite3.Row) -> list[dict]:
    maybe_release_new_member(db, account)
    done = completed_steps(db, account["id"])
    steps = []
    current_assigned = False
    for index, (key, label, description, kind, target) in enumerate(WORKFLOWS[account["role"]], start=1):
        if key in done:
            status = "completed"
        elif not current_assigned:
            status = "waiting_assistant" if key == "wait_for_team" else "current"
            current_assigned = True
        else:
            status = "locked"
        steps.append(
            {
                "index": index,
                "key": key,
                "label": label,
                "description": description,
                "kind": kind,
                "target": target,
                "status": status,
            }
        )
    return steps


def build_workbench(token: str) -> dict:
    with connect() as db:
        account = account_context(db, token)
        if not account:
            raise PermissionError("登录状态已失效，请重新登录。")
        db.execute("UPDATE accounts SET last_seen = ? WHERE id = ?", (now_ts(), account["id"]))
        steps = workflow_state(db, account)
        done_count = sum(step["status"] == "completed" for step in steps)
        current = next((step for step in steps if step["status"] in {"current", "waiting_assistant"}), steps[-1])
        return {
            "success": True,
            "server_time": now_ts(),
            "scene_code": account["scene_code"],
            "team_code": account["team_code"],
            "member_id": account["member_id"],
            "member_name": MEMBER_NAMES[account["member_id"]],
            "role": account["role"],
            "role_label": "员工",
            "participant_uid": account["participant_uid"],
            "current_stage": current["label"],
            "completed_count": done_count,
            "total_count": len(steps),
            "steps": steps,
        }


def enter_task(token: str, step_key: str) -> dict:
    with connect() as db:
        account = account_context(db, token)
        if not account:
            raise PermissionError("登录状态已失效，请重新登录。")
        step = next((item for item in workflow_state(db, account) if item["key"] == step_key), None)
        if not step or step["kind"] != "task":
            raise ValueError("任务节点不存在。")
        if step["status"] not in {"current", "completed"}:
            raise ValueError("请先完成当前工作流节点。")
        batch_id = TASK_STEP_BATCH[step_key]
        member_name = MEMBER_NAMES[account["member_id"]]
        team_code = account["team_code"]
    task_login = login_participant(team_code, member_name, batch_id)
    return {"success": True, "task_token": task_login["token"], "batch_id": batch_id, "step_key": step_key}


def validate_task_completion(db: sqlite3.Connection, account: sqlite3.Row, step_key: str) -> None:
    batch_id = TASK_STEP_BATCH[step_key]
    session = db.execute(
        "SELECT * FROM team_sessions WHERE team_code = ? AND batch_id = ?",
        (account["team_code"], batch_id),
    ).fetchone()
    if not session:
        raise ValueError("尚未进入该任务，无法完成当前节点。")
    participant = db.execute(
        "SELECT 1 FROM participants WHERE session_id = ? AND member_id = ?",
        (session["id"], account["member_id"]),
    ).fetchone()
    if not participant:
        raise ValueError("尚未进入该任务，无法完成当前节点。")
    if batch_id in {"round_1", "round_2"}:
        if not session["performance_at"] or now_ts() < session["performance_at"]:
            raise ValueError("本轮任务绩效尚未开放，请稍后再返回工作台。")


def complete_workflow_step(token: str, step_key: str) -> dict:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        account = account_context(db, token)
        if not account:
            raise PermissionError("登录状态已失效，请重新登录。")
        step = next((item for item in workflow_state(db, account) if item["key"] == step_key), None)
        if not step:
            raise ValueError("工作流节点不存在。")
        if step["status"] == "completed":
            return {"success": True}
        if step["status"] != "current":
            raise ValueError("当前节点尚未解锁。")
        if step["kind"] == "task":
            validate_task_completion(db, account, step_key)
        elif step["kind"] == "survey":
            raise ValueError("请提交当前问卷后完成此节点。")
        elif step["kind"] == "waiting":
            raise ValueError("请等待团队推广任务A完成。")
        db.execute(
            "INSERT OR IGNORE INTO workflow_progress(account_id, step_key, completed_at) VALUES (?, ?, ?)",
            (account["id"], step_key, now_ts()),
        )
        db.commit()
    return {"success": True}


def parse_client_time(value: str) -> tuple[str, float]:
    raw = str(value or "").strip()
    if not raw:
        return iso_time(), now_ts()
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return iso_time(), now_ts()
    return raw, timestamp


def submit_questionnaire(token: str, payload: dict) -> dict:
    module_name = str(payload.get("module_name", ""))
    answers = payload.get("answers")
    if module_name not in SURVEY_REQUIRED or not isinstance(answers, dict):
        raise ValueError("问卷数据无效。")
    normalized = {str(key): str(value).strip() for key, value in answers.items() if str(value).strip()}
    missing = SURVEY_REQUIRED[module_name] - normalized.keys()
    if missing:
        raise ValueError("请完成全部题目后再提交。")
    page_start_time, started_timestamp = parse_client_time(payload.get("page_start_time", ""))
    submitted_timestamp = now_ts()
    submit_time = iso_time(submitted_timestamp)
    duration = max(0, min(86400, round(submitted_timestamp - started_timestamp)))
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        account = account_context(db, token)
        if not account:
            raise PermissionError("登录状态已失效，请重新登录。")
        step = next((item for item in workflow_state(db, account) if item["key"] == module_name), None)
        if not step or step["kind"] != "survey":
            raise ValueError("当前账号不能填写该问卷。")
        if step["status"] == "completed":
            return {"success": True, "already_submitted": True}
        if step["status"] != "current":
            raise ValueError("请先完成当前工作流节点。")
        for question_id in sorted(SURVEY_REQUIRED[module_name]):
            db.execute(
                """
                INSERT OR REPLACE INTO questionnaire_responses(
                    account_id, session_id, team_id, member_id, role, participant_uid,
                    module_name, question_id, answer, page_start_time, submit_time, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account["id"], account["scene_code"], account["team_code"], account["member_id"],
                    account["role"], account["participant_uid"], module_name, question_id,
                    normalized[question_id], page_start_time, submit_time, duration,
                ),
            )
        db.execute(
            "INSERT OR IGNORE INTO workflow_progress(account_id, step_key, completed_at) VALUES (?, ?, ?)",
            (account["id"], module_name, submitted_timestamp),
        )
        db.commit()
    return {"success": True}


def performance_history(token: str) -> dict:
    with connect() as db:
        account = account_context(db, token)
        if not account:
            raise PermissionError("登录状态已失效，请重新登录。")
        batches = ["practice_b", "round_2"] if account["member_id"] == "04" else ["practice_a", "round_1", "round_2"]
        records = []
        for batch_id in batches:
            session = db.execute(
                "SELECT * FROM team_sessions WHERE team_code = ? AND batch_id = ?",
                (account["team_code"], batch_id),
            ).fetchone()
            if not session:
                records.append({"batch_id": batch_id, "batch_label": BATCHES[batch_id]["label"], "available": False})
                continue
            person = db.execute(
                "SELECT COUNT(*) count, AVG(success_rate) average FROM submissions WHERE session_id = ? AND member_id = ?",
                (session["id"], account["member_id"]),
            ).fetchone()
            team = db.execute(
                "SELECT COUNT(*) count, AVG(success_rate) average FROM submissions WHERE session_id = ?",
                (session["id"],),
            ).fetchone()
            records.append(
                {
                    "batch_id": batch_id,
                    "batch_label": BATCHES[batch_id]["label"],
                    "available": True,
                    "is_practice": batch_id.startswith("practice"),
                    "personal_completed": person["count"],
                    "personal_total": BATCHES[batch_id]["order_count"],
                    "personal_average": round(person["average"]) if person["average"] is not None else 0,
                    "team_completed": team["count"],
                    "team_total": BATCHES[batch_id]["order_count"] * len(BATCHES[batch_id]["required"]),
                    "team_average": round(team["average"]) if team["average"] is not None else 0,
                }
            )
        return {"success": True, "records": records}


def submission_map(db: sqlite3.Connection, session_id: int, member_id: str) -> dict[str, sqlite3.Row]:
    rows = db.execute(
        "SELECT * FROM submissions WHERE session_id = ? AND member_id = ? ORDER BY order_index",
        (session_id, member_id),
    ).fetchall()
    return {row["order_id"]: row for row in rows}


def performance_for(db: sqlite3.Connection, context: sqlite3.Row) -> dict:
    config = BATCHES[context["batch_id"]]
    member_rows = []
    all_scores = []
    for member_id in config["required"]:
        row = db.execute(
            "SELECT COUNT(*) count, AVG(success_rate) average FROM submissions WHERE session_id = ? AND member_id = ?",
            (context["id"], member_id),
        ).fetchone()
        count = int(row["count"] or 0)
        average = round(row["average"]) if row["average"] is not None else 0
        member_rows.append({"member_id": member_id, "completed": count, "average": average})
        scores = db.execute(
            "SELECT success_rate FROM submissions WHERE session_id = ? AND member_id = ?",
            (context["id"], member_id),
        ).fetchall()
        all_scores.extend(item["success_rate"] for item in scores)
    mine = next(item for item in member_rows if item["member_id"] == context["member_id"])
    return {
        "personal_completed": mine["completed"],
        "personal_average": mine["average"],
        "team_completed": sum(item["completed"] for item in member_rows),
        "team_average": round(sum(all_scores) / len(all_scores)) if all_scores else 0,
    }


def build_state(token: str) -> dict:
    with connect() as db:
        context = get_context(db, token)
        if not context:
            raise PermissionError("登录状态已失效，请重新登录。")
        db.execute("UPDATE participants SET last_seen = ? WHERE token = ?", (now_ts(), token))
        config = BATCHES[context["batch_id"]]
        now = now_ts()
        started = context["started_at"] is not None
        ended = bool(started and now >= context["end_at"])
        performance_ready = bool(ended and now >= context["performance_at"])
        if not started:
            phase = "waiting"
        elif not ended:
            phase = "running"
        elif performance_ready:
            phase = "ended_revealed"
        else:
            phase = "ended_waiting"

        joined_rows = db.execute(
            "SELECT member_id FROM participants WHERE session_id = ? ORDER BY member_id", (context["id"],)
        ).fetchall()
        joined_ids = {row["member_id"] for row in joined_rows}
        my_submissions = submission_map(db, context["id"], context["member_id"])
        formal = config["feedback"] == "formal"

        orders = []
        for order in order_rows(context["member_id"], context["batch_id"]):
            item = dict(order)
            submission = my_submissions.get(order["id"])
            item["submitted"] = submission is not None
            if submission:
                item["submission"] = {
                    "gender": submission["gender"],
                    "age": submission["age"],
                    "account_type": submission["account_type"],
                    "format_type": submission["format_type"],
                    "reason_text": submission["reason_text"],
                    "submitted_at": iso_time(submission["submitted_at"]),
                }
                if not formal:
                    item["result"] = practice_feedback(context["batch_id"], order["category"], submission)
            orders.append(item)

        member_progress = []
        for member_id in config["required"]:
            count = db.execute(
                "SELECT COUNT(*) count FROM submissions WHERE session_id = ? AND member_id = ?",
                (context["id"], member_id),
            ).fetchone()["count"]
            member_progress.append(
                {
                    "member_id": member_id,
                    "name": MEMBER_NAMES[member_id],
                    "joined": member_id in joined_ids,
                    "completed": count,
                    "total": config["order_count"],
                    "current": member_id == context["member_id"],
                }
            )

        result = {
            "server_time": now,
            "phase": phase,
            "team_code": context["team_code"],
            "member_id": context["member_id"],
            "member_name": MEMBER_NAMES[context["member_id"]],
            "batch_id": context["batch_id"],
            "batch_label": config["label"],
            "scene_code": context["scene_code"],
            "required_count": len(config["required"]),
            "joined_count": len(joined_ids.intersection(config["required"])),
            "started_at": context["started_at"],
            "end_at": context["end_at"],
            "performance_at": context["performance_at"],
            "duration": config["duration"],
            "order_count": config["order_count"],
            "is_practice": not formal,
            "orders": orders,
            "members": member_progress,
            "options": VALID_OPTIONS,
        }
        if performance_ready and formal:
            result["performance"] = performance_for(db, context)
        return result


def calculate_submission(batch_id: str, category: str, plan: dict) -> tuple[dict, int]:
    rule_set = LEGACY_RULES if BATCHES[batch_id]["rule"] == "legacy" else RECENT_RULES
    rules = rule_set[category]
    scores = {dimension: rules[dimension][plan[dimension]] for dimension in VALID_OPTIONS}
    return scores, round(sum(scores.values()) / len(scores))


def practice_feedback(batch_id: str, category: str, submission: sqlite3.Row) -> dict:
    if batch_id == "practice_a":
        return {
            "kind": "practice_a",
            "title": "系统研判结果",
            "success_rate": submission["success_rate"],
            "items": LEGACY_FEEDBACK[category],
        }
    trend = RECENT_TRENDS[category]
    scores = json.loads(submission["dimension_scores"])
    score = scores[trend["dimension"]]
    label = {90: "匹配程度高", 60: "匹配程度一般", 30: "匹配程度低"}.get(score, "匹配程度一般")
    return {
        "kind": "practice_b",
        "title": "近期趋势反馈",
        "match_label": label,
        "match_score": score,
        "items": [trend["text"]],
    }


def submit_plan(token: str, payload: dict) -> dict:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        context = get_context(db, token)
        if not context:
            raise PermissionError("登录状态已失效，请重新登录。")
        if not context["started_at"]:
            raise ValueError("团队成员尚未全部登录，暂不能提交订单。")
        if now_ts() >= context["end_at"]:
            raise TimeoutError("任务时间已结束，系统已锁定订单提交。")

        order_id = str(payload.get("order_id", ""))
        orders = {order["id"]: order for order in order_rows(context["member_id"], context["batch_id"])}
        order = orders.get(order_id)
        if not order:
            raise ValueError("订单不存在或不属于当前账号。")
        plan = {dimension: str(payload.get(dimension, "")) for dimension in VALID_OPTIONS}
        for dimension, allowed in VALID_OPTIONS.items():
            if plan[dimension] not in allowed:
                raise ValueError("请完成全部推广方案选择。")
        reason_text = str(payload.get("reason_text", "")).strip()
        if len(reason_text) > 200:
            raise ValueError("选择依据备注不能超过 200 个字符。")
        scores, success_rate = calculate_submission(context["batch_id"], order["category"], plan)
        try:
            db.execute(
                """
                INSERT INTO submissions(
                    session_id, member_id, order_id, order_index, brand, product_name, category, price,
                    gender, age, account_type, format_type, reason_text, dimension_scores, success_rate, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context["id"], context["member_id"], order["id"], order["index"], order["brand"], order["name"],
                    order["category"], order["price"], plan["gender"], plan["age"], plan["account_type"],
                    plan["format_type"], reason_text, json.dumps(scores, ensure_ascii=False), success_rate, now_ts(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("该订单已提交，不能再次修改。") from error
        log_event(db, context["id"], context["member_id"], "order_submitted", {"order_id": order_id})
        db.commit()
    return {"ok": True}


OPERATION_HEADERS = [
    "scene_code", "team_code", "batch_id", "batch_label", "member_id", "member_name", "participant_uid", "order_id", "order_index",
    "brand", "product_name", "category", "price", "gender", "age", "account_type", "format_type", "reason_text",
    "gender_score", "age_score", "account_score", "format_score", "success_rate", "submitted_at",
]


def operation_records(db: sqlite3.Connection, where: str = "", params: tuple = ()) -> list[dict]:
    rows = db.execute(
        f"""
        SELECT s.scene_code, s.team_code, s.batch_id, u.*
        FROM submissions u JOIN team_sessions s ON s.id = u.session_id
        {where}
        ORDER BY s.scene_code, s.team_code, s.batch_id, u.member_id, u.order_index
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        scores = json.loads(row["dimension_scores"])
        result.append(
            {
                "scene_code": row["scene_code"], "team_code": row["team_code"], "batch_id": row["batch_id"],
                "batch_label": BATCHES[row["batch_id"]]["label"], "member_id": row["member_id"],
                "member_name": MEMBER_NAMES[row["member_id"]],
                "participant_uid": participant_uid(row["scene_code"], row["team_code"], row["member_id"]),
                "order_id": row["order_id"],
                "order_index": row["order_index"], "brand": row["brand"], "product_name": row["product_name"],
                "category": row["category"], "price": row["price"], "gender": row["gender"], "age": row["age"],
                "account_type": row["account_type"], "format_type": row["format_type"],
                "reason_text": row["reason_text"], "gender_score": scores["gender"], "age_score": scores["age"],
                "account_score": scores["account_type"], "format_score": scores["format_type"],
                "success_rate": row["success_rate"], "submitted_at": iso_time(row["submitted_at"]),
            }
        )
    return result


def performance_records(db: sqlite3.Connection) -> list[dict]:
    sessions = db.execute("SELECT * FROM team_sessions ORDER BY scene_code, team_code, batch_id").fetchall()
    output = []
    for session in sessions:
        config = BATCHES[session["batch_id"]]
        team_row = db.execute(
            "SELECT COUNT(*) count, AVG(success_rate) average FROM submissions WHERE session_id = ?", (session["id"],)
        ).fetchone()
        for member_id in config["required"]:
            person = db.execute(
                "SELECT COUNT(*) count, AVG(success_rate) average FROM submissions WHERE session_id = ? AND member_id = ?",
                (session["id"], member_id),
            ).fetchone()
            output.append(
                {
                    "scene_code": session["scene_code"], "team_code": session["team_code"],
                    "batch_id": session["batch_id"], "batch_label": config["label"], "member_id": member_id,
                    "member_name": MEMBER_NAMES[member_id],
                    "participant_uid": participant_uid(session["scene_code"], session["team_code"], member_id),
                    "personal_completed": person["count"],
                    "personal_average_success_rate": round(person["average"]) if person["average"] is not None else "",
                    "team_completed": team_row["count"],
                    "team_average_success_rate": round(team_row["average"]) if team_row["average"] is not None else "",
                    "task_started_at": iso_time(session["started_at"]) if session["started_at"] else "",
                    "task_end_at": iso_time(session["end_at"]) if session["end_at"] else "",
                }
            )
    return output


SURVEY_HEADERS = [
    "session_id", "team_id", "member_id", "role", "participant_uid", "module_name",
    "question_id", "answer", "page_start_time", "submit_time", "duration_seconds",
]


def questionnaire_records(db: sqlite3.Connection) -> list[dict]:
    return [
        {header: row[header] for header in SURVEY_HEADERS}
        for row in db.execute(
            """
            SELECT session_id, team_id, member_id, role, participant_uid, module_name,
                   question_id, answer, page_start_time, submit_time, duration_seconds
            FROM questionnaire_responses
            ORDER BY session_id, team_id, member_id, module_name, question_id
            """
        ).fetchall()
    ]


def csv_payload(rows: list[dict], headers: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "NimangExperiment/1.0"

    def send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("请求数据过大。")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def token(self) -> str:
        auth = self.headers.get("Authorization", "")
        return auth.removeprefix("Bearer ").strip()

    def require_admin(self) -> None:
        if not secrets.compare_digest(self.headers.get("X-Admin-Key", ""), ADMIN_KEY):
            raise PermissionError("管理员密钥不正确。")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/account/login":
                self.send_json(200, login_account(payload.get("team_code", ""), payload.get("member_id", "")))
                return
            if path == "/api/task/enter":
                self.send_json(200, enter_task(self.token(), str(payload.get("step_key", ""))))
                return
            if path == "/api/workflow/complete":
                self.send_json(200, complete_workflow_step(self.token(), str(payload.get("step_key", ""))))
                return
            if path == "/api/questionnaire/submit":
                self.send_json(200, submit_questionnaire(self.token(), payload))
                return
            if path == "/api/login":
                self.send_json(200, login_participant(payload.get("team_code", ""), payload.get("member_id", ""), payload.get("batch_id", "")))
                return
            if path == "/api/submit":
                self.send_json(200, submit_plan(self.token(), payload))
                return
            if path == "/api/logout":
                with connect() as db:
                    context = get_context(db, self.token())
                    if context:
                        log_event(db, context["id"], context["member_id"], "logout", {})
                self.send_json(200, {"ok": True})
                return
            if path == "/api/admin/settings":
                self.require_admin()
                scene_code = str(payload.get("scene_code", "")).strip().upper()
                if not re.fullmatch(r"S[0-9A-Z-]{1,12}", scene_code):
                    raise ValueError("场次编号格式无效，例如 S01。")
                with connect() as db:
                    db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('scene_code', ?)", (scene_code,))
                self.send_json(200, {"ok": True, "scene_code": scene_code})
                return
            if path == "/api/admin/reset":
                self.require_admin()
                team_code = normalize_team(payload.get("team_code", ""))
                batch_id = str(payload.get("batch_id", ""))
                if batch_id not in BATCHES or not team_code:
                    raise ValueError("请选择要重置的团队与任务批次。")
                with connect() as db:
                    row = db.execute("SELECT id FROM team_sessions WHERE team_code = ? AND batch_id = ?", (team_code, batch_id)).fetchone()
                    if row:
                        db.execute("DELETE FROM team_sessions WHERE id = ?", (row["id"],))
                    reset_steps = {
                        "practice_a": ["practice_a", "round1_arrangement", "round1_task", "round2_arrangement", "round2_task", "performance"],
                        "practice_b": ["practice_b", "recent_trend", "wait_for_team", "round2_arrangement", "round2_task", "performance"],
                        "round_1": ["round1_task", "wait_for_team", "round2_arrangement", "round2_task", "performance"],
                        "round_2": ["round2_task", "performance"],
                    }[batch_id]
                    account_rows = db.execute("SELECT id FROM accounts WHERE team_code = ?", (team_code,)).fetchall()
                    account_ids = [item["id"] for item in account_rows]
                    if account_ids:
                        placeholders = ",".join("?" for _ in account_ids)
                        step_placeholders = ",".join("?" for _ in reset_steps)
                        db.execute(
                            f"DELETE FROM workflow_progress WHERE account_id IN ({placeholders}) AND step_key IN ({step_placeholders})",
                            (*account_ids, *reset_steps),
                        )
                        survey_steps = [step for step in reset_steps if step in SURVEY_REQUIRED]
                        if survey_steps:
                            survey_placeholders = ",".join("?" for _ in survey_steps)
                            db.execute(
                                f"DELETE FROM questionnaire_responses WHERE account_id IN ({placeholders}) AND module_name IN ({survey_placeholders})",
                                (*account_ids, *survey_steps),
                            )
                self.send_json(200, {"ok": True})
                return
            self.send_json(404, {"success": False, "message": "接口不存在。"})
        except PermissionError as error:
            self.send_json(401, {"success": False, "message": str(error)})
        except TimeoutError as error:
            self.send_json(423, {"success": False, "message": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"success": False, "message": str(error)})
        except Exception as error:
            self.send_json(500, {"success": False, "message": f"服务器处理失败：{error}"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/state":
                self.send_json(200, build_state(self.token()))
                return
            if parsed.path == "/api/workbench":
                self.send_json(200, build_workbench(self.token()))
                return
            if parsed.path == "/api/performance-history":
                self.send_json(200, performance_history(self.token()))
                return
            if parsed.path == "/api/admin/settings":
                self.require_admin()
                with connect() as db:
                    scene_code = get_setting(db, "scene_code")
                    counts = {
                        "accounts": db.execute("SELECT COUNT(*) count FROM accounts").fetchone()["count"],
                        "sessions": db.execute("SELECT COUNT(*) count FROM team_sessions").fetchone()["count"],
                        "submissions": db.execute("SELECT COUNT(*) count FROM submissions").fetchone()["count"],
                        "survey_responses": db.execute("SELECT COUNT(*) count FROM questionnaire_responses").fetchone()["count"],
                    }
                self.send_json(200, {"scene_code": scene_code, **counts})
                return
            if parsed.path == "/api/admin/export":
                self.require_admin()
                query = parse_qs(parsed.query)
                export_type = query.get("type", ["all"])[0]
                with connect() as db:
                    scene_code = get_setting(db, "scene_code") or "S01"
                    if export_type == "team":
                        team_code = normalize_team(query.get("team", [""])[0])
                        if not team_code:
                            raise ValueError("请输入团队编号。")
                        rows = operation_records(db, "WHERE s.team_code = ?", (team_code,))
                        label = f"{team_code}_operation_records"
                        headers = OPERATION_HEADERS
                    elif export_type == "scene":
                        rows = operation_records(db, "WHERE s.scene_code = ?", (scene_code,))
                        label = "current_scene_records"
                        headers = OPERATION_HEADERS
                    elif export_type == "performance":
                        rows = performance_records(db)
                        label = "performance_summary"
                        headers = list(rows[0].keys()) if rows else [
                            "scene_code", "team_code", "batch_id", "batch_label", "member_id", "member_name", "participant_uid",
                            "personal_completed", "personal_average_success_rate", "team_completed",
                            "team_average_success_rate", "task_started_at", "task_end_at",
                        ]
                    elif export_type == "survey":
                        rows = questionnaire_records(db)
                        label = "questionnaire_responses"
                        headers = SURVEY_HEADERS
                    else:
                        rows = operation_records(db)
                        label = "all_operation_records"
                        headers = OPERATION_HEADERS
                data = csv_payload(rows, headers)
                filename = f"{scene_code}_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.serve_static(parsed.path)
        except PermissionError as error:
            self.send_json(401, {"success": False, "message": str(error)})
        except ValueError as error:
            self.send_json(400, {"success": False, "message": str(error)})
        except Exception as error:
            self.send_json(500, {"success": False, "message": f"服务器处理失败：{error}"})

    def serve_static(self, request_path: str) -> None:
        relative = unquote(request_path).lstrip("/") or "index.html"
        target = (ROOT / relative).resolve()
        if ROOT not in target.parents and target != ROOT:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".html", ".css", ".js", ".svg"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store" if target.suffix in {".html", ".js"} else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="逆芒推广订单处理系统")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8023)
    args = parser.parse_args()
    init_db()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"逆芒推广订单处理系统已启动：http://{args.host}:{args.port}")
    print(f"操作助手后台：http://{args.host}:{args.port}/admin.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
