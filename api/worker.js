const ETSY_API = "https://api.etsy.com/v3/application/listings/active";
const ALLOWED_ORIGINS = new Set([
  "https://hang458.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);

function json(data, status, origin) {
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "public, max-age=120",
    "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "content-type",
    "vary": "Origin",
  };
  if (origin && ALLOWED_ORIGINS.has(origin)) headers["access-control-allow-origin"] = origin;
  return new Response(JSON.stringify(data), { status, headers });
}

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") return json({}, 200, origin);
    if (request.method !== "GET") return json({ error: "仅支持 GET 搜索请求" }, 405, origin);
    if (origin && !ALLOWED_ORIGINS.has(origin)) return json({ error: "请求来源未获允许" }, 403, origin);
    if (!env.ETSY_KEYSTRING || !env.ETSY_SHARED_SECRET) {
      return json({ error: "搜索代理尚未配置 Etsy API 凭证" }, 503, origin);
    }

    const incoming = new URL(request.url);
    const keyword = (incoming.searchParams.get("q") || "").trim();
    const limit = Math.min(100, Math.max(1, Number.parseInt(incoming.searchParams.get("limit") || "50", 10) || 50));
    const offset = Math.min(5000, Math.max(0, Number.parseInt(incoming.searchParams.get("offset") || "0", 10) || 0));
    if (keyword.length < 2 || keyword.length > 100) {
      return json({ error: "请输入 2 到 100 个字符的搜索词" }, 400, origin);
    }

    const apiUrl = new URL(ETSY_API);
    apiUrl.search = new URLSearchParams({
      keywords: keyword,
      limit: String(limit),
      offset: String(offset),
      sort_on: "score",
      sort_order: "desc",
      includes: "Images,Shop",
    });

    try {
      const response = await fetch(apiUrl, {
        headers: {
          "x-api-key": `${env.ETSY_KEYSTRING}:${env.ETSY_SHARED_SECRET}`,
          "accept": "application/json",
          "user-agent": "EtsyMarketRadar/1.0",
        },
      });
      if (!response.ok) {
        const status = response.status === 429 ? 429 : 502;
        return json({ error: status === 429 ? "Etsy API 请求额度暂时用完，请稍后再试" : `Etsy 搜索暂时不可用（HTTP ${response.status}）` }, status, origin);
      }

      const payload = await response.json();
      const listings = Array.isArray(payload.results) ? payload.results : [];
      const items = listings.map((item, index) => {
        const price = item.price || {};
        const images = item.images || item.Images || [];
        const shop = item.shop || item.Shop || {};
        const kind = item.is_digital === true || String(item.type || item.listing_type || "").toLowerCase() === "download" ? "digital" : "physical";
        return {
          listing_id: item.listing_id,
          title: item.title || `Etsy listing ${item.listing_id}`,
          url: item.url || `https://www.etsy.com/listing/${item.listing_id}`,
          image_url: images[0]?.url_570xN || images[0]?.url_fullxfull || null,
          price: price.amount == null ? null : Number(price.amount) / Number(price.divisor || 100),
          currency: price.currency_code || "USD",
          favorites: item.num_favorers ?? null,
          views: item.views ?? null,
          shop_name: shop.shop_name || item.shop_name || "",
          source_query: keyword,
          source_category: "Etsy 全站搜索",
          categories: [],
          listing_type: kind,
          search_rank: offset + index + 1,
          trend_score: null,
          favorites_24h: null,
        };
      });
      const count = Number(payload.count || 0);
      return json({
        query: keyword,
        offset,
        limit,
        total_count: count,
        has_more: offset + listings.length < count,
        items,
      }, 200, origin);
    } catch {
      return json({ error: "连接 Etsy 搜索服务失败，请稍后重试" }, 502, origin);
    }
  },
};
