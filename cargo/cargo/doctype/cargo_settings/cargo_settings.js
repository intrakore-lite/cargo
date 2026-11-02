// Copyright (c) 2026, Aradhya-Tripathi and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cargo Settings", {
	refresh(frm) {
		frm.add_custom_button(
			__("Base Images"),
			() => {
				frappe.confirm(
					__(
						"Build a Base image of the newest Pilot release on the head commit of each Frappe branch? Branches that already have one are skipped."
					),
					() =>
						frm
							.call({ doc: frm.doc, method: "build_base_images", freeze: true })
							.then(({ message }) =>
								frappe.show_alert(__("Started {0} Base images", [message.length]))
							)
				);
			},
			__("Build")
		);
		frm.add_custom_button(
			__("Sync INTRAKORE Apps"),
			() => sync_intrakore_apps(frm),
			__("Build")
		);
	},
});

function sync_intrakore_apps(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Sync INTRAKORE Apps"),
		fields: [
			{
				fieldname: "lock",
				fieldtype: "Code",
				label: __("Lock File"),
				description: __("Paste a lock file, or leave blank to read the Lock File URL."),
			},
			{
				fieldname: "manifest",
				fieldtype: "Code",
				label: __("Manifest"),
				description: __("Optional. Leave blank to read the Manifest URL, if set."),
			},
		],
		primary_action_label: __("Sync"),
		primary_action(values) {
			dialog.hide();
			frm.call({
				doc: frm.doc,
				method: "sync_intrakore_apps",
				args: values,
				freeze: true,
			}).then(({ message }) => {
				frappe.show_alert(__("{0} apps moved", [message.length]));
				frm.reload_doc();
			});
		},
	});
	dialog.show();
}
