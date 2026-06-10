"""
Tag service layer — CRUD สำหรับระบบ Tag สินค้า.
โครงสร้าง: tag_groups (1) → tags (many) → product_tags (many-to-many กับ SKU)

NOTE: product_tags.sku เป็น TEXT ธรรมดา ไม่ใช่ FK ไป master_item.sku
เพราะ save_master_to_db() ทำ TRUNCATE+re-insert ทุกครั้งที่ sync
"""
import streamlit as st
import pandas as pd
from sqlalchemy import text
from .database import get_engine

# ── DDL ──────────────────────────────────────────────────────────────────────
_TAG_DDL = [
    """
    CREATE TABLE IF NOT EXISTS tag_groups (
        id         SERIAL PRIMARY KEY,
        name       TEXT UNIQUE NOT NULL,
        color      VARCHAR(20)  DEFAULT '#FF4B4B',
        sort_order INTEGER      DEFAULT 0,
        is_visible BOOLEAN      DEFAULT TRUE,
        created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tags (
        id         SERIAL PRIMARY KEY,
        group_id   INTEGER      REFERENCES tag_groups(id) ON DELETE CASCADE,
        name       TEXT         NOT NULL,
        color      VARCHAR(20),
        sort_order INTEGER      DEFAULT 0,
        created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (group_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_tags (
        sku        VARCHAR(255) NOT NULL,
        tag_id     INTEGER      REFERENCES tags(id) ON DELETE CASCADE,
        created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (sku, tag_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_product_tags_tag ON product_tags(tag_id)",
    "CREATE INDEX IF NOT EXISTS idx_product_tags_sku ON product_tags(sku)",
]


def ensure_tag_tables():
    """Lazy-init: สร้างตารางถ้ายังไม่มี (ปลอดภัยกับ DB ที่ deploy แล้ว)."""
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in _TAG_DDL:
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))


# ── Cache helpers ─────────────────────────────────────────────────────────────

_DEFAULT_GROUP = "_default_"


def _ensure_default_group(conn) -> int:
    """สร้าง default group ถ้ายังไม่มี และคืน id."""
    row = conn.execute(
        text("SELECT id FROM tag_groups WHERE name = :n"), {"n": _DEFAULT_GROUP}
    ).fetchone()
    if row:
        return row[0]
    result = conn.execute(
        text("INSERT INTO tag_groups (name, color, sort_order) VALUES (:n, :c, 0) RETURNING id"),
        {"n": _DEFAULT_GROUP, "c": "#555555"},
    )
    return result.fetchone()[0]


def _clear():
    """เคลียร์ cache ทุกฟังก์ชันที่อ่านจาก DB."""
    for fn in (get_tag_groups, get_tags, get_products_for_tag,
               get_tag_counts, get_sku_tag_map, get_product_tag_details,
               get_flat_tags, load_all_sku_tags):
        fn.clear()


# ── READ ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_tag_groups(include_hidden: bool = True) -> pd.DataFrame:
    """คืน DataFrame ของ tag_groups เรียงตาม sort_order."""
    engine = get_engine()
    where = "" if include_hidden else "WHERE is_visible = TRUE"
    return pd.read_sql(
        f"SELECT * FROM tag_groups {where} ORDER BY sort_order, id",
        engine
    )


@st.cache_data(ttl=30)
def get_tags(group_id: int = None) -> pd.DataFrame:
    """คืน DataFrame ของ tags (+ group_name, group_color) เรียงตาม sort_order."""
    engine = get_engine()
    if group_id is not None:
        return pd.read_sql(
            "SELECT * FROM tags WHERE group_id = %(gid)s ORDER BY sort_order, id",
            engine, params={"gid": group_id}
        )
    return pd.read_sql(
        """
        SELECT t.*, tg.name AS group_name, tg.color AS group_color
        FROM   tags t
        JOIN   tag_groups tg ON t.group_id = tg.id
        ORDER  BY tg.sort_order, tg.id, t.sort_order, t.id
        """,
        engine
    )


@st.cache_data(ttl=30)
def get_products_for_tag(tag_id: int) -> list:
    """คืน list ของ SKU ที่อยู่ใน tag นี้."""
    engine = get_engine()
    df = pd.read_sql(
        "SELECT sku FROM product_tags WHERE tag_id = %(tid)s ORDER BY sku",
        engine, params={"tid": tag_id}
    )
    return df["sku"].tolist()


@st.cache_data(ttl=30)
def get_tag_counts() -> dict:
    """คืน {tag_id: จำนวน SKU}."""
    engine = get_engine()
    df = pd.read_sql(
        "SELECT tag_id, COUNT(*) AS cnt FROM product_tags GROUP BY tag_id",
        engine
    )
    if df.empty:
        return {}
    return dict(zip(df["tag_id"].astype(int), df["cnt"].astype(int)))


@st.cache_data(ttl=30)
def get_product_tag_details() -> "pd.DataFrame":
    """
    คืน DataFrame ของทุก assignment: sku, tag_id, group_name, tag_name.
    ใช้สำหรับ Product tab (แสดง + จัดการ per-product).
    """
    engine = get_engine()
    return pd.read_sql(
        """
        SELECT pt.sku,
               t.id   AS tag_id,
               tg.name AS group_name,
               t.name  AS tag_name
        FROM   product_tags pt
        JOIN   tags t        ON pt.tag_id   = t.id
        JOIN   tag_groups tg ON t.group_id  = tg.id
        ORDER  BY pt.sku, tg.sort_order, tg.id, t.sort_order, t.id
        """,
        engine,
    )


@st.cache_data(ttl=10)
def get_sku_tag_map() -> dict:
    """
    Public API สำหรับ views อื่น.
    คืน {sku: [tag_name, ...]} — แต่ละ SKU มีหลาย tag ได้.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT pt.sku,
                   t.name  AS tag_name
            FROM   product_tags pt
            JOIN   tags t        ON pt.tag_id  = t.id
            JOIN   tag_groups tg ON t.group_id = tg.id
            ORDER  BY pt.sku, tg.sort_order, t.sort_order
            """
        )).fetchall()
    result: dict = {}
    for row in rows:
        result.setdefault(row[0], []).append(row[1])
    return result


# ── WRITE — tag_groups ────────────────────────────────────────────────────────

def add_tag_group(name: str, color: str = "#FF4B4B") -> bool:
    """เพิ่ม tag group ใหม่ คืน False ถ้าชื่อซ้ำ."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            max_order = conn.execute(
                text("SELECT COALESCE(MAX(sort_order), 0) FROM tag_groups")
            ).scalar()
            conn.execute(
                text("INSERT INTO tag_groups (name, color, sort_order) VALUES (:n, :c, :so)"),
                {"n": name.strip(), "c": color, "so": int(max_order) + 1}
            )
        _clear()
        return True
    except Exception:
        return False


