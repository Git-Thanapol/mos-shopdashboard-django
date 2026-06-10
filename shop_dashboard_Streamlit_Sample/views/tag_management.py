"""
Tag Management — สินค้าเป็นหลัก, เลือก tags ด้วย st.multiselect

Flow (ลด rerun):
  1. เลือก tag → on_change callback อัป _PENDING ทันที (ก่อน rerun)
  2. rerun นั้นเห็น save button enabled พร้อม
  3. คลิก save → บันทึก DB + อัป _DB_SNAP + st.rerun() ครั้งเดียว
  4. rerun สุดท้าย: save button disabled สถานะสะอาด
"""
import random
import streamlit as st
import modules.tags as tag_svc

_TAG_COLORS = [
    "#FF4757", "#FF6B35", "#FFA502", "#2ED573",
    "#1E90FF", "#5352ED", "#A29BFE", "#FD79A8",
    "#E84393", "#00CEC9", "#00B894", "#6C5CE7",
    "#0984E3", "#FF3F8E", "#7BED9F", "#FF6348",
]

_PENDING = "tag_pending"   # {sku: [tag_id, ...]}
_DB_SNAP = "tag_db_snap"   # {sku: [tag_id, ...]} — updated in-place after save
_MS_V    = "tag_ms_v"      # int — bump เฉพาะเมื่อ tag list เปลี่ยน (add/delete tag)


def _msv() -> int:
    return st.session_state.get(_MS_V, 0)


def _init_state(sku_list: list):
    if _PENDING not in st.session_state:
        db = tag_svc.load_all_sku_tags()
        snap = {sku: list(db.get(str(sku), [])) for sku in sku_list}
        st.session_state[_PENDING] = {k: list(v) for k, v in snap.items()}
        st.session_state[_DB_SNAP] = snap


def _pending_count() -> int:
    pending = st.session_state.get(_PENDING, {})
    snap    = st.session_state.get(_DB_SNAP, {})
    return sum(1 for s, tids in pending.items()
               if set(tids) != set(snap.get(s, [])))


def _reset_state():
    """เรียกเมื่อ tag list เปลี่ยน (add/delete tag) — ต้องตามด้วย st.rerun()"""
    for key in (_PENDING, _DB_SNAP):
        st.session_state.pop(key, None)
    st.session_state[_MS_V] = _msv() + 1


def _on_tag_change(sku, tag_name_to_id: dict, key: str):
    """
    on_change callback: รันก่อน rerun → _PENDING อัปเดตทันที
    ทำให้ save button เป็น enabled ใน rerun เดียวกันกับที่ user เลือก tag
    """
    selected = st.session_state.get(key, [])
    new_ids  = [tag_name_to_id[n] for n in selected if n in tag_name_to_id]
    st.session_state.setdefault(_PENDING, {})[sku] = new_ids


# ── tag manager panel ─────────────────────────────────────────────────────────

