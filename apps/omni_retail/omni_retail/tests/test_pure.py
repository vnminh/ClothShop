"""Unit test cho phần logic thuần (không cần site): state machine, dự báo nền, chuẩn hóa kết quả AI.

Chạy: bench --site <site> run-tests --module omni_retail.tests.test_pure
hoặc: python -m unittest omni_retail.tests.test_pure (trong thư mục app)
"""

import unittest

from omni_retail.constants import (
	ACTOR_CUSTOMER, ACTOR_SHIPPER, ACTOR_STAFF, ACTOR_SYSTEM, CANCELLED, DELIVERY_HOME, DELIVERY_PICKUP,
	DONE, FAILED, PENDING, PROCESSING, READY_PICKUP, READY_SHIP, RETURNED, SHIPPING,
)
from omni_retail.forecasting import baseline, llm
from omni_retail.orders.state_machine import TransitionError, check_transition, next_statuses


class TestStateMachine(unittest.TestCase):
	def test_home_delivery_happy_path(self):
		path = [
			(PENDING, PROCESSING, ACTOR_STAFF), (PROCESSING, READY_SHIP, ACTOR_STAFF),
			(READY_SHIP, SHIPPING, ACTOR_SHIPPER), (SHIPPING, DONE, ACTOR_SHIPPER),
		]
		for src, dst, actor in path:
			self.assertTrue(check_transition(src, dst, DELIVERY_HOME, [actor]))

	def test_pickup_happy_path(self):
		for src, dst in [(PENDING, PROCESSING), (PROCESSING, READY_PICKUP), (READY_PICKUP, DONE)]:
			self.assertTrue(check_transition(src, dst, DELIVERY_PICKUP, [ACTOR_STAFF]))

	def test_cannot_skip_steps(self):
		for src, dst in [(PENDING, READY_SHIP), (PENDING, SHIPPING), (PROCESSING, DONE), (READY_SHIP, DONE)]:
			with self.assertRaises(TransitionError):
				check_transition(src, dst, DELIVERY_HOME, [ACTOR_STAFF, ACTOR_SHIPPER])

	def test_delivery_method_is_enforced(self):
		with self.assertRaises(TransitionError):
			check_transition(PROCESSING, READY_SHIP, DELIVERY_PICKUP, [ACTOR_STAFF])
		with self.assertRaises(TransitionError):
			check_transition(PROCESSING, READY_PICKUP, DELIVERY_HOME, [ACTOR_STAFF])

	def test_roles(self):
		with self.assertRaises(TransitionError):  # nhân viên không tự đánh dấu đang giao
			check_transition(READY_SHIP, SHIPPING, DELIVERY_HOME, [ACTOR_STAFF])
		with self.assertRaises(TransitionError):  # shipper không xác nhận đơn
			check_transition(PENDING, PROCESSING, DELIVERY_HOME, [ACTOR_SHIPPER])
		with self.assertRaises(TransitionError):  # khách không tự xác nhận
			check_transition(PENDING, PROCESSING, DELIVERY_HOME, [ACTOR_CUSTOMER])

	def test_cancellation_rules(self):
		self.assertTrue(check_transition(PENDING, CANCELLED, DELIVERY_HOME, [ACTOR_CUSTOMER]))
		with self.assertRaises(TransitionError):  # khách chỉ hủy khi còn chờ xác nhận
			check_transition(PROCESSING, CANCELLED, DELIVERY_HOME, [ACTOR_CUSTOMER])
		for src in (PENDING, PROCESSING, READY_SHIP, FAILED):
			self.assertTrue(check_transition(src, CANCELLED, DELIVERY_HOME, [ACTOR_STAFF]))
		for src in (SHIPPING, DONE, CANCELLED, RETURNED):
			with self.assertRaises(TransitionError):
				check_transition(src, CANCELLED, DELIVERY_HOME, [ACTOR_STAFF, ACTOR_SYSTEM])
		self.assertTrue(check_transition(READY_PICKUP, CANCELLED, DELIVERY_PICKUP, [ACTOR_SYSTEM]))

	def test_failed_delivery_and_return(self):
		self.assertTrue(check_transition(SHIPPING, FAILED, DELIVERY_HOME, [ACTOR_SHIPPER]))
		self.assertTrue(check_transition(FAILED, READY_SHIP, DELIVERY_HOME, [ACTOR_STAFF]))
		self.assertTrue(check_transition(DONE, RETURNED, DELIVERY_HOME, [ACTOR_STAFF]))
		with self.assertRaises(TransitionError):
			check_transition(RETURNED, DONE, DELIVERY_HOME, [ACTOR_STAFF])

	def test_next_statuses(self):
		self.assertEqual(set(next_statuses(PENDING, DELIVERY_HOME, [ACTOR_STAFF])), {PROCESSING, CANCELLED})
		self.assertEqual(next_statuses(PENDING, DELIVERY_HOME, [ACTOR_CUSTOMER]), [CANCELLED])
		self.assertEqual(set(next_statuses(SHIPPING, DELIVERY_HOME, [ACTOR_SHIPPER])), {DONE, FAILED})
		self.assertEqual(next_statuses(DONE, DELIVERY_HOME, [ACTOR_SHIPPER]), [])
		self.assertEqual(next_statuses(CANCELLED, DELIVERY_HOME, [ACTOR_STAFF, ACTOR_SHIPPER, ACTOR_SYSTEM]), [])