def rename_tag_group(group_id: int, new_name: str) -> bool:
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tag_groups SET name = :n WHERE id = :id"),
                {"n": new_name.strip(), "id": group_id}
            )
        _clear()
        return True
    except Exception:
        return False


def delete_tag_group(group_id: int) -> bool:
    """ลบ group พร้อม tags และ product_tags ที่เกี่ยวข้อง (CASCADE)."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM tag_groups WHERE id = :id"), {"id": group_id})
        _clear()
        return True
    except Exception:
        return False


def set_group_visibility(group_id: int, visible: bool) -> bool:
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tag_groups SET is_visible = :v WHERE id = :id"),
                {"v": visible, "id": group_id}
            )
        _clear()
        return True
    except Exception:
        return False


# ── WRITE — tags ──────────────────────────────────────────────────────────────

def add_tag(group_id: int, name: str) -> bool:
    """เพิ่ม tag ใหม่ในกลุ่ม คืน False ถ้าชื่อซ้ำในกลุ่มเดียวกัน."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            max_order = conn.execute(
                text("SELECT COALESCE(MAX(sort_order), 0) FROM tags WHERE group_id = :gid"),
                {"gid": group_id}
            ).scalar()
            conn.execute(
                text("INSERT INTO tags (group_id, name, sort_order) VALUES (:gid, :n, :so)"),
                {"gid": group_id, "n": name.strip(), "so": int(max_order) + 1}
            )
        _clear()
        return True
    except Exception:
        return False


def rename_tag(tag_id: int, new_name: str) -> bool:
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tags SET name = :n WHERE id = :id"),
                {"n": new_name.strip(), "id": tag_id}
            )
        _clear()
        return True
    except Exception:
        return False


