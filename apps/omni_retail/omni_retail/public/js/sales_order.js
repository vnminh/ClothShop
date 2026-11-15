// Nút xử lý + tiến trình cho đơn online (omni_retail)
(() => {
	const LABELS = {
		"Đang xử lý": "Xác nhận đơn",
		"Sẵn sàng giao hàng": "Sẵn sàng giao hàng",
		"Sẵn sàng nhận tại điểm bán": "Sẵn sàng cho khách đến nhận",
		"Đang giao hàng": "Shipper nhận hàng đi giao",
		"Thành công": "Hoàn tất (khách đã nhận hàng)",
		"Giao thất bại": "Giao thất bại",
		"Đã hủy": "Hủy đơn",
		"Đã trả hàng": "Khách trả hàng / hoàn tiền",
	};
	const NEED_NOTE = ["Giao thất bại", "Đã hủy", "Đã trả hàng"];

	function do_transition(frm, to_status, note) {
		frappe.call({
			method: "omni_retail.orders.api.transition",
			args: { sales_order: frm.doc.name, to_status, note },
			freeze: true,
			freeze_message: "Đang xử lý...",
		}).then(() => {
			frappe.show_alert({ message: `Đơn chuyển sang: ${to_status}`, indicator: "green" });
			frm.reload_doc();
		});
	}

	function render_progress(frm, t) {
		const idx = t.steps.indexOf(t.status);
		const off_track = idx < 0;
		const steps = t.steps
			.map((s, i) => {
				const done = !off_track && i <= idx;
				const color = done ? "var(--green-500, #28a745)" : "var(--gray-400, #ccc)";
				return `<div style="flex:1;text-align:center;font-size:12px;">
					<div style="height:6px;border-radius:3px;background:${color};margin-bottom:6px;"></div>
					<span style="${done ? "font-weight:600" : "color:var(--text-muted)"}">${s}</span></div>`;
			})
			.join('<div style="width:6px"></div>');
		const logs = (t.logs || [])
			.map(
				(l) => `<tr><td class="text-muted" style="white-space:nowrap">${frappe.datetime.str_to_user(l.log_time)}</td>
					<td><b>${frappe.utils.escape_html(l.to_status || "")}</b></td>
					<td>${frappe.utils.escape_html(l.actor_name || "")}</td>
					<td>${frappe.utils.escape_html(l.note || "")}</td></tr>`
			)
			.join("");
		const badge = off_track
			? `<div class="mb-2"><span class="indicator-pill ${t.status === "Giao thất bại" ? "orange" : "red"}">${t.status}</span></div>`
			: "";
		const pay = `<div class="text-muted small mt-2">${t.delivery_method}${t.store ? " – " + frappe.utils.escape_html(t.store.store_name) : ""}
			· ${t.payment_method} · ${t.payment_confirmed ? "Đã nhận thanh toán" : "Chưa thanh toán"}
			${t.shipper ? " · Shipper: " + frappe.utils.escape_html(t.shipper) : ""}
			${t.refund_required ? ' · <b class="text-danger">Cần hoàn tiền cho khách</b>' : ""}</div>`;
		const html = `${badge}<div style="display:flex">${steps}</div>${pay}
			<table class="table table-sm small mt-3 mb-0"><tbody>${logs}</tbody></table>`;
		// chèn ngay đầu form (phía trên các tab) để luôn nhìn thấy
		$(frm.layout.wrapper).find(".omni-progress").remove();
		$(`<div class="omni-progress" style="padding:var(--padding-md) var(--padding-lg);border-bottom:1px solid var(--border-color)">
			<div class="text-muted small mb-2" style="font-weight:600;text-transform:uppercase;letter-spacing:.03em">Tiến trình đơn online</div>${html}</div>`)
			.prependTo(frm.layout.wrapper);
	}

	frappe.ui.form.on("Sales Order", {
		refresh(frm) {
			$(frm.layout.wrapper).find(".omni-progress").remove();
			if (!frm.doc.omni_is_online || frm.doc.docstatus === 0 || frm.is_new()) return;
			frappe.call("omni_retail.orders.api.get_order_tracking", { sales_order: frm.doc.name }).then((r) => {
				const t = r.message;
				if (!t) return;
				render_progress(frm, t);
				(t.actions || []).forEach((to_status) => {
					let label = LABELS[to_status] || to_status;
					if (t.status === "Giao thất bại" && to_status === "Sẵn sàng giao hàng") label = "Giao lại";
					frm.add_custom_button(
						label,
						() => {
							if (NEED_NOTE.includes(to_status)) {
								frappe.prompt(
									[{ fieldname: "note", fieldtype: "Small Text", label: "Lý do / ghi chú", reqd: 1 }],
									(v) => do_transition(frm, to_status, v.note),
									label,
									"Xác nhận"
								);
							} else {
								frappe.confirm(`${label}?`, () => do_transition(frm, to_status));
							}
						},
						"Xử lý đơn online"
					);
				});
				if (t.can_confirm_payment) {
					frm.add_custom_button(
						"Xác nhận đã nhận chuyển khoản",
						() => {
							frappe.prompt(
								[{ fieldname: "reference", fieldtype: "Data", label: "Mã giao dịch ngân hàng" }],
								(v) => {
									frappe.call({
										method: "omni_retail.orders.api.confirm_payment",
										args: { sales_order: frm.doc.name, reference: v.reference },
										freeze: true,
									}).then(() => frm.reload_doc());
								},
								"Xác nhận thanh toán",
								"Xác nhận"
							);
						},
						"Xử lý đơn online"
					);
				}
				if ((t.actions || []).length || t.can_confirm_payment) {
					frm.page.set_inner_btn_group_as_primary("Xử lý đơn online");
				}
			});
		},
	});
})();
