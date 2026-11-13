# Lowprice Bot (최저가 모니터링 및 카카오톡 알림 봇)

네이버 쇼핑에서 특정 상품("두유 96팩")의 최저가를 실시간 검색 및 모니터링하여, 목표가(30,000원) 이하의 특가가 감지되었을 때 카카오톡 "나에게 보내기"로 즉시 알림을 전송하는 봇입니다.

## 🚀 주요 기능

1. **네이버 쇼핑 실시간 최저가 검색**
   - 네이버 Open API 및 공개 엔드포인트를 통한 실시간 가격 조회
   - 광고(Ad) 상품 자동 필터링 및 순수 상품 기준 최저가 추출
2. **목표 가격 도달 판정**
   - 1위 상품 가격이 목표가(30,000원 이하)에 도달했는지 확인
   - 목표가 이하일 때: `[특가 발견]` 메시지와 함께 카카오톡 알림 전송
   - 목표가 초과일 때: 콘솔에 `[유지]` 메시지 출력 (알림 미발송)
3. **카카오톡 '나에게 보내기' 메시지 알림**
   - 상품명, 가격, 쇼핑몰명, 리뷰 수 포함
   - '구매하러 가기' 원클릭 링크 버튼 제공
   - 리프레시 토큰(Refresh Token)을 사용한 자동 액세스 토큰 갱신
   - 실패 시 실패 사유 명확한 오류 리포트
4. **검증 테스트 하네스 (`test_harness.py`)**
   - 가상 데이터를 통한 4대 핵심 로직 완전 검증 (특가 알림, 유지 판정, 광고 필터링, 예외 처리)

## 📁 파일 구조

```
├── lowprice_bot.py           # 메인 최저가 모니터링 및 카카오톡 알림 봇
├── issue_kakao_token.py      # 카카오 OAuth2 토큰 발급 및 .env 갱신 도구
├── test_harness.py           # 가상 데이터 기반 4대 로직 단위 테스트
├── test_kakao_notification.py # 카카오톡 메시지 전송 로직 검증 테스트
├── .env.example              # 환경 변수 예시 템플릿
└── .gitignore                # Git 제외 파일 목록 (.env 등 민감 정보 보호)
```

## ⚙️ 설정 방법

1. `.env.example`을 복사하여 `.env` 파일을 생성합니다:
   ```bash
   cp .env.example .env
   ```
2. `.env` 파일에 카카오 Developers 앱의 REST API 키와 Client Secret을 입력합니다:
   ```env
   KAKAO_REST_API_KEY=your_rest_api_key
   KAKAO_CLIENT_SECRET=your_client_secret
   ```
3. 카카오 인가 코드를 발급받아 토큰을 갱신합니다:
   ```bash
   python issue_kakao_token.py
   ```

## 🧪 테스트 실행

```bash
python test_harness.py
python test_kakao_notification.py
```

## 🏃 봇 실행

```bash
python lowprice_bot.py
```
