#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
issue_kakao_token.py

카카오 OAuth 2.0 인가 코드(Authorization Code)를 사용하여 
액세스 토큰 및 리프레시 토큰(Refresh Token)을 발급받고,
발급된 토큰을 프로젝트의 .env 파일에 자동으로 저장/갱신하는 스크립트.
"""

import os
import sys
import json
import urllib.parse
import urllib.request

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
DEFAULT_REDIRECT_URI = "http://localhost"


def load_env(path: str = ENV_PATH) -> dict:
    env_vars = {}
    if not os.path.exists(path):
        return env_vars
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def update_env(path: str, new_vars: dict):
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


def issue_token(code: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> dict:
    env = load_env(ENV_PATH)
    client_id = env.get("KAKAO_REST_API_KEY")
    client_secret = env.get("KAKAO_CLIENT_SECRET")

    if not client_id:
        raise ValueError(".env 파일에서 KAKAO_REST_API_KEY를 찾을 수 없습니다.")

    # clean code if full url was passed
    if "code=" in code:
        code = code.split("code=")[1].split("&")[0]

    url = "https://kauth.kakao.com/oauth/token"
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            tokens = json.loads(resp_body)
            return tokens
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
            err_code = err_json.get("error_code")
            err_desc = err_json.get("error_description")
            raise RuntimeError(f"카카오 토큰 발급 실패 (HTTP {e.code}, {err_code}): {err_desc}")
        except json.JSONDecodeError:
            raise RuntimeError(f"카카오 토큰 발급 실패 (HTTP {e.code}): {err_body}")
    except Exception as e:
        raise RuntimeError(f"요청 중 네트워크 오류 발생: {e}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python issue_kakao_token.py <인가코드_또는_전체URL> [REDIRECT_URI]")
        print("예시  : python issue_kakao_token.py Xyp7TlbrMkuz...")
        sys.exit(1)

    raw_input = sys.argv[1]
    redirect_uri = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REDIRECT_URI

    # If full URL like http://localhost/?code=xxx was given, auto-extract
    if "code=" in raw_input:
        code = raw_input.split("code=")[1].split("&")[0]
    else:
        code = raw_input

    print("==================================================")
    print("🔑 카카오 리프레시 토큰 발급 진행 중...")
    print(f"  - 인가 코드   : {code[:10]}...{code[-5:]}")
    print(f"  - Redirect URI: {redirect_uri}")
    print("==================================================")

    try:
        tokens = issue_token(code, redirect_uri)
        refresh_token = tokens.get("refresh_token")
        access_token = tokens.get("access_token")

        if not refresh_token:
            print(f"[경고] 응답에 refresh_token이 없습니다: {tokens}")
            sys.exit(1)

        to_update = {
            "KAKAO_REFRESH_TOKEN": refresh_token,
            "KAKAO_REDIRECT_URI": redirect_uri,
        }
        if access_token:
            to_update["KAKAO_ACCESS_TOKEN"] = access_token

        update_env(ENV_PATH, to_update)

        print("\n✅ [발급 성공!] 리프레시 토큰이 .env 파일에 성공적으로 저장되었습니다!")
        print(f"  - KAKAO_REFRESH_TOKEN: {refresh_token[:10]}...{refresh_token[-5:]} (저장 완료)")
        if access_token:
            print(f"  - KAKAO_ACCESS_TOKEN : {access_token[:10]}...{access_token[-5:]} (저장 완료)")
        print("==================================================")

    except Exception as e:
        print(f"\n❌ [오류 발생] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
