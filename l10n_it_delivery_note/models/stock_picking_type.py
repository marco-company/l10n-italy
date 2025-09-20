from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    delivery_note_before_delivery = fields.Boolean(default=False, string="Enable Delivery Note Before Delivery")