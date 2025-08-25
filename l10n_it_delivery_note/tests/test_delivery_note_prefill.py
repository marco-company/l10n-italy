# Copyright (c) 2024, OCA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from .delivery_note_common import StockDeliveryNoteCommon


class TestDeliveryNotePrefill(StockDeliveryNoteCommon):
    """Test DDT pre-fill functionality"""

    def setUp(self):
        super().setUp()

        # Create transport data
        self.transport_condition = self.env["stock.picking.transport.condition"].create(
            {"name": "Test Transport Condition"}
        )
        self.transport_condition2 = self.env[
            "stock.picking.transport.condition"
        ].create({"name": "Test Transport Condition 2"})
        self.goods_appearance = self.env["stock.picking.goods.appearance"].create(
            {"name": "Test Goods Appearance"}
        )
        self.transport_reason = self.env["stock.picking.transport.reason"].create(
            {"name": "Test Transport Reason"}
        )
        self.transport_method = self.env["stock.picking.transport.method"].create(
            {"name": "Test Transport Method"}
        )

        # Get UoMs
        self.kg_uom = self.env.ref("uom.product_uom_kgm")
        self.m3_uom = self.env.ref("uom.product_uom_cubic_meter")

    def test_prefill_basic_functionality(self):
        """Test basic pre-fill functionality"""
        # Create a picking with pre-fill data
        picking = self.create_picking()
        picking.write(
            {
                "delivery_transport_condition_id": self.transport_condition.id,
                "delivery_goods_appearance_id": self.goods_appearance.id,
                "delivery_transport_reason_id": self.transport_reason.id,
                "delivery_transport_method_id": self.transport_method.id,
                "delivery_packages": 5,
                "delivery_volume": 2.5,
                "delivery_volume_uom_id": self.m3_uom.id,
                "delivery_gross_weight": 100.0,
                "delivery_gross_weight_uom_id": self.kg_uom.id,
                "delivery_net_weight": 90.0,
                "delivery_net_weight_uom_id": self.kg_uom.id,
            }
        )

        # Validate picking to trigger DDT creation
        picking.action_confirm()
        picking.action_assign()
        picking.move_lines.quantity_done = 1
        picking.button_validate()

        # Check that DDT was created with pre-fill data
        self.assertTrue(picking.delivery_note_id)
        dn = picking.delivery_note_id

        self.assertEqual(dn.transport_condition_id, self.transport_condition)
        self.assertEqual(dn.goods_appearance_id, self.goods_appearance)
        self.assertEqual(dn.transport_reason_id, self.transport_reason)
        self.assertEqual(dn.transport_method_id, self.transport_method)
        self.assertEqual(dn.packages, 5)
        self.assertEqual(dn.volume, 2.5)
        self.assertEqual(dn.volume_uom_id, self.m3_uom)
        self.assertEqual(dn.gross_weight, 100.0)
        self.assertEqual(dn.gross_weight_uom_id, self.kg_uom)
        self.assertEqual(dn.net_weight, 90.0)
        self.assertEqual(dn.net_weight_uom_id, self.kg_uom)

    def test_computed_fields_sync(self):
        """Test automatic computation from picking values (only physical data)"""
        # Create picking and DDT
        picking = self.create_picking()
        picking.action_confirm()
        picking.action_assign()
        picking.move_lines.quantity_done = 1
        picking.button_validate()

        dn = picking.delivery_note_id
        self.assertTrue(dn)

        # Modify physical fields - should be computed to DDT
        picking.write(
            {
                "delivery_packages": 10,
                "delivery_volume": 5.0,
            }
        )

        # Check that only physical data is automatically updated
        self.assertEqual(dn.packages, 10)
        self.assertEqual(dn.volume, 5.0)

        # Transport fields should NOT be updated after DDT creation
        # (they become "static" once DDT is created)
        old_transport_condition = dn.transport_condition_id
        picking.write({"delivery_transport_condition_id": self.transport_condition.id})
        # Transport condition should remain unchanged
        self.assertEqual(dn.transport_condition_id, old_transport_condition)

    def test_visibility_logic(self):
        """Test visibility logic for pre-fill fields"""
        picking = self.create_picking()

        # Initially, no DDT exists - transport fields should be visible
        self.assertFalse(picking.delivery_note_exists)

        # Create DDT
        picking.action_confirm()
        picking.action_assign()
        picking.move_lines.quantity_done = 1
        picking.button_validate()

        # Now DDT exists - transport fields should be hidden,
        # but numeric fields remain visible
        self.assertTrue(picking.delivery_note_exists)

        # Physical information fields should still be accessible for editing
        # Test that we can still modify physical fields after DDT creation
        picking.write(
            {
                "delivery_packages": 15,
                "delivery_volume": 8.0,
                "shipping_weight": 120.0,
                "delivery_net_weight": 110.0,
            }
        )

        # Verify changes are saved (would fail if fields were readonly)
        self.assertEqual(picking.delivery_packages, 15)
        self.assertEqual(picking.delivery_volume, 8.0)
        self.assertEqual(picking.shipping_weight, 120.0)
        self.assertEqual(picking.delivery_net_weight, 110.0)

    def test_weights_calculation(self):
        """Test weights calculation with pre-fill data"""
        # Create picking with pre-fill weights
        picking = self.create_picking()
        picking.write(
            {
                "shipping_weight": 100.0,
                "delivery_net_weight": 90.0,
                "delivery_net_weight_uom_id": self.env.ref("uom.product_uom_kgm").id,
            }
        )

        # Create DDT via normal flow
        picking.action_confirm()
        picking.action_assign()
        picking.move_lines.quantity_done = 1
        picking.button_validate()

        dn = picking.delivery_note_id
        self.assertTrue(dn)

        # Weights should be transferred from pre-fill data during creation
        self.assertEqual(dn.gross_weight, 100.0)
        self.assertEqual(dn.net_weight, 90.0)

        # Test computed fields: modify picking weights after DDT creation
        picking.write(
            {
                "shipping_weight": 120.0,
                "delivery_net_weight": 110.0,
            }
        )

        # DDT should be automatically updated via computed fields
        self.assertEqual(dn.gross_weight, 120.0)
        self.assertEqual(dn.net_weight, 110.0)

    def test_aggregation_multiple_pickings(self):
        """Test aggregation of values from multiple pickings"""
        # Create two pickings with different pre-fill data
        picking1 = self.create_picking()
        picking1.write(
            {
                "delivery_transport_condition_id": self.transport_condition.id,
                "delivery_packages": 3,
                "delivery_volume": 1.5,
                "shipping_weight": 50.0,
            }
        )

        picking2 = self.create_picking()
        picking2.write(
            {
                "delivery_packages": 2,
                "delivery_volume": 1.0,
                "shipping_weight": 30.0,
            }
        )

        # Test aggregation logic is now integrated in _create_delivery_note method
        # We test this by verifying that a DDT created from multiple pickings
        # aggregates correctly
        # Create DDT from multiple pickings via wizard
        wizard = (
            self.env["stock.delivery.note.create.wizard"]
            .with_context(active_ids=(picking1 + picking2).ids)
            .create(
                {
                    "selected_picking_ids": [(6, 0, (picking1 + picking2).ids)],
                }
            )
        )

        dn = wizard.confirm()

        # Physical data should be aggregated correctly
        self.assertEqual(dn.packages, 5)  # 3 + 2
        self.assertEqual(dn.volume, 2.5)  # 1.5 + 1.0
        self.assertEqual(dn.gross_weight, 80.0)  # 50 + 30

        # Transport fields should use first non-empty value
        self.assertEqual(dn.transport_condition_id, self.transport_condition)

    def test_delivery_method_carrier_sync(self):
        """Test that changing delivery method updates carrier using standard fields"""
        picking = self.create_picking()

        # Create a delivery carrier
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "Test Carrier",
                "delivery_type": "fixed",
                "product_id": self.env["product.product"]
                .create(
                    {
                        "name": "Delivery Product",
                        "type": "service",
                    }
                )
                .id,
            }
        )

        # Create partner for the carrier
        carrier_partner = self.env["res.partner"].create(
            {
                "name": "Carrier Partner",
            }
        )
        carrier.partner_id = carrier_partner

        # Set delivery method using standard field
        picking.delivery_method_id = carrier

        # Carrier should be automatically updated using standard field
        self.assertEqual(picking.delivery_note_carrier_id, carrier_partner)

    def test_master_picking_selection(self):
        """Test wizard master picking functionality for multi-picking scenarios"""
        # Create first picking with minimal data
        picking1 = self.create_picking()
        picking1.write(
            {
                "delivery_transport_condition_id": self.transport_condition.id,
                "delivery_packages": 4,
                "delivery_volume": 1.5,
            }
        )

        # Create second picking with more complete data (should become master)
        picking2 = self.create_picking()
        picking2.write(
            {
                "name": "PICK/002",
                "delivery_transport_condition_id": self.transport_condition2.id,
                "delivery_goods_appearance_id": self.goods_appearance.id,
                "delivery_transport_reason_id": self.transport_reason.id,
                "delivery_transport_method_id": self.transport_method.id,
                "delivery_packages": 3,
                "delivery_volume": 2.0,
                "delivery_volume_uom_id": self.m3_uom.id,
            }
        )

        # Create wizard with both pickings
        wizard = self.env["stock.delivery.note.create.wizard"].create(
            {
                "selected_picking_ids": [(6, 0, [picking1.id, picking2.id])],
                "partner_sender_id": self.partner_sender.id,
                "partner_id": self.partner.id,
                "partner_shipping_id": self.partner.id,
                "type_id": self.delivery_note_type.id,
            }
        )

        # Check that picking2 is selected as master (more filled fields)
        self.assertEqual(wizard.master_picking_id, picking2)

        # Check numeric fields are summed
        self.assertEqual(wizard.packages, 7)  # 4 + 3
        self.assertEqual(wizard.volume, 3.5)  # 1.5 + 2.0

        # Check transport data comes from master picking (picking2)
        self.assertEqual(wizard.transport_condition_id, self.transport_condition2)
        self.assertEqual(wizard.goods_appearance_id, self.goods_appearance)
        self.assertEqual(wizard.transport_reason_id, self.transport_reason)

        # Change master to first picking
        wizard.master_picking_id = picking1

        # Transport data should now come from first picking (less complete)
        self.assertEqual(wizard.transport_condition_id, self.transport_condition)
        self.assertFalse(wizard.goods_appearance_id)  # Not set in picking1

        # But numeric fields should remain the same (sum)
        self.assertEqual(wizard.packages, 7)
        self.assertEqual(wizard.volume, 3.5)

    def test_uom_conversion_in_aggregation(self):
        """Test that different UoMs are properly converted during aggregation"""
        # Create UoMs for testing
        kg_uom = self.env.ref("uom.product_uom_kgm")  # kg
        gram_uom = self.env.ref("uom.product_uom_gram")  # g
        m3_uom = self.env.ref("uom.product_uom_cubic_meter")  # m³
        liter_uom = self.env.ref("uom.product_uom_litre")  # L

        # Create first picking with kg and m³
        picking1 = self.create_picking()
        picking1.write(
            {
                "delivery_transport_condition_id": self.transport_condition.id,
                "delivery_gross_weight": 5.0,  # 5 kg
                "delivery_gross_weight_uom_id": kg_uom.id,
                "delivery_volume": 1.0,  # 1 m³
                "delivery_volume_uom_id": m3_uom.id,
            }
        )

        # Create second picking with grams and liters
        picking2 = self.create_picking()
        picking2.write(
            {
                "name": "PICK/002",
                "delivery_transport_condition_id": self.transport_condition2.id,
                "delivery_goods_appearance_id": self.goods_appearance.id,
                "delivery_gross_weight": 2000.0,  # 2000 g = 2 kg
                "delivery_gross_weight_uom_id": gram_uom.id,
                "delivery_volume": 500.0,  # 500 L = 0.5 m³
                "delivery_volume_uom_id": liter_uom.id,
            }
        )

        # Create wizard
        wizard = self.env["stock.delivery.note.create.wizard"].create(
            {
                "selected_picking_ids": [(6, 0, [picking1.id, picking2.id])],
                "partner_sender_id": self.partner_sender.id,
                "partner_id": self.partner.id,
                "partner_shipping_id": self.partner.id,
                "type_id": self.delivery_note_type.id,
            }
        )

        # Check that picking2 is master (more fields filled)
        self.assertEqual(wizard.master_picking_id, picking2)

        # Values should be converted to master's UoM (grams and liters)
        # 5 kg + 2000 g = 5000 g + 2000 g = 7000 g
        self.assertEqual(wizard.gross_weight, 7000.0)
        self.assertEqual(wizard.gross_weight_uom_id, gram_uom)

        # 1 m³ + 500 L = 1000 L + 500 L = 1500 L
        self.assertEqual(wizard.volume, 1500.0)
        self.assertEqual(wizard.volume_uom_id, liter_uom)

        # Change master to picking1 (kg and m³)
        wizard.master_picking_id = picking1

        # Values should be recalculated with picking1's UoM (kg and m³)
        # 5 kg + 2000 g = 5 kg + 2 kg = 7 kg
        self.assertEqual(wizard.gross_weight, 7.0)
        self.assertEqual(wizard.gross_weight_uom_id, kg_uom)

        # 1 m³ + 500 L = 1 m³ + 0.5 m³ = 1.5 m³
        self.assertEqual(wizard.volume, 1.5)
        self.assertEqual(wizard.volume_uom_id, m3_uom)

    def test_manual_uom_change_triggers_recompute(self):
        """Test that manually changing UoM fields triggers numeric recompute"""
        # Create UoMs for testing
        kg_uom = self.env.ref("uom.product_uom_kgm")  # kg
        gram_uom = self.env.ref("uom.product_uom_gram")  # g

        # Create picking with weight in kg
        picking = self.create_picking()
        picking.write(
            {
                "delivery_gross_weight": 5.0,  # 5 kg
                "delivery_gross_weight_uom_id": kg_uom.id,
            }
        )

        # Create wizard
        wizard = self.env["stock.delivery.note.create.wizard"].create(
            {
                "selected_picking_ids": [(6, 0, [picking.id])],
                "partner_sender_id": self.partner_sender.id,
                "partner_id": self.partner.id,
                "partner_shipping_id": self.partner.id,
                "type_id": self.delivery_note_type.id,
            }
        )

        # Initially should use kg (master picking UoM)
        self.assertEqual(wizard.gross_weight, 5.0)
        self.assertEqual(wizard.gross_weight_uom_id, kg_uom)

        # Manually change UoM to grams
        wizard.gross_weight_uom_id = gram_uom

        # Should trigger recompute: 5 kg = 5000 g
        self.assertEqual(wizard.gross_weight, 5000.0)
        self.assertEqual(wizard.gross_weight_uom_id, gram_uom)
