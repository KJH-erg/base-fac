from odoo.tests import TransactionCase, new_test_user


class TestMesKpi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line = cls.env['mrp.workcenter'].create({'name': 'KPI Line', 'oee_target': 90})
        cls.product = cls.env['product.product'].create({'name': 'Widget', 'is_storable': True})
        cls.routing = cls.env['mes.routing'].create({
            'name': 'Route',
            'code': 'R-KPI',
            'step_ids': [(0, 0, {'name': 'Make', 'workcenter_id': cls.line.id, 'cycle_minutes': 1})],
        })
        cls.plan = cls.env['mes.production.plan'].create({
            'product_id': cls.product.id,
            'workcenter_id': cls.line.id,
            'routing_id': cls.routing.id,
            'date_planned': '2031-03-10',
            'qty': 100,
        })
        cls.plan.action_confirm()
        # 120 min elapsed, 20 min down, 100 min run, 80 units made at 1 min standard.
        cls.result = cls.env['mes.production.result'].create({
            'plan_id': cls.plan.id,
            'step_id': cls.routing.step_ids.id,
            'date': '2031-03-10',
            'date_start': '2031-03-10 08:00:00',
            'date_end': '2031-03-10 10:00:00',
            'downtime_minutes': 20,
            'good_qty': 72,
            'defect_qty': 8,
        })
        cls.result.action_confirm()

    def _dashboard(self, date_from='2031-03-01', date_to='2031-03-31'):
        return self.env['mes.kpi.report'].get_dashboard_data(date_from, date_to)

    def test_oee_components(self):
        line = self._dashboard()['lines'][0]
        self.assertEqual(line['workcenter_id'], self.line.id)
        self.assertAlmostEqual(line['availability'], 100 / 120 * 100)
        self.assertAlmostEqual(line['performance'], 80)
        self.assertAlmostEqual(line['quality'], 90)
        self.assertAlmostEqual(line['oee'], (100 / 120) * 0.8 * 0.9 * 100)
        self.assertEqual(line['achievement'], 72)
        self.assertEqual(line['defect_rate'], 10)
        self.assertEqual(line['oee_target'], 90)

    def test_ratios_use_summed_quantities(self):
        """A 10-unit day at 100% and a 90-unit day at 50% is 55%, not their 75% average."""
        for day, good, defect in (('2031-04-01', 10, 0), ('2031-04-02', 45, 45)):
            self.env['mes.production.result'].create({
                'workcenter_id': self.line.id,
                'product_id': self.product.id,
                'date': day,
                'date_start': f'{day} 08:00:00',
                'date_end': f'{day} 09:00:00',
                'good_qty': good,
                'defect_qty': defect,
            }).action_confirm()
        self.assertAlmostEqual(self._dashboard('2031-04-01', '2031-04-30')['overall']['quality'], 55)

    def test_no_standard_time_means_no_oee(self):
        self.env['mes.production.result'].create({
            'workcenter_id': self.line.id,
            'product_id': self.product.id,
            'date': '2031-05-01',
            'date_start': '2031-05-01 08:00:00',
            'date_end': '2031-05-01 09:00:00',
            'good_qty': 1,
        }).action_confirm()
        overall = self._dashboard('2031-05-01', '2031-05-31')['overall']
        self.assertIsNone(overall['performance'])
        self.assertIsNone(overall['oee'])
        self.assertEqual(overall['quality'], 100)

    def test_draft_and_out_of_period_are_excluded(self):
        self.result.action_draft()
        line = self._dashboard()['lines'][0]
        self.assertEqual(line['good_qty'], 0)
        self.assertEqual(line['planned_qty'], 100)
        self.assertEqual(self._dashboard('2031-06-01', '2031-06-30')['lines'], [])

    def test_mrp_user_can_read_dashboard(self):
        user = new_test_user(self.env, login='mes_kpi_user', groups='mrp.group_mrp_user')
        data = self.env['mes.kpi.report'].with_user(user).get_dashboard_data('2031-03-01', '2031-03-31')
        self.assertEqual(data['lines'][0]['good_qty'], 72)
