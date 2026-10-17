/**
 * Hegazy Brief assistant: a tiny Cloudflare Worker that answers readers' questions with Gemini.
 * Your Gemini key stays here, on the server, never in the website.
 *
 * Settings (Cloudflare dashboard > your worker > Settings > Variables):
 *   GEMINI_API_KEY  (secret)  your Gemini key
 *   ALLOWED_ORIGIN            your site's address, e.g. https://your-username.github.io
 *   GEMINI_MODEL   (optional) a current Gemini model name, default gemini-2.5-flash
 */
const INSTR = "You are the assistant inside Hegazy Brief, a daily briefing on world markets, the economy, finance, accounting, business and politics, explained for Egyptians. " +
  "The reader may know nothing about finance, or may be an expert. Answer in the same language as the question (Arabic or English). " +
  "Start with a direct answer in plain words, explain every technical term you use, and connect the answer to Egypt when it is relevant. " +
  "Use the TODAY'S BRIEF material below for anything about today's news and repeat its numbers exactly. If it does not cover the question, say so, then answer from general knowledge, clearly marked as not from today's brief and possibly out of date. " +
  "Never give personal investment advice and never tell anyone to buy or sell; you may explain how things work. Politics: neutral facts only, no opinions about politicians or parties. " +
  "Keep answers under 170 words unless the reader asks for more. Plain text only.";

const hits = new Map(); // best-effort limit per visitor (per server instance)
function limited(ip) {
  const now = Date.now(), win = 60_000, max = 8;
  const list = (hits.get(ip) || []).filter(t => now - t < win);
  list.push(now); hits.set(ip, list);
  return list.length > max;
}

function cors(origin, allowed) {
  return { "Access-Control-Allow-Origin": origin === allowed ? origin : allowed, "Access-Control-Allow-Methods": "POST, OPTIONS",
           "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin" };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const headers = { ...cors(origin, env.ALLOWED_ORIGIN), "Content-Type": "application/json" };
    if (request.method === "OPTIONS") return new Response(null, { headers });
    if (request.method !== "POST" || origin !== env.ALLOWED_ORIGIN) return new Response(JSON.stringify({ error: "forbidden" }), { status: 403, headers });
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    if (limited(ip)) return new Response(JSON.stringify({ error: "rate_limited" }), { status: 429, headers });

    let body;
    try { body = await request.json(); } catch { return new Response(JSON.stringify({ error: "bad_request" }), { status: 400, headers }); }
    const question = String(body.question || "").slice(0, 600);
    if (!question.trim()) return new Response(JSON.stringify({ error: "empty" }), { status: 400, headers });
    const history = (Array.isArray(body.history) ? body.history : []).slice(-6)
      .map(m => (m.role === "user" ? "Reader: " : "Assistant: ") + String(m.content || "").slice(0, 800)).join("\n");
    const ctx = body.context || {};
    const material = ["Edition: " + String(ctx.date || "").slice(0, 120),
      "Markets: " + (ctx.markets || []).join(" / ").slice(0, 4000),
      "Matching stories:\n" + (ctx.stories || []).join("\n\n").slice(0, 9000),
      "All story titles:\n" + String(body.titles || "").slice(0, 4000)].join("\n\n");
    const prompt = INSTR + "\n\nTODAY'S BRIEF\n" + material + (history ? "\n\nConversation so far:\n" + history : "") + "\n\nReader's question: " + question;

    const model = env.GEMINI_MODEL || "gemini-2.5-flash";
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${env.GEMINI_API_KEY}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.3, maxOutputTokens: 700 } })
    });
    if (r.status === 429) return new Response(JSON.stringify({ error: "rate_limited" }), { status: 429, headers });
    if (!r.ok) return new Response(JSON.stringify({ error: "upstream" }), { status: 502, headers });
    const data = await r.json();
    const answer = (data.candidates?.[0]?.content?.parts || []).map(p => p.text || "").join("").trim();
    return new Response(JSON.stringify({ answer: answer || "Sorry, I couldn't answer that." }), { headers });
  }
};
