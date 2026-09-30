"""Editable website data and small, shared validation rules."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "news": ("消息与报道", "list"),
    "gallery": ("活动相册", "list"),
    "structure": ("本会架构", "dict"),
    "tici": ("题词", "list"),
    "hexin": ("贺信", "list"),
    "site": ("页面文字", "dict"),
}


def path_for(name):
    if name not in DATASETS:
        raise ValueError("未知内容分类")
    filename = "site-content" if name == "site" else name
    return ROOT / "assets" / f"{filename}.json"


def load(name):
    return json.loads(path_for(name).read_text(encoding="utf-8"))


def validate(name, value):
    kind = DATASETS[name][1]
    if not isinstance(value, list if kind == "list" else dict):
        raise ValueError("内容格式不正确")
    if name in ("news", "gallery"):
        seen = set()
        media = json.loads((ROOT / "assets" / "image-variants.json").read_text())
        for row in value:
            if not isinstance(row, dict) or not isinstance(row.get("title"), str) or not row["title"].strip():
                raise ValueError("每条内容都需要标题")
            pattern = r"\d{4}-\d{2}-\d{2}" if name == "news" else r"\d{4}(?:-\d{2}(?:-\d{2})?)?"
            if not re.fullmatch(pattern, str(row.get("date", ""))):
                raise ValueError("日期格式应为 YYYY-MM-DD；历史相册可只填年份或年月")
            key = row.get("id")
            if not isinstance(key, int if name == "news" else str) or (name == "gallery" and not re.fullmatch(r"[A-Za-z0-9_-]+", key)) or key in seen:
                raise ValueError("编号重复或格式错误")
            seen.add(key)
            if not isinstance(row.get("images", []), list):
                raise ValueError("图片列表格式错误")
            if any(key not in media for key in row.get("images", [])) or (row.get("cover") and row["cover"] not in row["images"]):
                raise ValueError("封面或图片不存在，请重新选择")
            if name == "gallery" and (not row["images"] or not row.get("cover")):
                raise ValueError("每个相册至少需要一张图片，并设置封面")
            if name == "news" and (row.get("category") not in ("news", "media") or not isinstance(row.get("body"), list) or any(not isinstance(p, str) for p in row["body"])):
                raise ValueError("文章分类或正文格式错误")
            if name == "news":
                if row.get("tag") and row["tag"] not in ("tour", "national", "policy", "mentor"):
                    raise ValueError("活动分类仅支持 tour、national、policy、mentor")
                for link in row.get("links", []):
                    if not isinstance(link, dict) or not re.match(r"^https?://", str(link.get("url", "")), re.I):
                        raise ValueError("相关文章链接必须使用 http 或 https")
    elif name in ("tici", "hexin"):
        if any(not isinstance(row, dict) or not row.get("file") for row in value):
            raise ValueError("题词贺信需要图片")
        media = json.loads((ROOT / "assets" / "image-variants.json").read_text())
        if any(row["file"] not in media for row in value):
            raise ValueError("题词贺信图片不存在")
    elif name == "site":
        tokens = set(re.findall(r"\{\{SITE_([A-Z0-9_]+)\}\}", (ROOT / "src" / "index.template.html").read_text()))
        if any(key.lower() not in value or not isinstance(value[key.lower()], str) for key in tokens):
            raise ValueError("页面文字缺少必填内容")
        if any(not isinstance(v, (str, list, dict, int)) for v in value.values()):
            raise ValueError("页面文字格式错误")
        patterns = {
            "home_banner_article": r"\d+",
            "stats_years": r"\d+", "stats_members": r"\d+", "stats_brands": r"\d+", "stats_committees": r"\d+",
            "contact_phone_digits": r"\+?\d+", "contact_whatsapp_digits": r"\d+",
            "contact_email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "contact_wechat": r"[A-Za-z0-9_-]+",
        }
        if any(not re.fullmatch(pattern, str(value.get(key, ""))) for key, pattern in patterns.items()):
            raise ValueError("横幅文章编号、统计数字或联系方式格式不正确")
        if not isinstance(value.get("brands"), dict) or set(value["brands"]) != {"tour", "national", "policy", "mentor"}:
            raise ValueError("四大品牌活动缺少栏目")
        if any(not isinstance(b, dict) or any(not isinstance(b.get(k), str) for k in ("n", "name", "tag", "cls", "desc", "long")) for b in value["brands"].values()):
            raise ValueError("品牌活动内容格式错误")
        if not isinstance(value.get("sails"), list) or len(value["sails"]) != 5 or any(not isinstance(s, list) or len(s) != 2 or any(not isinstance(x, str) for x in s) for s in value["sails"]):
            raise ValueError("五帆精神应保留五组标题和说明")
    elif name == "structure":
        if any(k not in value for k in ("exec", "committees", "honor", "fund", "past")):
            raise ValueError("本会架构缺少栏目")

        for key, rows in value.items():
            if key not in ("exec", "committees", "honor", "fund", "past"): continue
            if not isinstance(rows, list): raise ValueError("架构栏目必须是名单列表")
            required = ("name", "chair") if key == "committees" else ("term", "name") if key == "past" else ("title",)
            for row in rows:
                if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in required):
                    raise ValueError("请填写架构条目的名称和职务")
                if key in ("exec", "honor", "fund") and (not isinstance(row.get("names"), list) or any(not isinstance(n, str) or not n.strip() for n in row["names"])):
                    raise ValueError("名单请每行填写一位姓名")
