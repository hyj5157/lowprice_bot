#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_kakao_notification.py

lowprice_bot.py의 카카오톡 '나에게 보내기' 알림 기능 검증 스크립트.
"""

import sys
import os
import json
import io
import urllib.parse
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowprice_bot

def test_kakao_requirements():
    print("==================================================")
    print("🧪 카카오톡 '나에게 보내기' 알림 기능 검증")
    print("==================================================")
    
    # 1. 메시지 포맷 및 버튼 링크 검증
    sample_item = {
        "title": "연세 뼈를 생각한 고칼슘 두유 180ml X 96팩",
        "price": 28000,
        "price_text": "28,000원",
        "mall": "프레쉬영스토어",
        "review_count": 1442,
        "link": "https://smartstore.naver.com/main/products/13591553049"
    }
    
    captured_payload = {}
    
    class MockSuccessResp:
        def read(self):
            return json.dumps({"result_code": 0}).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(req, timeout=10):
        body_str = req.data.decode("utf-8")
        parsed = urllib.parse.parse_qs(body_str)
        template_str = parsed.get("template_object", [""])[0]
        captured_payload["template"] = json.loads(template_str)
        captured_payload["headers"] = dict(req.headers)
        return MockSuccessResp()

    mock_env = {
        "KAKAO_REST_API_KEY": "test_rest_api_key",
        "KAKAO_ACCESS_TOKEN": "test_access_token",
    }
    
    with patch("lowprice_bot.load_env", return_value=mock_env):
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = lowprice_bot.send_kakao_memo(sample_item)
            
    tmpl = captured_payload.get("template", {})
    text = tmpl.get("text", "")
    
    req2_title = sample_item["title"] in text
    req2_price = sample_item["price_text"] in text
    req2_mall = sample_item["mall"] in text
    req2_review = "1,442개" in text
    req2_btn = tmpl.get("button_title") == "구매하러 가기"
    req2_link = tmpl.get("link", {}).get("web_url") == sample_item["link"]
    
    print("[검사 1] 메시지 필수 항목(상품명, 가격, 쇼핑몰, 리뷰수, '구매하러 가기' 버튼 링크):")
    if req2_title and req2_price and req2_mall and req2_review and req2_btn and req2_link:
        print("  -> ✅ PASS: 모든 항목 및 버튼 링크 정상 포함")
    else:
        print("  -> ❌ FAIL")

    # 2. 토큰 누락 또는 전송 실패 시 보낸 척하지 않고 오류를 알리는가?
    stderr_buf = io.StringIO()
    old_err = sys.stderr
    sys.stderr = stderr_buf
    try:
        empty_env = {"KAKAO_REST_API_KEY": "test_key"}
        with patch("lowprice_bot.load_env", return_value=empty_env):
            fail_res = lowprice_bot.send_kakao_memo(sample_item)
    finally:
        sys.stderr = old_err
        
    err_output = stderr_buf.getvalue()
    not_pretended = (fail_res is False) and ("[카카오톡 알림 실패]" in err_output)
    print("\n[검사 2] 전송 실패 시 보낸 척하지 않고 원인을 있는 그대로 알리는가:")
    if not_pretended:
        print("  -> ✅ PASS: 실패 반환(False) 및 원인 메시지 정상 출력")
    else:
        print("  -> ❌ FAIL")
        
    print("==================================================")

if __name__ == "__main__":
    test_kakao_requirements()