class TestBaseline(unittest.TestCase):
	def test_recent_rate_constant_series(self):
		self.assertAlmostEqual(baseline.recent_daily_rate([14] * 20), 2.0)

	def test_recent_rate_weights_recent_weeks_more(self):
		rising = [0, 0, 0, 0, 14, 14, 14, 14]
		self.assertGreater(baseline.recent_daily_rate(rising), 1.0)  # TB đơn giản sẽ là 1.0
		self.assertEqual(baseline.recent_daily_rate([]), 0.0)

	def test_seasonal_factor_needs_a_year_of_history(self):
		self.assertEqual(baseline.seasonal_factor([10] * 40, 28), 1.0)

	def test_seasonal_factor_detects_last_year_uplift(self):
		# 78 tuần: năm trước, 4 tuần sau "hôm nay" bán gấp đôi 8 tuần trước đó
		weekly = [10.0] * 78
		pivot = 78 - 52
		for i in range(pivot, pivot + 4):
			weekly[i] = 20.0
		self.assertAlmostEqual(baseline.seasonal_factor(weekly, 28), 2.0)

	def test_seasonal_factor_is_clamped_and_ignores_thin_data(self):
		weekly = [10.0] * 78
		pivot = 78 - 52
		for i in range(pivot, pivot + 4):
			weekly[i] = 500.0
		self.assertEqual(baseline.seasonal_factor(weekly, 28), 2.5)
		thin = [0.0] * 78
		thin[pivot] = 30
		self.assertEqual(baseline.seasonal_factor(thin, 28), 1.0)

	def test_baseline_forecast(self):
		out = baseline.baseline_forecast([7] * 20, 30)
		self.assertAlmostEqual(out["daily_rate"], 1.0)
		self.assertAlmostEqual(out["forecast"], 30.0)

	def test_suggest_order_qty(self):
		# 2/ngày, lead 7 + phủ 30 + an toàn 7 = 44 ngày -> 88; tồn 20, đang về 10 -> 58
		self.assertEqual(baseline.suggest_order_qty(2, 7, 30, 7, 20, 10), 58)
		self.assertEqual(baseline.suggest_order_qty(2, 7, 30, 7, 200, 0), 0)  # đủ hàng
		self.assertEqual(baseline.suggest_order_qty(2, 7, 30, 7, 20, 10, multiple=10), 60)
		self.assertEqual(baseline.suggest_order_qty(0.1, 7, 30, 7, 0, 0, min_order_qty=20), 20)
		self.assertEqual(baseline.suggest_order_qty(0, 7, 30, 7, 0, 0, min_order_qty=20), 0)  # không bán -> không đặt
		self.assertEqual(baseline.suggest_order_qty(2, 7, 30, 7, -5, 0), 88)  # tồn âm coi như 0

	def test_bucketize(self):
		self.assertEqual(baseline.bucketize([1] * 8, 4), [4, 4])
		self.assertEqual(baseline.bucketize([1] * 6, 4), [2, 4])


class TestLLMParsing(unittest.TestCase):
	def test_parse_plain_and_fenced(self):
		self.assertEqual(llm.parse_json_content('{"a": 1}'), {"a": 1})
		self.assertEqual(llm.parse_json_content('```json\n{"a": 1}\n```'), {"a": 1})
		self.assertEqual(llm.parse_json_content('Kết quả: {"a": 1} hết.'), {"a": 1})
		with self.assertRaises(ValueError):
			llm.parse_json_content("không có json")

	def test_normalize_clamps_and_filters(self):
		raw = {
			"summary": " Nhu cầu tăng. ",
			"items": [
				{"code": "A", "factor": 1.4, "reason": "mùa lạnh"},
				{"code": "B", "factor": 50},  # vượt biên
				{"code": "C", "factor": "abc"},  # không hợp lệ
				{"code": "D", "factor": -2},  # âm
				{"code": "X", "factor": 2},  # mã lạ
				"rác",
			],
		}
		summary, adj = llm.normalize_adjustments(raw, ["A", "B", "C", "D"], 0.3, 3.0)
		self.assertEqual(summary, "Nhu cầu tăng.")
		self.assertEqual(adj["A"], {"factor": 1.4, "reason": "mùa lạnh"})
		self.assertEqual(adj["B"]["factor"], 3.0)
		self.assertEqual(adj["C"]["factor"], 1.0)
		self.assertEqual(adj["D"]["factor"], 0.3)
		self.assertNotIn("X", adj)

	def test_normalize_handles_garbage(self):
		self.assertEqual(llm.normalize_adjustments(None, ["A"]), ("", {}))
		self.assertEqual(llm.normalize_adjustments({"items": "x"}, ["A"]), ("", {}))


if __name__ == "__main__":
	unittest.main()
