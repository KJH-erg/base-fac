from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user


class TestMesProductionPlan(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line = cls.env['mrp.workcenter'].create({'name': 'Line A'})
        cls.line.resource_calendar_id.hours_per_day = 8
        cls.product = cls.env['product.product'].create({'name': 'Widget', 'is_storable': True})
        cls.routing = cls.env['mes.routing'].create({
            'name': 'Route',
            'code': 'R-1',
            'step_ids': [(0, 0, {'name': 'Cut', 'workcenter_id': cls.line.id, 'setup_minutes': 30, 'cycle_minutes': 1})],
        })

    def _plan(self, **vals):
        return self.env['mes.production.plan'].create({
            'product_id': self.product.id,
            'workcenter_id': self.line.id,
            'routing_id': self.routing.id,
            'date_planned': '2026-11-02',
            'qty': 90,
        } | vals)

    def test_reference_and_minutes(self):
        plan = self._plan()
        self.assertTrue(plan.name.startswith('PLAN/'))
        self.assertEqual(plan.planned_minutes, 120)

    def test_load_sums_plans_on_same_line_and_day(self):
        first = self._plan()
        second = self._plan()
        self._plan(date_planned='2026-11-03')
        self._plan(state='cancel')
        self.env.invalidate_all()
        self.assertEqual(first.load_percent, 50)
        self.assertEqual(second.load_percent, 50)

    def test_late_flag(self):
        self.assertTrue(self._plan(date_deadline='2026-11-01').is_late)
        self.assertFalse(self._plan(date_deadline='2026-11-02').is_late)

    def test_create_production(self):
        plan = self._plan()
        with self.assertRaises(UserError):
            plan.action_create_production()
        plan.action_confirm()
        plan.action_create_production()
        self.assertEqual(plan.production_id.product_qty, 90)
        self.assertEqual(plan.production_id.origin, plan.name)
        with self.assertRaises(UserError):
            plan.action_create_production()

    def test_access_rights(self):
        user = new_test_user(self.env, login='mes_plan_user', groups='mrp.group_mrp_user')
        plan = self._plan().with_user(user)
        plan.qty = 10
        self.assertTrue(self.routing.with_user(user).name)
        with self.assertRaises(AccessError):
            plan.unlink()
        with self.assertRaises(AccessError):
            self.routing.with_user(user).name = 'Nope'
