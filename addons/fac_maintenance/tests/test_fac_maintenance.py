from datetime import datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFacMaintenance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.request = cls.env['fac.maintenance.request'].create({
            'title': 'Noise from spindle',
            'equipment_ref': 'EQ-T-01',
            'technician_id': cls.env.user.id,
        })

    def test_reference_from_sequence(self):
        self.assertTrue(self.request.name.startswith('MR/'))

    def test_normal_flow(self):
        self.assertEqual(self.request.state, 'requested')
        self.request.action_start()
        self.assertEqual(self.request.state, 'in_progress')
        self.assertTrue(self.request.date_started)
        self.request.write({'work_description': 'Replaced bearing', 'cost': 150})
        self.request.action_done()
        self.assertEqual(self.request.state, 'done')
        self.assertTrue(self.request.date_done)

    def test_start_needs_technician(self):
        self.request.technician_id = False
        with self.assertRaises(UserError):
            self.request.action_start()

    def test_done_needs_work_description(self):
        self.request.action_start()
        with self.assertRaises(UserError):
            self.request.action_done()

    def test_cannot_finish_before_start(self):
        self.request.work_description = 'Nothing'
        with self.assertRaises(UserError):
            self.request.action_done()

    def test_cancel_and_reopen(self):
        self.request.action_start()
        self.request.action_cancel()
        self.assertEqual(self.request.state, 'cancelled')
        self.request.action_reopen()
        self.assertEqual(self.request.state, 'requested')
        self.assertFalse(self.request.date_started)

    def test_done_cannot_be_cancelled(self):
        self.request.action_start()
        self.request.work_description = 'Done'
        self.request.action_done()
        with self.assertRaises(UserError):
            self.request.action_cancel()

    def test_duration(self):
        self.request.write({
            'date_started': datetime(2026, 10, 1, 8, 0),
            'date_done': datetime(2026, 10, 1, 10, 30),
        })
        self.assertAlmostEqual(self.request.duration_hours, 2.5)

    def test_history_by_equipment(self):
        Request = self.env['fac.maintenance.request']
        for title in ('First', 'Second'):
            request = Request.create({
                'title': title, 'equipment_ref': 'EQ-T-02', 'technician_id': self.env.user.id,
                'work_description': 'Fixed', 'cost': 10,
            })
            request.action_start()
            request.action_done()
        history = Request.search([('equipment_ref', '=', 'EQ-T-02'), ('state', '=', 'done')])
        self.assertEqual(len(history), 2)
        self.assertEqual(sum(history.mapped('cost')), 20)

    def test_cost_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self.request.cost = -1
