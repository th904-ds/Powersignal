"""KPX / data.go.kr 응답 파서.

분류는 코드 번호가 아니라 '메시지 키워드' 우선으로 한다. data.go.kr 은
게이트웨이/제공기관에 따라 같은 숫자코드(예: 03)가 NODATA 이기도 하고 인증오류
이기도 해서, 숫자만 믿으면 인증오류를 빈데이터로 착각해 조용히 빈 파일을 만들 위험이
있다. 그래서:
  - 정상      : resultCode 00 또는 메시지에 NORMAL/정상
  - NODATA   : 메시지에 NODATA / 데이터가 없 → NoData (오류 아님, 빈 결과)
  - 그 외     : ApiError (인증키/트래픽/필수파라미터 누락 등 → 사용자에게 노출)
또한 data.go.kr 게이트웨이 인증오류는 dataType=json 이어도 XML 봉투
(<OpenAPI_ServiceResponse>...<returnAuthMsg>)로 오므로 그것도 잡는다.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

_OK_CODES = {"00", "0", "INFO-0", "INFO-00", "INFO-000"}
_NODATA_HINTS = ("NODATA", "NO_DATA", "NO DATA", "데이터가 없", "데이터없음")


class ApiError(RuntimeError):
    """인증키/트래픽/필수파라미터 누락 등. 빈데이터 아님."""


class NoData(Exception):
    """정상 응답이지만 데이터 0건. 오류 아님."""


def parse(text: str) -> tuple[list[dict], int]:
    body = text.strip()
    if not body:
        raise ApiError("빈 응답")
    if body[0] in "{[":
        return _parse_json(body)
    if body[0] == "<":
        return _parse_xml(body)
    raise ApiError(f"알 수 없는 응답 형식: {body[:120]!r}")


def parse_odcloud(text: str) -> tuple[list[dict], int]:
    """odcloud(api.odcloud.kr): {totalCount, data:[...]} 구조."""
    body = text.strip()
    if body and body[0] == "<":
        raise ApiError(f"odcloud XML 오류 응답: {body[:120]!r}")
    obj = json.loads(body)
    if "data" not in obj:
        raise ApiError(f"odcloud 오류 응답: {obj}")
    return [r for r in (obj.get("data") or []) if isinstance(r, dict)], _to_int(
        obj.get("totalCount"), -1)


# --------------------------------------------------------------- 분류
def _classify(code: str, msg: str) -> str:
    code = (code or "").strip()
    u = (msg or "").upper()
    if code in _OK_CODES or "NORMAL" in u or "정상" in (msg or ""):
        return "ok"
    if any(h in u or h in (msg or "") for h in _NODATA_HINTS):
        return "nodata"
    return "error"


def _handle(code: str, msg: str):
    kind = _classify(code, msg)
    if kind == "nodata":
        raise NoData()
    if kind == "error":
        raise ApiError(f"resultCode={code!r} msg={msg!r}")


# --------------------------------------------------------------- JSON
def _parse_json(body: str) -> tuple[list[dict], int]:
    obj = json.loads(body)
    resp = obj.get("response", obj)
    header = _dig(resp, "header") or {}
    _handle(str(header.get("resultCode", "")), str(header.get("resultMsg", "")))

    b = _dig(resp, "body") or resp
    total = _to_int(b.get("totalCount"), -1)
    items = _dig(b, "items")
    if isinstance(items, dict):
        items = items.get("item")
    if items is None:
        items = b.get("item")
    return [r for r in _as_list(items) if isinstance(r, dict)], total


# ---------------------------------------------------------------- XML
def _parse_xml(body: str) -> tuple[list[dict], int]:
    root = ET.fromstring(body)

    # data.go.kr 게이트웨이 인증/시스템 오류 봉투
    auth_msg = _xml_text(root, ".//returnAuthMsg") or _xml_text(root, ".//errMsg")
    if auth_msg:
        reason = _xml_text(root, ".//returnReasonCode") or ""
        raise ApiError(f"게이트웨이 오류 reasonCode={reason} msg={auth_msg!r}")

    _handle(_xml_text(root, ".//resultCode") or "",
            _xml_text(root, ".//resultMsg") or "")

    total = _to_int(_xml_text(root, ".//totalCount"), -1)
    items = root.findall(".//item")
    if not items:
        body_el = root.find(".//body")
        if body_el is not None:
            items = [c for c in body_el if len(list(c))]
    rows = [{child.tag: (child.text or "").strip() for child in it} for it in items]
    return rows, total


# ------------------------------------------------------------- helpers
def _dig(d, key):
    return d.get(key) if isinstance(d, dict) else None


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _to_int(v, default):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _xml_text(root, path):
    el = root.find(path)
    return el.text if el is not None else None