def delete_tag(tag_id: int) -> bool:
    """ลบ tag พร้อม product_tags ที่เกี่ยวข้อง (CASCADE)."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM tags WHERE id = :id"), {"id": tag_id})
        _clear()
        return True
    except Exception:
        return False


# ── WRITE — product_tags ──────────────────────────────────────────────────────

def set_tag_members(tag_id: int, skus: list) -> bool:
    """
    แทนที่สมาชิกทั้งหมดของ tag ด้วย skus list ใหม่.
    เป็นหัวใจของการ sync หลัง drag-and-drop.
    """
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM product_tags WHERE tag_id = :tid"), {"tid": tag_id})
            for sku in skus:
                sku_clean = str(sku).strip()
                if sku_clean:
                    conn.execute(
                        text(
                            "INSERT INTO product_tags (sku, tag_id) VALUES (:sku, :tid)"
                            " ON CONFLICT DO NOTHING"
                        ),
                        {"sku": sku_clean, "tid": tag_id}
                    )
        _clear()
        return True
    except Exception:
        return False


def assign_tag(sku: str, tag_id: int) -> bool:
    """ติด tag เดียวกับ SKU (ไม่ลบของเดิม)."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO product_tags (sku, tag_id) VALUES (:sku, :tid)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"sku": sku.strip(), "tid": tag_id}
            )
        _clear()
        return True
    except Exception:
        return False


def unassign_tag(sku: str, tag_id: int) -> bool:
    """ถอด tag ออกจาก SKU."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM product_tags WHERE sku = :sku AND tag_id = :tid"),
                {"sku": sku.strip(), "tid": tag_id}
            )
        _clear()
        return True
    except Exception:
        return False


# ── Flat Tag API (UI ไม่แสดง group hierarchy) ─────────────────────────────────

@st.cache_data(ttl=60)
def get_flat_tags() -> list:
    """คืน [{id, name, color}] ของทุก tag (ไม่สนใจ group)."""
    engine = get_engine()
    df = pd.read_sql(
        "SELECT id, name, color FROM tags ORDER BY sort_order, id",
        engine,
    )
    return df.to_dict("records")


def add_flat_tag(name: str, color: str = "#FF4B4B") -> bool:
    """เพิ่ม tag ใหม่ใน default group (สร้าง group ถ้ายังไม่มี)."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            grp_id = _ensure_default_group(conn)
            max_order = conn.execute(
                text("SELECT COALESCE(MAX(sort_order),0) FROM tags WHERE group_id=:g"),
                {"g": grp_id},
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO tags (group_id, name, color, sort_order)"
                    " VALUES (:g, :n, :c, :so)"
                ),
                {"g": grp_id, "n": name.strip(), "c": color, "so": int(max_order) + 1},
            )
        _clear()
        return True
    except Exception:
        return False


def delete_flat_tag(tag_id: int) -> bool:
    """ลบ tag (+ product_tags ที่เกี่ยวข้อง via CASCADE)."""
    return delete_tag(tag_id)


@st.cache_data(ttl=60)
def load_all_sku_tags() -> dict:
    """
    คืน {sku: [tag_id, ...]} ของทุก assignment ใน DB.
    ใช้ initialize session state ตอน load หน้า (โหลดครั้งเดียว).
    """
    engine = get_engine()
    df = pd.read_sql(
        "SELECT sku, tag_id FROM product_tags ORDER BY sku, tag_id",
        engine,
    )
    result: dict = {}
    if not df.empty:
        for _, row in df.iterrows():
            result.setdefault(row["sku"], []).append(int(row["tag_id"]))
    return result


LAST_ERROR = ""


def batch_save_sku_tags(assignments: dict) -> bool:
    """
    Batch-write assignments {sku: [tag_id, ...]} ลง DB ครั้งเดียว.
    รัน transaction เดียว — เหมาะกับ save button (ไม่ call ระหว่าง drag).
    ถ้า fail: คืน False และเก็บสาเหตุไว้ใน LAST_ERROR.
    """
    global LAST_ERROR
    try:
        engine = get_engine()
        with engine.begin() as conn:
            for sku, tag_ids in assignments.items():
                sku_clean = str(sku).strip()
                if not sku_clean:
                    continue
                conn.execute(
                    text("DELETE FROM product_tags WHERE sku = :sku"),
                    {"sku": sku_clean},
                )
                for tid in tag_ids:
                    conn.execute(
                        text(
                            "INSERT INTO product_tags (sku, tag_id)"
                            " VALUES (:sku, :tid) ON CONFLICT DO NOTHING"
                        ),
                        {"sku": sku_clean, "tid": int(tid)},
                    )
        _clear()
        LAST_ERROR = ""
        return True
    except Exception as e:
        LAST_ERROR = f"{type(e).__name__}: {e}"
        print(f"batch_save_sku_tags FAILED: {LAST_ERROR}")
        return False
