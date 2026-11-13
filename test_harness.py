#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_harness.py

lowprice_bot.py 파일의 핵심 동작 4가지를 가상(Mock) 데이터를 사용하여 엄격하게 검증하는 테스트 하네스.

[검사 항목]
1. 30000원 이하 일 때 특가 메시지가 출력되는가?
2. 30000원 초과 일 때 유지 메시지가 출력되는가?
3. 광고 상품이 섞여 있을 때 걸러낼 수 있는가?
4. 값을 가져오지 못했을 경우 멈추지 않고 오류를 알려주는가?

[검사 원칙]
- 실제 네이버 서버에 요청하지 않고 100% 가상 데이터(Mock)만 사용
- 검사 항목을 임의로 삭제하거나 느슨하게 완화하지 않음
- 각 항목별 PASS / FAIL 상태를 명확히 출력
- 모든 테스트가 통과할 때까지 점검
"""

import sys
import os
import io
import re
from unittest.mock import patch, MagicMock

# lowprice_bot 모듈 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowprice_bot


class MockHTTPResponse:
    """urllib.request.urlopen의 가상 응답 객체"""
    def __init__(self, data_bytes: bytes, status_code: int = 200):
        self.data_bytes = data_bytes
        self.status = status_code

    def read(self):
        return self.data_bytes

    def decode(self, encoding="utf-8", errors="replace"):
        return self.data_bytes.decode(encoding, errors=errors)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def make_mock_html(items: list) -> bytes:
    """
    items 리스트를 받아 네이버 쇼핑 포털 HTML 구조를 가상으로 생성합니다.
    item 딕셔너리 구성:
      - slog: data-slog-content 값 (광고: 'shp_gui:nad-xxx', 일반: 'shp_gui:00000009_xxx')
      - title: 상품명
      - price: 가격 (숫자)
      - mall: 쇼핑몰명
      - review: 리뷰 수
      - link: 링크
      - is_ad_flag: 추가 광고 표시 여부
    """
    html_parts = [
        '<!DOCTYPE html><html><body>',
        '<div class="api_subject_bx">',
        '<ul>'
    ]

    for item in items:
        slog = item.get("slog", "shp_gui:00000009_default")
        title = item.get("title", "테스트 두유 96팩")
        price = item.get("price", 30000)
        mall = item.get("mall", "테스트몰")
        review = item.get("review", 100)
        link = item.get("link", "https://smartstore.naver.com/test")
        extra_ad = '<span class="blind">광고</span>' if item.get("is_ad_flag") else ''

        li = f'''
        <li class="K70iQ12A" data-slog-content="{slog}">
            {extra_ad}
            <div class="KKrqaeRx"><img alt="{title}" src="http://img.jpg" /></div>
            <div class="WZhDZY7M">
                <a href="{link}" class="GBrjh9Fl hGyO4Mqh"><span>{title}</span></a>
                <div class="cpAdW9Tj">
                    <span class="lfETsaia">{price:,}</span><span class="TVuGseeW">원</span>
                </div>
                <div class="IHUXQSZ1">
                    <span class="jya46iRF">({review:,})</span>
                </div>
                <div class="Yx2Iv1IM">
                    <span class="Hejy2JWA">{mall}</span>
                </div>
            </div>
        </li>
        '''
        html_parts.append(li)

    html_parts.append('</ul></div></body></html>')
    return "\n".join(html_parts).encode("utf-8")


def run_bot_capture_output():
    """lowprice_bot.main()을 실행하고 stdout, stderr와 종료코드를 캡처합니다."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_buf
    sys.stderr = stderr_buf

    try:
        lowprice_bot.main()
    except SystemExit as se:
        exit_code = se.code if se.code is not None else 0
    except Exception as e:
        stderr_buf.write(f"\n[미처리 예외 발생]: {type(e).__name__}: {e}\n")
        exit_code = 99
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code


def test_1_under_30000_special_price():
    """
    [검사 1] 30,000원 이하 일 때 특가 메시지가 출력되는가?
    - 1위 가격이 27,000원(<= 30,000원)인 가상 데이터 제공
    - "[특가 발견]목표 가격 이하입니다!" 메시지가 출력되어야 함.
    """
    mock_items = [
        {"slog": "shp_gui:00000009_item1", "title": "연세 고칼슘 두유 96팩", "price": 27000, "mall": "연세몰", "review": 500},
        {"slog": "shp_gui:00000009_item2", "title": "삼육 검은콩 두유 96팩", "price": 31000, "mall": "삼육몰", "review": 300},
        {"slog": "shp_gui:00000009_item3", "title": "매일 담백한 두유 96팩", "price": 35000, "mall": "매일몰", "review": 200},
    ]
    mock_html = make_mock_html(mock_items)

    env_clean = {k: v for k, v in os.environ.items() if not k.startswith("NAVER_")}
    with patch.dict(os.environ, env_clean, clear=True):
        with patch("urllib.request.urlopen", return_value=MockHTTPResponse(mock_html)):
            stdout, stderr, code = run_bot_capture_output()

    expected_msg = "[특가 발견]목표 가격 이하입니다!"
    if expected_msg in stdout and code == 0:
        return True, f"특가 메시지 정상 출력 확인 (1위 가격: 27,000원)"
    else:
        reason = f"특가 메시지 미출력 또는 비정상 종료 (code: {code})\n출력내용: {stdout}"
        return False, reason


