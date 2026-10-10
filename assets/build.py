# -*- coding: utf-8 -*-
"""出游信息地图生成器 —— 参数化引擎。

一份模板 + 每个目的地一份 trip.json，产出单文件 index.html（零外部依赖，仅底图瓦片需联网）。

用法：
    python build.py --trip <trip.json> [--out <输出html>] [--check-only] [--quiet]

设计要点：
  * 模板 assets/templates/index.template.html 与地区无关，通过 __占位符__ 注入。
  * 所有地区/主题专属内容（标题、文案、坐标、瓦片源、类别配色、备注块）都在 trip.json。
  * 构建期硬断言：类别未归类、字段缺失、星标不唯一、来源截图缺失等一律直接报错，
    绝不"静默降级"——这是「不编造、不冒充精确」的执行闸门。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "templates", "index.template.html")

# 每条数据必填 / 选填字段
REQUIRED_FIELDS = ("id", "n", "ty", "ar")
KNOWN_FIELDS = {"id", "n", "ty", "ar", "ad", "ds", "rm", "src", "lat", "lng", "loc", "img", "star", "offmap"}


class BuildError(Exception):
    pass


def fail(msg):
    raise BuildError(msg)


# ---------------------------------------------------------------- 校验
def validate(cfg, spots):
    """构建期硬断言。任何一条不通过即中止构建。"""
    errs, warns = [], []

    # --- 数据基本字段 ---
    seen_ids = set()
    for i, s in enumerate(spots):
        tag = "第 %d 条(%s)" % (i + 1, s.get("n") or "无名")
        for f in REQUIRED_FIELDS:
            if not s.get(f):
                errs.append("%s 缺必填字段 %s" % (tag, f))
        if not isinstance(s.get("id"), int):
            errs.append("%s id 必须是整数，当前 %r" % (tag, s.get("id")))
        elif s["id"] in seen_ids:
            errs.append("%s id 重复：%s" % (tag, s["id"]))
        else:
            seen_ids.add(s["id"])

        # 未知字段：容忍但提示，便于发现拼写错误（如 loc 写成 lac）
        unknown = set(s) - KNOWN_FIELDS
        if unknown:
            warns.append("%s 含未识别字段 %s（拼写错误？）" % (tag, sorted(unknown)))

        # 坐标必须成对
        has_lat, has_lng = s.get("lat") is not None, s.get("lng") is not None
        if has_lat != has_lng:
            errs.append("%s 经纬度必须成对出现（lat=%r lng=%r）" % (tag, s.get("lat"), s.get("lng")))
        if has_lat:
            if not (-90 <= s["lat"] <= 90):
                errs.append("%s 纬度越界：%r" % (tag, s["lat"]))
            if not (-180 <= s["lng"] <= 180):
                errs.append("%s 经度越界：%r" % (tag, s["lng"]))

        # loc 只允许省略 / "exact"（精确定位）/ "approx"（区域近似）
        if s.get("loc") not in (None, "exact", "approx"):
            errs.append("%s loc 只允许省略、\"exact\" 或 \"approx\"，当前 %r" % (tag, s.get("loc")))

    # --- 类别体系必须覆盖全部 ty（漏一个即报错）---
    groups = cfg.get("categoryGroups") or []
    if not groups:
        fail("trip.json 缺少 categoryGroups —— 类别配色体系是必需的")
    type_color, covered = {}, set()
    for g in groups:
        for r in ("name", "color", "types"):
            if not g.get(r):
                fail("categoryGroups 某项缺字段 %s：%r" % (r, g))
        for t in g["types"]:
            if t in type_color:
                errs.append("类别 %r 被多个分组重复定义" % t)
            type_color[t] = g["color"]
            covered.add(t)
    used = {s["ty"] for s in spots}
    missing = sorted(used - covered)
    if missing:
        errs.append(
            "以下 %d 个类别未归入任何 categoryGroups，构建中止（防止地图上出现无名灰点）：%s"
            % (len(missing), "、".join(missing))
        )
    unused = sorted(covered - used)
    if unused:
        warns.append("categoryGroups 中 %d 个类别本次数据未用到：%s" % (len(unused), "、".join(unused)))

    # --- 唯一星标（住处/锚点）---
    stars = [s for s in spots if s.get("star")]
    if len(stars) > 1:
        errs.append("star:true 的条目有 %d 个，必须唯一（地图上只应有一枚五角星）：%s"
                    % (len(stars), "、".join(x["n"] for x in stars)))
    if stars and stars[0].get("lat") is None:
        errs.append("star 条目「%s」没有坐标，无法落星" % stars[0]["n"])
    if not stars:
        warns.append("没有任何 star:true 条目 —— 「以住处为基准算距离」功能将不可用")

    # --- 口径互斥且并集为全集 ---
    def cls(s):
        if s.get("offmap"):
            return "offmap"
        if s.get("lat") is None:
            return "noloc"
        if s.get("loc") == "approx":
            return "approx"
        return "exact"

    buckets = {"exact": 0, "approx": 0, "noloc": 0, "offmap": 0}
    for s in spots:
        buckets[cls(s)] += 1
    if sum(buckets.values()) != len(spots):
        errs.append("口径分档之和(%d) ≠ 总数(%d)" % (sum(buckets.values()), len(spots)))

    # --- 备注块 ---
    for n in cfg.get("notes") or []:
        if not n.get("title"):
            errs.append("notes 某项缺 title")
        if n.get("position", "head") not in ("head", "tail"):
            errs.append("notes 的 position 只允许 head/tail，当前 %r" % n.get("position"))

    return errs, warns, {"buckets": buckets, "stars": len(stars), "types": len(used), "groups": len(groups), "typeColor": type_color}


# ---------------------------------------------------------------- 渲染
def check_assets(cfg, spots, out_dir):
    """来源截图存在性校验。

    返回 (info, warn, err)。这是防止线上详情页裂图的闸门——src 是相对路径，
    缺图不会抛错，只会静默 404，往往要等页面发出去才被发现。

    分级判定：全部缺失（多为配置样例 / 还没放图）→ 告警；部分缺失 → 报错中止，
    因为那才是真遗漏。
    """
    root = os.path.abspath(os.path.join(out_dir, cfg.get("meta", {}).get("assetRoot", ".")))
    imgs = [s["img"] for s in spots if s.get("img")]
    if not imgs:
        return None, None, None
    if not os.path.isdir(root):
        return None, "assetRoot 目录不存在，已跳过来源截图校验：%s" % root, None
    miss = [p for p in imgs if not os.path.exists(os.path.join(root, p.replace("/", os.sep)))]
    if not miss:
        return "已校验 %d 张来源截图，全部存在" % len(imgs), None, None
    if len(miss) == len(imgs):
        return None, ("%d 张来源截图在 %s 下全部找不到。若你确实有图，请检查 assetRoot 与输出目录；"
                      "若这是配置样例（本就不含图），可忽略。" % (len(miss), root)), None
    return None, None, "有 %d/%d 张来源截图缺失（线上会裂图）：%s" % (
        len(miss), len(imgs), "、".join(miss[:5]))


def render_notes(items):
    """把 notes 配置渲染成 HTML 片段。section 为分组小标题（可选）。"""
    if not items:
        return "<!-- 无 -->"
    out = ['<div class="notes">']
    for n in items:
        if n.get("section"):
            out.append('  <div class="sect">%s</div>' % n["section"])
        out.append('  <details class="note">')
        out.append('    <summary>%s</summary>' % n["title"])
        out.append('    <ul>')
        for it in n.get("items") or []:
            out.append('      <li>%s</li>' % it)
        out.append('    </ul>')
        out.append('  </details>')
    out.append('</div>')
    return "\n        ".join(out)


def build(trip_path, out_path=None, check_only=False, quiet=False):
    trip_path = os.path.abspath(trip_path)
    base = os.path.dirname(trip_path)
    with open(trip_path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["_baseDir"] = base

    meta = cfg.get("meta") or {}
    data_rel = meta.get("data")
    if not data_rel:
        fail("trip.json 的 meta.data 未指定数据文件")
    data_path = data_rel if os.path.isabs(data_rel) else os.path.join(base, data_rel)
    if not os.path.exists(data_path):
        fail("数据文件不存在：%s" % data_path)
    with open(data_path, encoding="utf-8") as f:
        spots = json.load(f)

    errs, warns, stat = validate(cfg, spots)
    if errs:
        print("✗ 构建期校验未通过（%d 项）：" % len(errs), file=sys.stderr)
        for e in errs:
            print("   - " + e, file=sys.stderr)
        fail("已中止，未生成任何文件。请修好数据后重跑。")
    if warns and not quiet:
        for w in warns:
            print("  ⚠ " + w)

    if check_only:
        print("✓ 校验通过（未生成文件）")
        return stat

    # --- 组装 CFG（注入前端）---
    labels = dict(cfg.get("labels") or {})
    labels.setdefault("fallbackColor", (cfg.get("theme") or {}).get("fallbackColor", "#7f8c8d"))
    fcfg = {
        "geo": cfg["geo"],
        "lodging": cfg.get("lodging") or {},
        "navSrc": meta.get("slug") or "trip-map",
        "labels": labels,
        "typeColor": stat["typeColor"],
        "fallbackColor": labels["fallbackColor"],
    }

    theme = cfg.get("theme") or {}
    texts = cfg.get("texts") or {}
    notes = cfg.get("notes") or []

    tpl_path = cfg.get("template") or TEMPLATE
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()

    with open(os.path.join(HERE, "vendor", "leaflet.css"), encoding="utf-8") as f:
        lcss = f.read()
    with open(os.path.join(HERE, "vendor", "leaflet.js"), encoding="utf-8") as f:
        ljs = f.read()

    repl = {
        "__LEAFLET_CSS__": lcss,
        "__LEAFLET_JS__": ljs,
        "__DATA__": json.dumps(spots, ensure_ascii=False),
        "__CFG__": json.dumps(fcfg, ensure_ascii=False),
        "__TITLE__": text(cfg.get("meta", {}).get("title", "")),
        "__H1__": text(cfg.get("meta", {}).get("h1", "")),
        "__H1_ACCENT__": text(cfg.get("meta", {}).get("h1Accent", "")),
        "__SUB__": texts.get("sub", ""),
        "__HINT__": texts.get("hint", ""),
        "__MAPFAIL__": texts.get("mapfail", "⚠️ 底图瓦片加载失败，请检查网络后刷新。"),
        "__PLACEHOLDER__": text(texts.get("placeholder", "搜索名称 / 关键词…")),
        "__DETAILHOME__": texts.get("detailHome", "<h3>点选一个地点</h3>"),
        "__STATS_OFFMAP__": text(texts.get("statsOffmap", "其他地点不标注")),
        "__STATS_NOTE__": texts.get("statsNote", ""),
        "__LODGING_BTN__": text(labels.get("lodgingBtn", "🏨 以住处为基准算距离")),
        "__MAPBAR_TITLE__": text(labels.get("mapbarTitle", "🗺️ 地图")),
        "__MAPBAR_COLLAPSE__": text(labels.get("mapbarCollapse", "收起 ▲")),
        "__NOTES_HEAD__": render_notes([n for n in notes if n.get("position", "head") == "head"]),
        "__NOTES_TAIL__": render_notes([n for n in notes if n.get("position") == "tail"]),
        "__ACCENT__": theme.get("accent", "#b5443a"),
        "__ACCENT_DARK__": theme.get("accentDark", "#9c382f"),
        "__ACCENT_RGB__": theme.get("accentRgb", "181,68,58"),
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    left = re.findall(r"__[A-Z][A-Z0-9_]*__", html)
    if left:
        fail("模板中仍有未替换的占位符：%s" % sorted(set(left)))

    out = out_path or os.path.join(base, meta.get("output", "index.html"))
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    ainfo, awarn, aerr = check_assets(cfg, spots, os.path.dirname(out))
    if aerr:
        fail(aerr)
    if awarn and not quiet:
        print("  ⚠ " + awarn)
    if ainfo and not quiet:
        print("  · " + ainfo)

    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    if not quiet:
        b = stat["buckets"]
        print("✓ 已生成 %s" % out)
        print("  条目 %d ＝ 精确 %d + 区域近似 %d + 未定位 %d + 不标注 %d ｜ 星标 %d ｜ 类别 %d 组 / %d 型"
              % (len(spots), b["exact"], b["approx"], b["noloc"], b["offmap"],
                 stat["stars"], stat["groups"], stat["types"]))
        print("  大小 %.1f KB" % (len(html.encode("utf-8")) / 1024))
    return stat


def text(v):
    """轻量 HTML 转义（仅用于纯文本字段；含标签的长文案请放 texts.*，原样注入）。"""
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    ap = argparse.ArgumentParser(description="出游信息地图生成器")
    ap.add_argument("--trip", required=True, help="trip.json 路径")
    ap.add_argument("--out", help="输出 html 路径（默认取 meta.output）")
    ap.add_argument("--check-only", action="store_true", help="只校验不生成")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    try:
        build(a.trip, a.out, a.check_only, a.quiet)
    except BuildError as e:
        print("构建失败：%s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
