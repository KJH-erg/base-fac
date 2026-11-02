from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestMesRouting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line_a = cls.env['mrp.workcenter'].create({'name': 'Line A'})
        cls.line_b = cls.env['mrp.workcenter'].create({'name': 'Line B'})
        cls.product = cls.env['product.product'].create({'name': 'Widget', 'is_storable': True})
        cls.bom = cls.env['mrp.bom'].create({'product_tmpl_id': cls.product.product_tmpl_id.id})
        cls.routing = cls.env['mes.routing'].create({
            'name': 'Widget route',
            'code': 'R-1',
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'step_ids': [
                (0, 0, {'name': 'Cut', 'sequence': 1, 'workcenter_id': cls.line_a.id, 'setup_minutes': 10, 'cycle_minutes': 2}),
                (0, 0, {'name': 'Pack', 'sequence': 2, 'workcenter_id': cls.line_b.id, 'setup_minutes': 5, 'cycle_minutes': 1}),
            ],
        })

    def test_minutes_for_qty(self):
        self.assertEqual(self.routing.minutes_for_qty(10), 45)
        self.assertEqual(self.routing.minutes_for_qty(10, self.line_a), 30)

    def test_last_step_follows_sequence(self):
        cut, pack = self.routing.step_ids
        self.assertTrue(pack.is_last_step)
        self.assertFalse(cut.is_last_step)
        cut.sequence = 3
        self.assertTrue(cut.is_last_step)
        self.assertFalse(pack.is_last_step)

    def test_apply_to_bom_replaces_operations(self):
        old = self.env['mrp.routing.workcenter'].create({
            'name': 'Old', 'bom_id': self.bom.id, 'workcenter_id': self.line_a.id,
        })
        self.routing.bom_id = self.bom
        self.routing.action_apply_to_bom()
        self.assertFalse(old.active)
        self.assertEqual(self.bom.operation_ids.mapped('name'), ['Cut', 'Pack'])
        self.assertEqual(self.bom.operation_ids[0].time_cycle_manual, 2)

    def test_apply_needs_target_bom(self):
        with self.assertRaises(UserError):
            self.routing.action_apply_to_bom()

    def test_copy_gets_new_code(self):
        self.assertNotEqual(self.routing.copy().code, self.routing.code)
