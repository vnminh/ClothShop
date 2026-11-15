// omni_retail – mở rộng Webshop: (1) checkout chọn hình thức nhận hàng/thanh toán, (2) theo dõi đơn online
(function () {
	if (!window.frappe || !frappe.ready) return;
	const HOME = "Giao tại nhà";
	const PICKUP = "Nhận tại điểm bán";
	const TRANSFER = "Chuyển khoản";
	const esc = (s) => $("<div>").text(s == null ? "" : s).html();

	// ------------------------------------------------------------------ checkout
	const state = { delivery_method: HOME, pickup_store: null, payment_method: null, options: null };

	function render_checkout() {
		const o = state.options;
		const $slot = $(".omni-checkout");
		const stores = o.stores
			.map(
				(s) => `<option value="${esc(s.name)}" ${s.in_stock ? "" : "disabled"} ${state.pickup_store === s.name ? "selected" : ""}>
					${esc(s.store_name)}${s.in_stock ? "" : " (không đủ hàng)"}</option>`
			)
			.join("");
		const store = o.stores.find((s) => s.name === state.pickup_store);
		const home_short = (o.home_shortages || []).length;
		$slot.html(`
			<h6>Hình thức nhận hàng</h6>
			${o.delivery_methods
				.map(
					(m) => `<label><input type="radio" name="omni_delivery" value="${esc(m)}" ${state.delivery_method === m ? "checked" : ""}>
						<span>${esc(m)}</span></label>`
				)
				.join("")}
			${
				state.delivery_method === PICKUP
					? `<select class="form-control omni-store"><option value="">-- Chọn điểm bán --</option>${stores}</select>
						${store ? `<div class="omni-note"><b>${esc(store.store_name)}</b><br>${esc(store.address || "")}${store.phone ? "<br>ĐT: " + esc(store.phone) : ""}
						<br>Hàng được giữ ${o.pickup_expiry_days} ngày kể từ khi sẵn sàng.</div>` : ""}`
					: home_short
					? `<div class="omni-warn">Kho giao hàng hiện không đủ một số sản phẩm trong giỏ. Bạn có thể chọn nhận tại điểm bán còn hàng.</div>`
					: ""
			}
			<h6>Thanh toán</h6>
			${o.payment_methods
				.map(
					(m) => `<label><input type="radio" name="omni_payment" value="${esc(m)}" ${state.payment_method === m ? "checked" : ""}>
						<span>${esc(m === TRANSFER ? "Chuyển khoản ngân hàng" : state.delivery_method === PICKUP ? "Thanh toán khi nhận hàng tại quầy" : m)}</span></label>`
				)
				.join("")}
			${state.payment_method === TRANSFER && o.bank_transfer_info ? `<div class="omni-note">${esc(o.bank_transfer_info)}</div>` : ""}
		`);
		// đơn nhận tại điểm bán không cần địa chỉ giao hàng
		$('[data-section="shipping-address"]').toggle(state.delivery_method !== PICKUP);
	}

	function init_checkout() {
		const $btn = $(".btn-place-order");
		if (!$btn.length) return;
		$btn.text("Đặt hàng");
		$(".place-order").before('<div class="omni-checkout"></div>');
		frappe.call("omni_retail.orders.checkout.get_checkout_options").then((r) => {
			state.options = r.message;
			Object.assign(state, r.message.selected);
			render_checkout();
		});
		$(document).on("change", "input[name=omni_delivery]", function () {
			state.delivery_method = this.value;
			render_checkout();
		});
		$(document).on("change", "input[name=omni_payment]", function () {
			state.payment_method = this.value;
			render_checkout();
		});
		$(document).on("change", ".omni-store", function () {
			state.pickup_store = this.value || null;
			render_checkout();
		});
		// chặn handler gốc của Webshop (capture phase) để gọi API đặt hàng của omni_retail
		document.addEventListener(
			"click",
			function (e) {
				const btn = e.target.closest && e.target.closest(".btn-place-order");
				if (!btn) return;
				e.preventDefault();
				e.stopImmediatePropagation();
				place_order(btn);
			},
			true
		);
	}

	function place_order(btn) {
		if (state.delivery_method === PICKUP && !state.pickup_store) {
			frappe.msgprint("Vui lòng chọn điểm bán để nhận hàng.");
			return;
		}
		frappe.call({
			type: "POST",
			method: "omni_retail.orders.checkout.place_order",
			args: {
				delivery_method: state.delivery_method,
				pickup_store: state.pickup_store,
				payment_method: state.payment_method,
			},
			btn: btn,
			freeze: true,
			freeze_message: "Đang đặt hàng...",
			callback: function (r) {
				if (!r.exc && r.message) {
					$(".cart-container table").hide();
					window.location.href = "/orders/" + encodeURIComponent(r.message);
				}
			},
		});
	}

	// ------------------------------------------------------------------ theo dõi đơn
	function fmt_time(s) {
		const d = new Date((s || "").replace(" ", "T"));
		return isNaN(d) ? s : d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
	}

	function render_tracking(t) {
		const idx = t.steps.indexOf(t.status);
		const steps = t.steps.map((s, i) => `<div class="omni-step ${idx >= 0 && i <= idx ? "done" : ""}">${esc(s)}</div>`).join("");
		const logs = (t.logs || [])
			.slice()
			.reverse()
			.map((l) => `<li><time>${esc(fmt_time(l.log_time))}</time><b>${esc(l.to_status)}</b><span>${esc(l.note || "")}</span></li>`)
			.join("");
		const can_cancel = (t.actions || []).includes("Đã hủy");
		const meta = [
			esc(t.delivery_method) + (t.store ? ": <b>" + esc(t.store.store_name) + "</b> – " + esc(t.store.address || "") : ""),
			esc(t.payment_method) + (t.payment_confirmed ? " (đã thanh toán)" : ""),
			t.shipper ? "Shipper: " + esc(t.shipper) : "",
			t.refund_required ? "<b>Đơn sẽ được hoàn tiền</b>" : "",
		]
			.filter(Boolean)
			.join(" · ");
		return `<div class="omni-track">
			<div class="omni-track-head">
				<div class="omni-track-status ${idx < 0 ? "is-bad" : ""}">${esc(t.status)}</div>
				${can_cancel ? '<button class="btn btn-sm btn-danger omni-cancel">Hủy đơn hàng</button>' : ""}
			</div>
			<div class="omni-steps">${steps}</div>
			<div class="omni-track-meta">${meta}</div>
			${t.bank_transfer_info ? `<div class="omni-checkout" style="border:0;margin:0;padding:0"><div class="omni-note"><b>Thông tin chuyển khoản:</b> ${esc(t.bank_transfer_info)}</div></div>` : ""}
			<ul>${logs}</ul>
		</div>`;
	}

	function init_tracking() {
		const m = window.location.pathname.match(/^\/orders\/(.+)$/);
		if (!m) return;
		const name = decodeURIComponent(m[1]);
		frappe.call({ method: "omni_retail.orders.api.get_order_tracking", args: { sales_order: name } }).then((r) => {
			const t = r.message;
			if (!t) return;
			$(".omni-track").remove();
			const $target = $(".page_content").first().length ? $(".page_content").first() : $("main").first();
			$target.prepend(render_tracking(t));
			$(".omni-cancel").on("click", function () {
				frappe.confirm("Bạn chắc chắn muốn hủy đơn hàng này?", () => {
					frappe.call({
						method: "omni_retail.orders.api.cancel_my_order",
						args: { sales_order: name },
						freeze: true,
					}).then(() => window.location.reload());
				});
			});
		});
	}

	frappe.ready(function () {
		if (window.location.pathname === "/cart") init_checkout();
		init_tracking();
	});
})();
