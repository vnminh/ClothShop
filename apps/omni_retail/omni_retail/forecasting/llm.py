"""Gọi DeepSeek qua OpenRouter và chuẩn hóa kết quả. Phần parse/chuẩn hóa là thuần Python."""

import json
import re

from omni_retail.forecasting.baseline import clamp

SYSTEM_PROMPT = """Bạn là chuyên gia hoạch định nhu cầu (demand planner) cho một chuỗi bán lẻ thời trang tại Việt Nam.
Nhiệm vụ: xem xét dự báo nền (thống kê) của từng sản phẩm và điều chỉnh theo yếu tố ngoại cảnh: mùa vụ/thời tiết,
lễ tết, sự kiện mua sắm, chương trình khuyến mãi sắp chạy, xu hướng bán gần đây.

Quy tắc:
- `baseline_forecast` là nhu cầu dự kiến trong kỳ dự báo, ĐÃ bao gồm hệ số mùa vụ thống kê (`stat_seasonal_factor`).
- Với mỗi sản phẩm, trả về `factor`: hệ số nhân vào baseline_forecast. factor = 1 nghĩa là đồng ý với dự báo nền.
- Chỉ điều chỉnh khi có căn cứ rõ từ dữ liệu hoặc sự kiện; đừng cộng dồn tác động mùa vụ đã có trong dự báo nền.
- `reason`: 1 câu tiếng Việt ngắn gọn nêu căn cứ (dưới 30 từ).
- `summary`: 3-5 câu tiếng Việt nhận định chung về nhu cầu kỳ tới và rủi ro tồn kho.

Chỉ trả về JSON đúng dạng:
{"summary": "...", "items": [{"code": "<mã sản phẩm>", "factor": 1.0, "reason": "..."}]}"""


def build_messages(payload):
	return [
		{"role": "system", "content": SYSTEM_PROMPT},
		{"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
	]


def call_llm(messages, api_key, model, base_url="https://openrouter.ai/api/v1", timeout=180):
	import requests

	resp = requests.post(
		base_url.rstrip("/") + "/chat/completions",
		headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
		json={
			"model": model,
			"messages": messages,
			"temperature": 0.2,
			"max_tokens": 6000,
			"response_format": {"type": "json_object"},
		},
		timeout=timeout,
	)
	if resp.status_code >= 400:
		raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")
	data = resp.json()
	if data.get("error"):
		raise RuntimeError(f"OpenRouter error: {str(data['error'])[:300]}")
	return data["choices"][0]["message"]["content"]


def parse_json_content(text):
	"""Lấy object JSON từ câu trả lời của model (chấp nhận cả khi bọc trong ```json ... ```)."""
	if isinstance(text, dict):
		return text
	text = (text or "").strip()
	fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
	if fenced:
		text = fenced.group(1).strip()
	try:
		return json.loads(text)
	except ValueError:
		start, end = text.find("{"), text.rfind("}")
		if start >= 0 and end > start:
			return json.loads(text[start : end + 1])
		raise


def normalize_adjustments(raw, valid_codes, lo=0.3, hi=3.0):
	"""Kiểm tra và chặn biên kết quả AI. Trả (summary, {code: {"factor", "reason"}}).
	Bỏ qua mã lạ; hệ số không hợp lệ -> 1.0; hệ số ngoài biên -> kẹp về [lo, hi]."""
	valid = set(valid_codes)
	out = {}
	if not isinstance(raw, dict):
		return "", out
	items = raw.get("items")
	if not isinstance(items, list):
		items = []
	for row in items:
		if not isinstance(row, dict):
			continue
		code = row.get("code")
		if code not in valid:
			continue
		out[code] = {
			"factor": round(clamp(row.get("factor", 1), lo, hi), 3),
			"reason": str(row.get("reason") or "").strip()[:300],
		}
	summary = raw.get("summary")
	return (str(summary).strip() if summary else ""), out