def test_2_over_30000_keep_price():
    """
    [검사 2] 30,000원 초과 일 때 유지 메시지가 출력되는가?
    - 1위 가격이 33,900원(> 30,000원)인 가상 데이터 제공
    - "[유지] 아직 목표 가격보다 비싸요!" 메시지가 출력되어야 함.
    """
    mock_items = [
        {"slog": "shp_gui:00000009_item1", "title": "연세 고칼슘 두유 96팩", "price": 33900, "mall": "연세몰", "review": 500},
        {"slog": "shp_gui:00000009_item2", "title": "삼육 검은콩 두유 96팩", "price": 42000, "mall": "삼육몰", "review": 300},
        {"slog": "shp_gui:00000009_item3", "title": "매일 아몬드 두유 96팩", "price": 54000, "mall": "매일몰", "review": 200},
    ]
    mock_html = make_mock_html(mock_items)

    env_clean = {k: v for k, v in os.environ.items() if not k.startswith("NAVER_")}
    with patch.dict(os.environ, env_clean, clear=True):
        with patch("urllib.request.urlopen", return_value=MockHTTPResponse(mock_html)):
            stdout, stderr, code = run_bot_capture_output()

    expected_msg = "[유지] 아직 목표 가격보다 비싸요!"
    if expected_msg in stdout and code == 0:
        return True, f"유지 메시지 정상 출력 확인 (1위 가격: 33,900원)"
    else:
        reason = f"유지 메시지 미출력 또는 비정상 종료 (code: {code})\n출력내용: {stdout}"
        return False, reason


def test_3_filter_ads_properly():
    """
    [검사 3] 광고 상품이 섞여 있을 때 걸러낼 수 있는가?
    - 가격이 더 저렴한 가짜 광고 상품(nad-, pmax-, ader 등) 3개와
      진짜 일반 상품 3개를 혼합한 가상 데이터 제공
    - 광고 상품(15,000원, 18,000원 등)은 반드시 걸러지고,
      진짜 상품 중 최저가인 32,000원이 1위로 출력되어야 함.
    """
    mixed_items = [
        # 광고 상품 1: 가격이 매우 낮음 (15,000원), nad- 광고 슬롯
        {"slog": "shp_gui:nad-a001-02-999999", "title": "[광고] 낚시 특가 두유 96팩", "price": 15000, "mall": "광고몰", "is_ad_flag": True},
        # 광고 상품 2: pmax 광고 슬롯 (18,000원)
        {"slog": "shp_gui:pmax-8888888", "title": "[스폰서] 초저가 두유 96팩", "price": 18000, "mall": "스폰서몰"},
        # 광고 상품 3: ader.naver.com 광고 링크 (20,000원)
        {"slog": "shp_gui:00000009_adlink", "title": "배너 프로모션 두유 96팩", "price": 20000, "link": "https://ader.naver.com/v1/click?ad=123"},

        # 진짜 상품 1: 32,000원 (광고 제거 시 진짜 1위여야 함)
        {"slog": "shp_gui:00000009_real1", "title": "진짜 정품 검은콩 두유 96팩", "price": 32000, "mall": "정품몰", "review": 880},
        # 진짜 상품 2: 36,000원
        {"slog": "shp_gui:00000009_real2", "title": "정품 고소한 두유 96팩", "price": 36000, "mall": "신선몰", "review": 420},
        # 진짜 상품 3: 41,000원
        {"slog": "shp_gui:00000009_real3", "title": "정품 호두아몬드 두유 96팩", "price": 41000, "mall": "건강몰", "review": 150},
    ]
    mock_html = make_mock_html(mixed_items)

    env_clean = {k: v for k, v in os.environ.items() if not k.startswith("NAVER_")}
    with patch.dict(os.environ, env_clean, clear=True):
        with patch("urllib.request.urlopen", return_value=MockHTTPResponse(mock_html)):
            stdout, stderr, code = run_bot_capture_output()

    # 검증 1: 광고 문구나 광고 상품명이 출력에 포함되지 않아야 함
    has_ad_1 = "[광고] 낚시 특가 두유 96팩" in stdout or "15,000원" in stdout
    has_ad_2 = "[스폰서] 초저가 두유 96팩" in stdout or "18,000원" in stdout
    has_ad_3 = "배너 프로모션 두유 96팩" in stdout or "20,000원" in stdout

    # 검증 2: 진짜 상품 중 최저가인 32,000원이 1위로 출력되어야 함
    has_real_rank1 = "[1위] 진짜 정품 검은콩 두유 96팩" in stdout and "32,000원" in stdout

    if not (has_ad_1 or has_ad_2 or has_ad_3) and has_real_rank1:
        return True, "광고 상품(3건) 완벽 제거 및 진짜 상품(32,000원) 1위 선정 확인"
    else:
        reasons = []
        if has_ad_1 or has_ad_2 or has_ad_3:
            reasons.append("광고 상품이 필터링되지 않고 출력에 포함됨")
        if not has_real_rank1:
            reasons.append("진짜 상품 1위(32,000원)가 정상 선정되지 않음")
        return False, "; ".join(reasons)


