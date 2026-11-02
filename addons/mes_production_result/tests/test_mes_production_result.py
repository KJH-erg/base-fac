from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase


class TestMesProductionResult(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line = cls.env['mrp.workcenter'].create({'name': 'Line A'})
        cls.product = cls.env['product.product'].create({'name': 'Widget', 'is_storable': True})
        cls.routing = cls.env['mes.routing'].create({
            'name': 'Route',
            'code': 'R-1',
            'step_ids': [
                (0, 0, {'name': 'Cut', 'sequence': 1, 'workcenter_id': cls.line.id, 'cycle_minutes': 1}),
                (0, 0, {'name': 'Pack', 'sequence': 2, 'workcenter_id': cls.line.id, 'cycle_minutes': 0.5}),
            ],
        })
        cls.cut, cls.pack = cls.routing.step_ids
        cls.plan = cls.env['mes.production.plan'].create({
            'product_id': cls.product.id,
            'workcenter_id': cls.line.id,
            'routing_id': cls.routing.id,
            'qty': 100,
        })
        cls.plan.action_confirm()

    def _result(self, **vals):
        return self.env['mes.production.result'].create({
            'plan_id': self.plan.id,
            'date_start': '2026-11-02 08:00:00',
            'date_end': '2026-11-02 10:00:00',
        } | vals)

    def test_defaults_come_from_plan_and_step(self):
        result = self._result(step_id=self.pack.id, good_qty=1)
        self.assertEqual(result.workcenter_id, self.line)
        self.assertEqual(result.product_id, self.product)
        self.assertTrue(result.name.startswith('RES/'))

    def test_minutes(self):
        result = self._result(step_id=self.pack.id, good_qty=90, defect_qty=10, downtime_minutes=20)
        self.assertEqual(result.work_minutes, 120)
        self.assertEqual(result.run_minutes, 100)
        self.assertEqual(result.standard_minutes, 50)
        self.assertEqual(result.defect_rate, 10)

    def test_only_last_step_counts_as_output(self):
        self._result(step_id=self.cut.id, good_qty=60, defect_qty=5).action_confirm()
        self.assertEqual(self.plan.good_qty, 0)
        self.assertEqual(self.plan.defect_qty, 5)
        self._result(step_id=self.pack.id, good_qty=60).action_confirm()
        self.assertEqual(self.plan.good_qty, 60)
        self.assertEqual(self.plan.achievement_percent, 60)

    def test_draft_results_do_not_count(self):
        self._result(step_id=self.pack.id, good_qty=60)
        self.assertEqual(self.plan.good_qty, 0)

    def test_plan_state_follows_output(self):
        result = self._result(step_id=self.pack.id, good_qty=100)
        result.action_confirm()
        self.assertEqual(self.plan.state, 'done')
        result.action_draft()
        self.assertEqual(self.plan.state, 'confirmed')

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self._result(date_end='2026-11-02 07:00:00')
        with self.assertRaises(ValidationError):
            self._result(downtime_minutes=121)
        with self.assertRaises(UserError):
            self._result().action_confirm()
        result = self._result(good_qty=1)
        result.action_confirm()
        with self.assertRaises(UserError):
            result.unlink()