def _render_tag_manager():
    tags = tag_svc.get_flat_tags()

    st.markdown("**แท็กที่มีทั้งหมด:**")
    if tags:
        cards_html = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 16px">'
        for t in tags:
            c = t["color"] or "#888"
            cards_html += (
                f'<div style="border:1px solid {c};border-left:4px solid {c};'
                f'border-radius:8px;padding:8px 18px;min-width:90px;text-align:center;'
                f'background:rgba(255,255,255,0.04)">'
                f'<div style="color:{c};font-size:9px;font-weight:700;'
                f'letter-spacing:0.8px;margin-bottom:4px;text-transform:uppercase">TAG</div>'
                f'<div style="color:#f0f0f0;font-size:13px;font-weight:600">{t["name"]}</div>'
                f'</div>'
            )
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)

        # ── delete ────────────────────────────────────────────────────────────
        tag_names = [t["name"] for t in tags]
        cd, cb = st.columns([4, 1])
        with cd:
            del_choice = st.selectbox(
                "del", tag_names, index=None,
                placeholder="เลือกแท็กที่ต้องการลบ...",
                label_visibility="collapsed", key="ftag_del_choice",
            )
        with cb:
            if st.button("🗑️ ลบ", key="ftag_del_btn", use_container_width=True,
                         disabled=(del_choice is None)):
                tag_id = next((t["id"] for t in tags if t["name"] == del_choice), None)
                if tag_id:
                    tag_svc.delete_flat_tag(tag_id)
                    _reset_state()
                    st.rerun()
    else:
        st.caption("ยังไม่มีแท็ก")

    st.markdown("---")
    st.markdown("**➕ เพิ่มแท็กใหม่:**")
    ca, cb = st.columns([4, 1])
    with ca:
        new_name = st.text_input("nn", placeholder="ชื่อแท็ก เช่น Flash Sale, หน้าร้อน...",
                                 label_visibility="collapsed", key="ftag_new_name")
    with cb:
        if st.button("➕ เพิ่ม", key="ftag_add", use_container_width=True, type="primary"):
            if new_name.strip():
                color = random.choice(_TAG_COLORS)
                if tag_svc.add_flat_tag(new_name.strip(), color):
                    st.toast(f"✅ เพิ่มแท็ก «{new_name.strip()}»")
                    _reset_state()
                    st.rerun()
                else:
                    st.error("ชื่อแท็กนี้มีอยู่แล้ว")


# ── main view ─────────────────────────────────────────────────────────────────

