#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lowprice_bot.py

[기능]
1. 네이버 쇼핑 검색 스킬을 사용하여 "두유 96팩" 상품을 최저가 순으로 검색합니다.
   - 네이버 Open API 키(NAVER_CLIENT_ID, NAVER_CLIENT_SECRET) 환경 변수가 있으면 공식 API 우선 사용
   - 키가 없을 경우 네이버 쇼핑 공개 포털의 검색 엔드포인트를 통해 실시간 조회
2. 반환된 광고(Ad) 상품을 식별하여 제거하고, 진짜(Organic) 상품만 필터링합니다.
3. 최저가 순서로 상위 3개 상품의 상품명, 가격, 쇼핑몰, 리뷰수, 링크를 보기 좋게 출력합니다.
4. 1위 상품의 가격이 목표가(30,000원) 이하인지 검사하여 판정 결과를 출력합니다:
   - 목표가 이하일 때: "[특가 발견]목표 가격 이하입니다!" 출력 후 카카오톡 '나에게 보내기' 알림 전송
   - 목표가 초과일 때: " [유지] 아직 목표 가격보다 비싸요!" 화면에만 출력 (메시지 전송 안 함)
5. 카카오톡 알림 전송:
   - .env 파일에서 인증 정보를 읽어와 처리 (코드 내 하드코딩 금지)
   - 액세스 토큰 만료 시 리프레시 토큰으로 자동 갱신
   - 상품명, 가격, 쇼핑몰명, 리뷰수 및 '구매하러 가기' 버튼 링크 포함
   - 알림 전송 실패 시 보낸 척하지 않고 오류 원인을 있는 그대로 출력
