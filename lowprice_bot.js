/**
 * lowprice_bot.js
 * 
 * [기능]
 * 1. 네이버 쇼핑 검색 스킬을 사용하여 "두유 96팩" 상품을 최저가 순으로 검색합니다.
 * 2. 반환된 광고(Ad) 상품을 식별하여 제거하고, 진짜(Organic) 상품만 필터링합니다.
 * 3. 최저가 순서로 상위 3개 상품의 상품명, 가격, 쇼핑몰, 리뷰수, 링크를 출력합니다.
 * 4. 1위 상품의 가격이 목표가(30,000원) 이하인지 검사하여 판정합니다:
 *    - 목표가 이하일 때: "[특가 발견]목표 가격 이하입니다!" 출력 후 카카오톡 '나에게 보내기' 알림 전송
 *    - 목표가 초과일 때: " [유지] 아직 목표 가격보다 비싸요!" 화면에만 출력 (메시지 미전송)
 * 5. 카카오톡 알림 전송:
 *    - .env 파일에서 인증 정보를 읽어와 처리 (하드코딩 금지)
 *    - 상품명, 가격, 쇼핑몰명, 리뷰수, '구매하러 가기' 버튼 링크 포함
 *    - 실패 시 보낸 척하지 않고 오류 내용 있는 그대로 출력
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ENV_PATH = path.join(__dirname, ".env");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
const TARGET_QUERY = "두유 96팩";
const TARGET_PRICE = 30000;

function loadEnv(filePath = ENV_PATH) {
  const env = {};
  if (!fs.existsSync(filePath)) return env;
  const content = fs.readFileSync(filePath, "utf-8");
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx !== -1) {
      const k = trimmed.slice(0, idx).trim();
      const v = trimmed.slice(idx + 1).trim();
      env[k] = v;
    }
  }
  return env;
}

function updateEnv(filePath, newVars) {
  let lines = [];
  const updatedKeys = new Set();
  if (fs.existsSync(filePath)) {
    lines = fs.readFileSync(filePath, "utf-8").split("\n");
    lines = lines.map(line => {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith("#") && trimmed.includes("=")) {
        const k = trimmed.split("=")[0].trim();
        if (newVars[k] !== undefined) {
          updatedKeys.add(k);
          return `${k}=${newVars[k]}`;
        }
      }
      return line;
    });
  }
  for (const [k, v] of Object.entries(newVars)) {
    if (!updatedKeys.has(k)) {
      lines.push(`${k}=${v}`);
    }
  }
  fs.writeFileSync(filePath, lines.filter(Boolean).join("\n") + "\n", "utf-8");
}

async function refreshKakaoToken(envData) {
  const refreshToken = envData.KAKAO_REFRESH_TOKEN;
  const clientId = envData.KAKAO_REST_API_KEY;
  const clientSecret = envData.KAKAO_CLIENT_SECRET;
  if (!refreshToken || !clientId) return null;

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: clientId,
    refresh_token: refreshToken,
  });
  if (clientSecret) body.append("client_secret", clientSecret);

  try {
    const res = await fetch("https://kauth.kakao.com/oauth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
      body: body.toString(),
    });
    if (!res.ok) return null;
    const tokens = await res.json();
    if (tokens.access_token) {
      const toUpdate = { KAKAO_ACCESS_TOKEN: tokens.access_token };
      if (tokens.refresh_token) toUpdate.KAKAO_REFRESH_TOKEN = tokens.refresh_token;
      updateEnv(ENV_PATH, toUpdate);
      Object.assign(envData, toUpdate);
      return tokens.access_token;
    }
  } catch {
    return null;
  }
  return null;
}

async function sendKakaoMemo(item) {
  const envData = loadEnv(ENV_PATH);
  let accessToken = envData.KAKAO_ACCESS_TOKEN;

  if (!accessToken && envData.KAKAO_REFRESH_TOKEN) {
    accessToken = await refreshKakaoToken(envData);
  }

  if (!accessToken) {
    console.error("\n❌ [카카오톡 알림 실패] 전송할 수 없습니다.");
    console.error("  원인: .env 파일에 유효한 카카오 인증 토큰(KAKAO_ACCESS_TOKEN 또는 KAKAO_REFRESH_TOKEN)이 존재하지 않습니다.");
    console.error("  참고: 토큰 발급 후 .env 파일에 등록해 주셔야 메시지 전송이 가능합니다.");
    return false;
  }

  const template = {
    object_type: "text",
    text: `🎉 [특가 발견] 두유 96팩 목표가 이하 달성!\n\n• 상품명: ${item.title}\n• 가격: ${item.priceText}\n• 쇼핑몰: ${item.mall}\n• 리뷰수: ${item.reviewCount.toLocaleString()}개`,
    link: {
      web_url: item.link,
      mobile_web_url: item.link,
    },
    button_title: "구매하러 가기",
  };

  const body = new URLSearchParams({
    template_object: JSON.stringify(template),
  });

  const sendReq = async (token) => {
    return await fetch("https://kapi.kakao.com/v2/api/talk/memo/default/send", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
      },
      body: body.toString(),
    });
  };

  try {
    let res = await sendReq(accessToken);
    if (res.status === 401 && envData.KAKAO_REFRESH_TOKEN) {
      const newToken = await refreshKakaoToken(envData);
      if (newToken) res = await sendReq(newToken);
    }

    if (res.ok) {
      const result = await res.json();
      if (result.result_code === 0) {
        console.log("\n📲 [카카오톡 알림 성공] 1위 특가 상품 정보가 카카오톡 '나에게 보내기'로 성공적으로 전송되었습니다!");
        return true;
      }
    }
    const errText = await res.text();
    console.error(`\n❌ [카카오톡 알림 실패] 카카오 API 응답 오류 (HTTP ${res.status}): ${errText}`);
    return false;
  } catch (err) {
    console.error(`\n❌ [카카오톡 알림 실패] 네트워크 오류: ${err.message}`);
    return false;
  }
}

function cleanText(s) {
  if (!s) return "";
  return s.replace(/<[^>]+>/g, " ").replace(/&[a-zA-Z0-9#]+;/g, " ").replace(/\s+/g, " ").trim();
}

function parseIntSafe(s) {
  if (!s) return null;
  const digits = String(s).replace(/\D/g, "");
  return digits ? parseInt(digits, 10) : null;
}

async function searchNaverShopping(query) {
  const envData = loadEnv(ENV_PATH);
  const clientId = process.env.NAVER_CLIENT_ID || envData.NAVER_CLIENT_ID || process.env.NAVER_SEARCH_CLIENT_ID;
  const clientSecret = process.env.NAVER_CLIENT_SECRET || envData.NAVER_CLIENT_SECRET || process.env.NAVER_SEARCH_CLIENT_SECRET;

  if (clientId && clientSecret) {
    console.log("[정보] 네이버 검색 Open API(최저가순)를 통해 조회합니다.\n");
    const url = `https://openapi.naver.com/v1/search/shop.json?query=${encodeURIComponent(query)}&sort=asc&display=50`;
    const res = await fetch(url, {
      headers: {
        "X-Naver-Client-Id": clientId,
        "X-Naver-Client-Secret": clientSecret,
      }
    });
    if (!res.ok) throw new Error(`네이버 Open API 요청 실패 (HTTP ${res.status})`);
    const data = await res.json();
    const valid = [];
    for (const it of (data.items || [])) {
      if (it.mallName?.includes("광고") || it.title?.includes("광고")) continue;
      const p = parseIntSafe(it.lprice);
      if (!p || p <= 0) continue;
      const title = cleanText(it.title);
      if (!title.includes("96")) continue;
      valid.push({
        title,
        price: p,
        priceText: `${p.toLocaleString()}원`,
        mall: cleanText(it.mallName) || "기타",
        reviewCount: parseIntSafe(it.reviewCount) || 0,
        link: it.link || "",
      });
    }
    return valid;
  }

  console.log("[정보] 네이버 쇼핑 공개 포털을 통해 실시간 조회합니다.\n");
  const url = `https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query=${encodeURIComponent(query)}`;
  const res = await fetch(url, {
    headers: {
      "User-Agent": UA,
      "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
      "Referer": "https://www.naver.com/",
    }
  });
  if (!res.ok) throw new Error(`네이버 쇼핑 포털 HTTP 에러 (상태코드: ${res.status})`);
  const html = await res.text();

  const itemMatches = [...html.matchAll(/<li[^>]+data-slog-content="([^"]+)"[^>]*>([\s\S]*?)<\/li>/gi)];
  if (!itemMatches.length) throw new Error("네이버 쇼핑 상품 리스트 파싱 실패");

  const organicItems = [];
  for (const m of itemMatches) {
    const slog = m[1];
    const block = m[2];
    if (slog.includes("nad-") || slog.includes("pmax-") || block.includes("ader.naver.com") || block.includes('class="blind">광고')) continue;

    const titleMatch = block.match(/<a[^>]+class="[^"]*hGyO4Mqh[^"]*"[^>]*><span>([\s\S]*?)<\/span>/i) ||
                       block.match(/alt="([^"]+)"/i);
    const title = cleanText(titleMatch?.[1]);
    if (!title || !title.includes("96")) continue;

    const priceMatches = [...block.matchAll(/<span class="lfETsaia">([\d,]+)<\/span>/gi)];
    let price = priceMatches.length ? parseIntSafe(priceMatches[priceMatches.length - 1][1]) : null;
    if (!price) {
      const alt = block.match(/<span class="price"><strong>([\d,]+)<\/strong>/i);
      price = alt ? parseIntSafe(alt[1]) : null;
    }
    if (!price || price <= 0) continue;

    const mallMatch = block.match(/<span class="Hejy2JWA">([\s\S]*?)<\/span>/i) ||
                      block.match(/<a[^>]+class="[^"]*K3t5KkCj[^"]*"[^>]*>([\s\S]*?)<\/a>/i);
    const mall = cleanText(mallMatch?.[1]) || "네이버 쇼핑몰";

    const reviewMatch = block.match(/<span class="jya46iRF">\([^\d]*([\d,]+)[^\d]*\)<\/span>/i) ||
                        block.match(/리뷰\s*<em[^>]*>([\d,]+)<\/em>/i);
    const reviewCount = reviewMatch ? (parseIntSafe(reviewMatch[1]) || 0) : 0;

    const linkMatch = block.match(/<a[^>]+href="([^"]+)"[^>]*class="[^"]*GBrjh9Fl/i) ||
                      block.match(/<a[^>]+class="[^"]*o_ELSfeN[^"]*"[^>]+href="([^"]+)"/i) ||
                      block.match(/<a[^>]+href="([^"]+)"/i);
    let link = linkMatch?.[1] || "";
    if (link.startsWith("//")) link = "https:" + link;
    link = link.replace(/&amp;/g, "&");

    organicItems.push({
      title,
      price,
      priceText: `${price.toLocaleString()}원`,
      mall,
      reviewCount,
      link,
    });
  }

  return organicItems;
}

async function main() {
  console.log("==================================================");
  console.log(`🤖 최저가 알리미 봇: "${TARGET_QUERY}" 검색 시작`);
  console.log("==================================================");

  try {
    const products = await searchNaverShopping(TARGET_QUERY);
    if (!products || !products.length) {
      console.error("[오류 발생] 광고를 제외한 실제 유효 상품을 찾을 수 없습니다.");
      process.exit(1);
    }

    products.sort((a, b) => a.price - b.price);
    const top3 = products.slice(0, 3);

    console.log(`\n📋 [최저가 TOP ${top3.length} 상품 목록]`);
    console.log("--------------------------------------------------");
    top3.forEach((item, index) => {
      console.log(`[${index + 1}위] ${item.title}`);
      console.log(`  - 가격    : ${item.priceText}`);
      console.log(`  - 쇼핑몰  : ${item.mall}`);
      console.log(`  - 리뷰수  : ${item.reviewCount.toLocaleString()}개`);
      console.log(`  - 링크    : ${item.link}`);
      console.log("--------------------------------------------------");
    });

    const rank1Item = top3[0];
    const rank1Price = rank1Item.price;
    console.log(`\n🎯 [목표가 판정 결과] (기준가: ${TARGET_PRICE.toLocaleString()}원 / 1위 실구매가: ${rank1Price.toLocaleString()}원)`);

    if (rank1Price <= TARGET_PRICE) {
      console.log("[특가 발견]목표 가격 이하입니다!");
      console.log("\n💬 [알림 트리거] 목표가 이하 특가 상품이 발견되어 카카오톡 '나에게 보내기'를 진행합니다...");
      await sendKakaoMemo(rank1Item);
    } else {
      console.log(" [유지] 아직 목표 가격보다 비싸요!");
      console.log("ℹ️ (목표 가격보다 비싸므로 카카오톡 알림을 전송하지 않고 화면에만 출력합니다.)");
    }
    console.log("==================================================\n");

  } catch (err) {
    console.error("\n❌ [오류 발생] 작업을 중단합니다.");
    console.error(`상세 내용: ${err.message}`);
    process.exit(1);
  }
}

main();
