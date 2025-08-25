# Copyright (c) 2019, Link IT Europe Srl
# @author: Matteo Bilotta <mbilotta@linkeurope.it>

import datetime

from odoo import api, fields, models

from ..mixins.delivery_mixin import (
    _default_volume_uom,
    _default_weight_uom,
    _domain_volume_uom,
    _domain_weight_uom,
)
from ..mixins.picking_checker import PICKING_TYPES


class StockDeliveryNoteCreateWizard(models.TransientModel):
    _name = "stock.delivery.note.create.wizard"
    _inherit = "stock.delivery.note.base.wizard"
    _description = "Delivery Note Creator"

    def _default_date(self):
        return datetime.date.today()

    def _default_type(self):
        active_ids = self.env.context.get("active_ids", [])
        picking_ids = self.env["stock.picking"].browse(active_ids)
        if picking_ids:
            type_code = picking_ids[0].picking_type_id.code
            company_id = picking_ids[0].company_id
            return self.env["stock.delivery.note.type"].search(
                [("code", "=", type_code), ("company_id", "=", company_id.id)], limit=1
            )

        else:
            return self.env["stock.delivery.note.type"].search(
                [("code", "=", "outgoing")], limit=1
            )

    partner_shipping_id = fields.Many2one("res.partner", required=True)

    date = fields.Date(default=_default_date)
    type_id = fields.Many2one(
        "stock.delivery.note.type", default=_default_type, required=True
    )
    picking_type = fields.Selection(
        PICKING_TYPES, string="Picking type", compute="_compute_picking_type"
    )

    # Override fields with final DDT field names (no mapping needed!)
    transport_condition_id = fields.Many2one("stock.picking.transport.condition")
    goods_appearance_id = fields.Many2one("stock.picking.goods.appearance")
    transport_reason_id = fields.Many2one("stock.picking.transport.reason")
    transport_method_id = fields.Many2one("stock.picking.transport.method")
    carrier_id = fields.Many2one("res.partner")
    transport_datetime = fields.Datetime()
    packages = fields.Integer()
    volume = fields.Float()
    volume_uom_id = fields.Many2one(
        "uom.uom", default=_default_volume_uom, domain=_domain_volume_uom
    )
    gross_weight = fields.Float()
    gross_weight_uom_id = fields.Many2one(
        "uom.uom", default=_default_weight_uom, domain=_domain_weight_uom
    )
    net_weight = fields.Float()
    net_weight_uom_id = fields.Many2one(
        "uom.uom", default=_default_weight_uom, domain=_domain_weight_uom
    )

    # Master picking selection for non-numeric fields
    master_picking_id = fields.Many2one(
        "stock.picking",
        string="Master Picking",
        help="Select which picking to use as master data",
        domain="[('id', 'in', selected_picking_ids)]",
        default=lambda self: self._get_best_master_picking()
        if self.selected_picking_ids
        else False,
    )

    @api.depends("selected_picking_ids")
    def _compute_picking_type(self):
        picking_types = set(self.selected_picking_ids.mapped("picking_type_code"))
        picking_types = list(picking_types)

        if len(picking_types) != 1:
            raise ValueError(
                "You have just called this method on an "
                "heterogeneous set of pickings.\n"
                "All pickings should have the same "
                "'picking_type_code' field value."
            )

        self.picking_type = picking_types[0]

    def _get_best_master_picking(self):
        """Find the picking with the most filled non-numeric fields"""
        if not self.selected_picking_ids:
            return False

        def count_filled_fields(picking):
            """Count how many non-numeric fields are filled in this picking"""
            return sum(
                bool(getattr(picking, field))
                for field in [
                    "delivery_transport_condition_id",
                    "delivery_goods_appearance_id",
                    "delivery_transport_reason_id",
                    "delivery_transport_method_id",
                    "delivery_carrier_id",
                    "delivery_transport_datetime",
                    "delivery_volume_uom_id",
                    "delivery_gross_weight_uom_id",
                    "delivery_net_weight_uom_id",
                ]
            )

        return max(self.selected_picking_ids, key=count_filled_fields)

    def _aggregate_field_with_uom(self, field_name, uom_field_name, target_uom):
        """Helper method to aggregate a field with UoM conversion"""
        total = 0
        for picking in self.selected_picking_ids:
            value = getattr(picking, field_name, 0) or 0
            if value:
                picking_uom = getattr(picking, uom_field_name, False)
                if target_uom and picking_uom:
                    # Always use _compute_quantity (handles same UoM efficiently)
                    converted_value = picking_uom._compute_quantity(value, target_uom)
                    total += converted_value
                else:
                    # Fallback if no UoM available
                    total += value
        return total

    @api.onchange("master_picking_id")
    def _onchange_master_picking_id(self):
        """Auto-populate non-numeric fields from master picking"""
        if not self.master_picking_id:
            return

        # Get values from master picking (hardcoded for performance and clarity)
        master = self.master_picking_id

        # Transport fields
        self.transport_condition_id = master.delivery_transport_condition_id
        self.goods_appearance_id = master.delivery_goods_appearance_id
        self.transport_reason_id = master.delivery_transport_reason_id
        self.transport_method_id = master.delivery_transport_method_id
        self.carrier_id = master.delivery_carrier_id
        self.transport_datetime = master.delivery_transport_datetime

        # UoM fields
        self.volume_uom_id = master.delivery_volume_uom_id
        self.gross_weight_uom_id = master.delivery_gross_weight_uom_id
        self.net_weight_uom_id = master.delivery_net_weight_uom_id

    @api.onchange(
        "selected_picking_ids",
        "master_picking_id",
        "volume_uom_id",
        "gross_weight_uom_id",
        "net_weight_uom_id",
    )
    def _onchange_recompute_numeric_fields(self):
        """Recompute numeric fields with UoM conversion"""
        if not self.selected_picking_ids:
            # Reset fields if no data
            self.packages = 0
            self.volume = 0
            self.gross_weight = 0
            self.net_weight = 0
            return

        # Aggregate numeric fields using wizard's current UoM fields
        self.packages = sum(p.delivery_packages or 0 for p in self.selected_picking_ids)
        self.volume = self._aggregate_field_with_uom(
            "delivery_volume", "delivery_volume_uom_id", self.volume_uom_id
        )
        self.gross_weight = self._aggregate_field_with_uom(
            "delivery_gross_weight",
            "delivery_gross_weight_uom_id",
            self.gross_weight_uom_id,
        )
        self.net_weight = self._aggregate_field_with_uom(
            "delivery_net_weight", "delivery_net_weight_uom_id", self.net_weight_uom_id
        )

    @api.model
    def check_compliance(self, pickings):
        super().check_compliance(pickings)

        self._check_delivery_notes(pickings)
        return True

    @api.onchange("partner_id")
    def _onchange_partner(self):
        self.check_compliance(self.selected_picking_ids)
        self.update(
            {
                "partner_shipping_id": self.partner_id,
                "partner_id": self.selected_picking_ids.mapped("sale_id.partner_id")
                if self.selected_picking_ids.mapped("sale_id.partner_id")
                else self.partner_id,
            }
        )

    def _prepare_delivery_note_vals(self, sale_order_id):
        delivery_method_id = self.selected_picking_ids.mapped("carrier_id")[:1]
        return {
            "company_id": self.selected_picking_ids.mapped("company_id")[:1].id
            or False,
            "partner_sender_id": self.partner_sender_id.id,
            "partner_id": (
                self.selected_picking_ids.mapped("sale_id.partner_id").id
                if self.selected_picking_ids.mapped("sale_id.partner_id").id
                else self.partner_id.id
            ),
            "partner_shipping_id": self.partner_shipping_id.id,
            "type_id": self.type_id.id,
            "date": self.date,
            "carrier_id": self.carrier_id.id or delivery_method_id.partner_id.id,
            "delivery_method_id": self.partner_id.property_delivery_carrier_id.id,
            "transport_condition_id": self.transport_condition_id.id
            or sale_order_id.default_transport_condition_id.id
            or self.partner_id.default_transport_condition_id.id
            or self.type_id.default_transport_condition_id.id,
            "goods_appearance_id": self.goods_appearance_id.id
            or sale_order_id.default_goods_appearance_id.id
            or self.partner_id.default_goods_appearance_id.id
            or self.type_id.default_goods_appearance_id.id,
            "transport_reason_id": self.transport_reason_id.id
            or sale_order_id.default_transport_reason_id.id
            or self.partner_id.default_transport_reason_id.id
            or self.type_id.default_transport_reason_id.id,
            "transport_method_id": self.transport_method_id.id
            or sale_order_id.default_transport_method_id.id
            or self.partner_id.default_transport_method_id.id
            or self.type_id.default_transport_method_id.id,
            "transport_datetime": self.transport_datetime,
            "packages": self.packages,
            "volume": self.volume,
            "volume_uom_id": self.volume_uom_id.id or False,
            "gross_weight": self.gross_weight,
            "gross_weight_uom_id": self.gross_weight_uom_id.id or False,
            "net_weight": self.net_weight,
            "net_weight_uom_id": self.net_weight_uom_id.id or False,
        }

    def confirm(self):
        self.check_compliance(self.selected_picking_ids)

        sale_order_ids = self.mapped("selected_picking_ids.sale_id")
        sale_order_id = sale_order_ids and sale_order_ids[0] or self.env["sale.order"]

        delivery_note = self.env["stock.delivery.note"].create(
            self._prepare_delivery_note_vals(sale_order_id)
        )

        self.selected_picking_ids.write({"delivery_note_id": delivery_note.id})
        if sale_order_id:
            sale_order_id._assign_delivery_notes_invoices(sale_order_id.invoice_ids.ids)

        if self.user_has_groups("l10n_it_delivery_note.use_advanced_delivery_notes"):
            return delivery_note.goto()