6. 잘못된 값을 가져오거나 오류 발생 시 절대 임의로 데이터를 지어내지 않고, 오류 원인을 그대로 출력한 뒤 즉시 종료합니다.
"""

import sys
import os
import re
import json
import urllib.parse
import urllib.request
from html import unescape

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
TARGET_QUERY = "두유 96팩"
TARGET_PRICE = 30000
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env(path: str = ENV_PATH) -> dict:
    """프로젝트 폴더의 .env 파일을 파싱하여 딕셔너리로 반환합니다."""
    env_vars = {}
    if not os.path.exists(path):
        return env_vars
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    except Exception as e:
        print(f"[경고] .env 파일 읽기 실패: {e}", file=sys.stderr)
    return env_vars


def update_env(path: str, new_vars: dict):
    """.env 파일에 새로운 키-값 쌍을 저장하거나 갱신합니다."""
    lines = []
    keys_updated = set()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, _ = stripped.split("=", 1)
                    k = k.strip()
                    if k in new_vars:
                        lines.append(f"{k}={new_vars[k]}\n")
                        keys_updated.add(k)
                        continue
                lines.append(line)

    for k, v in new_vars.items():
        if k not in keys_updated:
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(f"{k}={v}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def refresh_kakao_access_token(env_data: dict) -> str | None:
    """리프레시 토큰을 이용해 카카오 액세스 토큰을 재발급받고 .env를 갱신합니다."""
    refresh_token = env_data.get("KAKAO_REFRESH_TOKEN")
    client_id = env_data.get("KAKAO_REST_API_KEY")
    client_secret = env_data.get("KAKAO_CLIENT_SECRET")

    if not refresh_token:
        return None
    if not client_id:
        return None

    url = "https://kauth.kakao.com/oauth/token"
    params = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        params["client_secret"] = client_secret

    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
            new_access = tokens.get("access_token")
            new_refresh = tokens.get("refresh_token")
            if new_access:
                to_save = {"KAKAO_ACCESS_TOKEN": new_access}
                if new_refresh:
                    to_save["KAKAO_REFRESH_TOKEN"] = new_refresh
                update_env(ENV_PATH, to_save)
                env_data.update(to_save)
                return new_access
    except Exception as e:
        print(f"[카카오 토큰 갱신 실패] {e}", file=sys.stderr)
        return None
    return None


def send_kakao_memo(item: dict) -> bool:
    """
    카카오톡 '나에게 보내기' API를 통해 1위 특가 상품 알림을 전송합니다.
    - 실패 시 보낸 척하지 않고 원인을 있는 그대로 출력합니다.
    """
    env_data = load_env(ENV_PATH)
    access_token = env_data.get("KAKAO_ACCESS_TOKEN")

    # 1. 액세스 토큰이 없거나 만료 가능성이 있으면 리프레시 토큰으로 갱신 시도
    if not access_token:
        if env_data.get("KAKAO_REFRESH_TOKEN"):
            access_token = refresh_kakao_access_token(env_data)

    if not access_token:
        print("\n❌ [카카오톡 알림 실패] 전송할 수 없습니다.", file=sys.stderr)
        print("  원인: .env 파일에 유효한 카카오 인증 토큰(KAKAO_ACCESS_TOKEN 또는 KAKAO_REFRESH_TOKEN)이 존재하지 않습니다.", file=sys.stderr)
        print("  참고: 토큰 발급 후 .env 파일에 등록해 주셔야 메시지 전송이 가능합니다.", file=sys.stderr)
        return False

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    # 메시지 템플릿 구성 (텍스트 및 '구매하러 가기' 버튼)
    template = {
        "object_type": "text",
        "text": (
            f"🎉 [특가 발견] 두유 96팩 목표가 이하 달성!\n\n"
            f"• 상품명: {item['title']}\n"
            f"• 가격: {item['price_text']}\n"
            f"• 쇼핑몰: {item['mall']}\n"
            f"• 리뷰수: {item['review_count']:,}개"
        ),
        "link": {
            "web_url": item["link"],
            "mobile_web_url": item["link"],
        },
        "button_title": "구매하러 가기"
    }

    data = urllib.parse.urlencode({"template_object": json.dumps(template, ensure_ascii=False)}).encode("utf-8")

    def execute_send(token):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
            }
        )
        return urllib.request.urlopen(req, timeout=10)

    try:
        try:
            with execute_send(access_token) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                if resp_json.get("result_code") == 0:
                    print("\n📲 [카카오톡 알림 성공] 1위 특가 상품 정보가 카카오톡 '나에게 보내기'로 성공적으로 전송되었습니다!")
                    return True
                else:
                    print(f"\n❌ [카카오톡 알림 실패] 전송 결과 오류: {resp_json}", file=sys.stderr)
                    return False
        except urllib.error.HTTPError as he:
            # 401 Unauthorized인 경우 토큰 갱신 후 1회 재시도
            if he.code == 401 and env_data.get("KAKAO_REFRESH_TOKEN"):
                print("[정보] 카카오 액세스 토큰이 만료되어 리프레시 토큰으로 자동 갱신을 시도합니다...")
                new_token = refresh_kakao_access_token(env_data)
                if new_token:
                    with execute_send(new_token) as resp_retry:
                        resp_json = json.loads(resp_retry.read().decode("utf-8"))
                        if resp_json.get("result_code") == 0:
                            print("\n📲 [카카오톡 알림 성공] 토큰 자동 갱신 후 카카오톡 알림이 성공적으로 전송되었습니다!")
                            return True
            err_body = he.read().decode("utf-8", errors="replace")
            print(f"\n❌ [카카오톡 알림 실패] 카카오 API 응답 오류 (HTTP {he.code})", file=sys.stderr)
            print(f"  오류 내용: {err_body}", file=sys.stderr)
            return False

    except Exception as e:
        print(f"\n❌ [카카오톡 알림 실패] 전송 중 네트워크/시스템 오류 발생: {e}", file=sys.stderr)
        return False


def clean_text(s: str) -> str:
    if not s:
        return ""
    no_html = re.sub(r"<[^>]+>", " ", s)
    unescaped = unescape(no_html)
    return " ".join(unescaped.split())


def parse_int_safe(s) -> int | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", str(s))
    return int(digits) if digits else None


def search_naver_shopping(query: str):
    env_data = load_env(ENV_PATH)
    client_id = os.environ.get("NAVER_CLIENT_ID") or env_data.get("NAVER_CLIENT_ID") or os.environ.get("NAVER_SEARCH_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET") or env_data.get("NAVER_CLIENT_SECRET") or os.environ.get("NAVER_SEARCH_CLIENT_SECRET")

    # 1. 네이버 Open API 키가 있는 경우
    if client_id and client_secret:
        print("[정보] 네이버 검색 Open API(최저가순)를 통해 조회합니다.\n")
        url = f"https://openapi.naver.com/v1/search/shop.json?query={urllib.parse.quote(query)}&sort=asc&display=50"
        req = urllib.request.Request(
            url,
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "User-Agent": UA,
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"네이버 Open API 요청 실패: {e}")

        items = data.get("items")
        if not isinstance(items, list):
            raise RuntimeError("네이버 Open API 응답 구조가 유효하지 않습니다 (items 배열 누락).")

        valid_items = []
        for item in items:
            title_raw = item.get("title", "")
            mall_raw = item.get("mallName", "")
            # 광고 필터링
            if "광고" in mall_raw or "광고" in title_raw:
                continue

            price = parse_int_safe(item.get("lprice"))
            if not price or price <= 0:
                continue

            title = clean_text(title_raw)
            if "96" not in title:
                continue

            valid_items.append({
                "title": title,
                "price": price,
                "price_text": f"{price:,}원",
                "mall": clean_text(mall_raw) or "기타",
                "review_count": parse_int_safe(item.get("reviewCount")) or 0,
                "link": item.get("link", ""),
            })

        return valid_items

    # 2. 키가 없을 경우 네이버 쇼핑 공개 포털을 통해 실시간 조회 (BFF Fallback)
    print("[정보] 네이버 쇼핑 공개 포털을 통해 실시간 조회합니다.\n")
    url = f"https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": "https://www.naver.com/",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"네이버 쇼핑 포털 네트워크 연결 오류: {e}")

    if not html or len(html) < 500:
        raise RuntimeError("네이버 쇼핑 응답 데이터가 비어있거나 올바르지 않습니다.")

    # 상품 아이템 추출
    item_pattern = re.compile(r'<li[^>]+data-slog-content="([^"]+)"[^>]*>([\s\S]*?)</li>', re.IGNORECASE)
    matches = item_pattern.findall(html)
    if not matches:
        raise RuntimeError("네이버 쇼핑 상품 리스트를 파싱할 수 없습니다. (포털 구조 변경 또는 접근 제한)")

    organic_items = []
    for slog, block in matches:
        # [광고 필터링]: nad-, pmax-, ader.naver.com 등 광고 식별자 제외
        is_ad = ("nad-" in slog or "pmax-" in slog or
                 "ader.naver.com" in block or
                 'class="blind">광고' in block or
                 "ad_id" in block)
        if is_ad:
            continue

        # 상품명 추출
        title_m = (re.search(r'<a[^>]+class="[^"]*hGyO4Mqh[^"]*"[^>]*><span>([\s\S]*?)</span>', block, re.IGNORECASE) or
                   re.search(r'alt="([^"]+)"', block, re.IGNORECASE) or
                   re.search(r'<span class="[^"]*title[^"]*">([\s\S]*?)</span>', block, re.IGNORECASE))
        title = clean_text(title_m.group(1)) if title_m else ""
        if not title:
            continue

        # 가격 추출
        price_matches = re.findall(r'<span class="lfETsaia">([\d,]+)</span>', block, re.IGNORECASE)
        price = parse_int_safe(price_matches[-1]) if price_matches else None
        if not price:
            alt_price = re.search(r'<span class="price"><strong>([\d,]+)</strong>', block, re.IGNORECASE)
            price = parse_int_safe(alt_price.group(1)) if alt_price else None

        if not price or price <= 0:
            continue

        # 쇼핑몰명 추출
        mall_m = (re.search(r'<span class="Hejy2JWA">([\s\S]*?)</span>', block, re.IGNORECASE) or
                  re.search(r'<a[^>]+class="[^"]*K3t5KkCj[^"]*"[^>]*>([\s\S]*?)</a>', block, re.IGNORECASE) or
                  re.search(r'<span class="[^"]*mall[^"]*">([\s\S]*?)</span>', block, re.IGNORECASE))
        mall = clean_text(mall_m.group(1)) if mall_m else ""
        if not mall:
            mall = "네이버 스마트스토어" if "smartstore.naver.com" in block else "네이버 쇼핑몰"

        # 리뷰수 추출
        review_m = (re.search(r'<span class="jya46iRF">\([^\d]*([\d,]+)[^\d]*\)</span>', block, re.IGNORECASE) or
                    re.search(r'리뷰\s*<em[^>]*>([\d,]+)</em>', block, re.IGNORECASE) or
                    re.search(r'리뷰\s*([\d,]+)', block, re.IGNORECASE))
        review_count = parse_int_safe(review_m.group(1)) if review_m else 0

        # 링크 추출
        link_m = (re.search(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*GBrjh9Fl', block, re.IGNORECASE) or
                  re.search(r'<a[^>]+class="[^"]*o_ELSfeN[^"]*"[^>]+href="([^"]+)"', block, re.IGNORECASE) or
                  re.search(r'<a[^>]+href="([^"]+)"', block, re.IGNORECASE))
        link = link_m.group(1) if link_m else ""
        if link.startswith("//"):
            link = "https:" + link
        link = link.replace("&amp;", "&")

        # 96팩 규격 필터링
        if "96" not in title:
            continue

        organic_items.append({
            "title": title,
            "price": price,
            "price_text": f"{price:,}원",
            "mall": mall,
            "review_count": review_count,
            "link": link,
        })

    return organic_items


def main():
    print("==================================================")
    print(f'🤖 최저가 알리미 봇: "{TARGET_QUERY}" 검색 시작')
    print("==================================================")

    try:
        products = search_naver_shopping(TARGET_QUERY)

        # 유효성 검증
        if not products:
            print("[오류 발생] 광고를 제외한 실제 유효 상품을 찾을 수 없습니다.", file=sys.stderr)
            print("원인: 검색 결과 내에 '96팩' 규격의 일반 상품이 없거나 필터링되었습니다.", file=sys.stderr)
            sys.exit(1)

        # 최저가 순 정렬
        products.sort(key=lambda x: x["price"])
        top3 = products[:3]

        print(f"\n📋 [최저가 TOP {len(top3)} 상품 목록]")
        print("--------------------------------------------------")
        for i, item in enumerate(top3, start=1):
            print(f"[{i}위] {item['title']}")
            print(f"  - 가격    : {item['price_text']}")
            print(f"  - 쇼핑몰  : {item['mall']}")
            print(f"  - 리뷰수  : {item['review_count']:,}개")
            print(f"  - 링크    : {item['link']}")
            print("--------------------------------------------------")

        # 목표가 판정 및 조건부 카카오톡 알림 전송
        rank1_item = top3[0]
        rank1_price = rank1_item["price"]
        print(f"\n🎯 [목표가 판정 결과] (기준가: {TARGET_PRICE:,}원 / 1위 실구매가: {rank1_price:,}원)")

        if rank1_price <= TARGET_PRICE:
            print("[특가 발견]목표 가격 이하입니다!")
            # 1위 가격이 목표가 이하일 때만 카카오톡 전송
            print("\n💬 [알림 트리거] 목표가 이하 특가 상품이 발견되어 카카오톡 '나에게 보내기'를 진행합니다...")
            send_kakao_memo(rank1_item)
        else:
            print(" [유지] 아직 목표 가격보다 비싸요!")
            print("ℹ️ (목표 가격보다 비싸므로 카카오톡 알림을 전송하지 않고 화면에만 출력합니다.)")

        print("==================================================\n")

    except Exception as err:
        print("\n❌ [오류 발생] 정상적인 데이터를 가져오지 못하여 작업을 중단합니다.", file=sys.stderr)
        print(f"상세 내용: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