def show(df_daily, df_fix_cost, sku_map, sku_list, sku_type_map, category_options=None):
    tag_svc.ensure_tag_tables()

    st.markdown(
        '<div class="header-bar"><div class="header-title">'
        '<i class="fas fa-tags"></i> ระบบจัดการแท็กสินค้า</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    _init_state(sku_list)

    all_tags       = tag_svc.get_flat_tags()
    tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
    tag_name_to_id = {t["name"]: t["id"] for t in all_tags}
    tag_options    = [t["name"] for t in all_tags]

    # ── toolbar ───────────────────────────────────────────────────────────────
    c_search, c_save, c_mgmt = st.columns([3, 1, 1])

    with c_search:
        search = st.text_input(
            "tm_search",
            placeholder="🔍 ค้นหา SKU หรือชื่อสินค้า...",
            label_visibility="collapsed",
            key="tm_search_box",
        )

    # n_pending อ่านหลัง on_change callback วิ่งแล้ว → ตัวเลขถูกต้องทันที
    n_pending = _pending_count()

    with c_save:
        save_label = f"💾 บันทึก ({n_pending})" if n_pending else "💾 บันทึก"
        if st.button(save_label, type="primary", use_container_width=True,
                     disabled=(n_pending == 0)):
            snap    = st.session_state.get(_DB_SNAP, {})
            pending = st.session_state.get(_PENDING, {})
            changed = {s: tids for s, tids in pending.items()
                       if set(tids) != set(snap.get(s, []))}
            if tag_svc.batch_save_sku_tags(changed):
                # อัป snap in-place → n_pending = 0 หลัง rerun
                for s, tids in changed.items():
                    st.session_state[_DB_SNAP][s] = list(tids)
                st.toast(f"✅ บันทึก {len(changed)} สินค้าสำเร็จ")
                st.rerun()   # 1 rerun เพื่อแสดง save button disabled
            else:
                st.error(f"เกิดข้อผิดพลาดขณะบันทึก: {tag_svc.LAST_ERROR}")

    with c_mgmt:
        if st.button("⚙️ แท็ก", use_container_width=True):
            st.session_state.show_ftag_mgmt = not st.session_state.get("show_ftag_mgmt", False)

    if st.session_state.get("show_ftag_mgmt", False):
        with st.container(border=True):
            _render_tag_manager()

    st.markdown("")

    if not all_tags:
        st.info("💡 ยังไม่มีแท็ก — กด **⚙️ แท็ก** เพื่อเพิ่มแท็กแรก")
        return

    # ── filter ────────────────────────────────────────────────────────────────
    sq = search.strip().lower()
    filtered = [s for s in sku_list
                if not sq
                or sq in str(s).lower()
                or sq in str(sku_map.get(s, "")).lower()]

    if not filtered:
        st.info(f"ไม่พบสินค้าที่ตรงกับ «{search}»")
        return

    _PAGE = 20
    showing = filtered[:_PAGE]
    if len(filtered) > _PAGE:
        st.caption(f"💡 แสดง {_PAGE} / {len(filtered)} รายการ — ค้นหาเพื่อกรองให้แคบลง")

    # ── product rows ──────────────────────────────────────────────────────────
    pending = st.session_state[_PENDING]
    msv     = _msv()

    for sku in showing:
        sku_str   = str(sku)
        name      = str(sku_map.get(sku, sku))
        cur_ids   = pending.get(sku, [])
        cur_names = [tag_id_to_name[tid] for tid in cur_ids if tid in tag_id_to_name]
        ms_key    = f"ms_{sku_str}_v{msv}"

        with st.container(border=True):
            col_info, col_tags = st.columns([2, 3])
            with col_info:
                st.markdown(f"**`{sku_str}`**")
                st.caption(name)
            with col_tags:
                st.multiselect(
                    f"tag_{sku_str}",
                    options=tag_options,
                    default=cur_names,
                    key=ms_key,
                    label_visibility="collapsed",
                    placeholder="เลือกแท็ก...",
                    on_change=_on_tag_change,
                    args=(sku, tag_name_to_id, ms_key),
                )

    # ── overview table ────────────────────────────────────────────────────────
    st.markdown("")
    with st.expander("📋 ดูภาพรวมแท็กสินค้าทั้งหมด", expanded=False):
        _render_overview_table(sku_list, sku_map, tag_id_to_name, sq)


# ── overview table (read-only) ────────────────────────────────────────────────

def _render_overview_table(sku_list: list, sku_map: dict, tag_id_to_name: dict,
                           filter_term: str = ""):
    pending = st.session_state.get(_PENDING, {})
    fq = filter_term.strip().lower()

    _CHIP = (
        "background:#7b1fa2;color:#fff;border-radius:10px;"
        "padding:2px 8px;font-size:11px;margin:1px;display:inline-block"
    )

    rows = []
    for sku in sku_list:
        name = sku_map.get(sku, sku)
        if fq and fq not in str(sku).lower() and fq not in str(name).lower():
            continue
        tag_ids   = pending.get(sku, [])
        tag_names = [tag_id_to_name[t] for t in tag_ids if t in tag_id_to_name]
        chips = "".join(
            f'<span style="{_CHIP}">🏷️ {tn}</span>' for tn in tag_names
        ) if tag_names else '<span style="color:#555;font-size:11px">—</span>'
        rows.append(
            f'<tr><td style="font-family:monospace;font-size:12px;padding:4px 8px;'
            f'white-space:nowrap">{sku}</td>'
            f'<td style="font-size:12px;padding:4px 8px">{name}</td>'
            f'<td style="padding:4px 8px">{chips}</td></tr>'
        )

    if not rows:
        st.caption("ไม่พบสินค้า")
        return

    st.markdown(
        '<table style="width:100%;border-collapse:collapse">'
        '<thead><tr style="border-bottom:1px solid #444">'
        '<th style="text-align:left;padding:4px 8px;font-size:12px">SKU</th>'
        '<th style="text-align:left;padding:4px 8px;font-size:12px">ชื่อสินค้า</th>'
        '<th style="text-align:left;padding:4px 8px;font-size:12px">แท็ก</th>'
        '</tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>",
        unsafe_allow_html=True,
    )