def test_4_handle_failure_without_crash():
    """
    [검사 4] 값을 가져오지 못했을 경우 멈추지 않고 오류를 알려주는가?
    - 4-1: 네트워크 연결 실패 예외 발생 시뮬레이션
    - 4-2: 응답 결과가 비어있거나 올바르지 않은 경우 시뮬레이션
    두 경우 모두 시스템이 크래시(비정상 트레이스백)하거나 묵묵부답으로 멈추지 않고,
    '[오류 발생]' 문구와 함께 원인을 안내하고 정상적으로 에러 처리(종료코드 1)를 수행하는가?
    """
    env_clean = {k: v for k, v in os.environ.items() if not k.startswith("NAVER_")}

    # Case 4-1: 네트워크 예외 발생 시
    with patch.dict(os.environ, env_clean, clear=True):
        with patch("urllib.request.urlopen", side_effect=Exception("Connection timed out (시뮬레이션)")):
            stdout_1, stderr_1, code_1 = run_bot_capture_output()

    # Case 4-2: 응답이 비어있을 때 (빈 HTML)
    empty_html = "<html><body><div>검색 결과 없음</div></body></html>".encode("utf-8")
    with patch.dict(os.environ, env_clean, clear=True):
        with patch("urllib.request.urlopen", return_value=MockHTTPResponse(empty_html)):
            stdout_2, stderr_2, code_2 = run_bot_capture_output()

    combined_1 = stdout_1 + stderr_1
    combined_2 = stdout_2 + stderr_2

    has_err_notice_1 = "[오류 발생]" in combined_1 and "Connection timed out" in combined_1
    has_err_notice_2 = "[오류 발생]" in combined_2
    exited_safely = (code_1 == 1 and code_2 == 1)

    if has_err_notice_1 and has_err_notice_2 and exited_safely:
        return True, "네트워크 단절 및 빈 데이터 상황에서 안내 메시지 출력 및 안전 종료(code 1) 확인"
    else:
        reasons = []
        if not has_err_notice_1:
            reasons.append(f"네트워크 오류 시 오류 안내 미흡 (출력: {combined_1})")
        if not has_err_notice_2:
            reasons.append(f"빈 데이터 수신 시 오류 안내 미흡 (출력: {combined_2})")
        if not exited_safely:
            reasons.append(f"종료 코드가 1이 아님 (case1: {code_1}, case2: {code_2})")
        return False, "; ".join(reasons)


def main():
    print("==================================================")
    print("🧪 lowprice_bot.py 테스트 하네스 검사 시작")
    print("   (가상 데이터 기반 독립 단위 검증)")
    print("==================================================")

    tests = [
        ("1. 30,000원 이하 일 때 특가 메시지 출력 검증", test_1_under_30000_special_price),
        ("2. 30,000원 초과 일 때 유지 메시지 출력 검증", test_2_over_30000_keep_price),
        ("3. 광고 상품 필터링 (진짜 상품만 선별) 검증", test_3_filter_ads_properly),
        ("4. 데이터 조회 실패 시 오류 안내 및 안전 처리 검증", test_4_handle_failure_without_crash),
    ]

    all_passed = True
    results = []

    for name, test_fn in tests:
        try:
            passed, detail = test_fn()
        except Exception as e:
            passed = False
            detail = f"테스트 실행 중 예기치 못한 에러: {e}"

        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        results.append((name, status_str, detail))

    print("\n[검사 결과 목록]")
    print("--------------------------------------------------")
    for name, status, detail in results:
        icon = "✅" if status == "PASS" else "❌"
        print(f"{icon} [{status}] {name}")
        print(f"    └ 상세: {detail}")
    print("--------------------------------------------------")

    if all_passed:
        print("\n🎉 축하합니다! 모든 검사 항목(4/4)이 PASS 되었습니다.")
        print("==================================================")
        sys.exit(0)
    else:
        print("\n⚠️ 일부 검사 항목이 FAIL 되었습니다.")
        print("==================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()
