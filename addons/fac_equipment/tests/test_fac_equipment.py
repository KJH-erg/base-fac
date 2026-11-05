from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestFacEquipment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.equipment = cls.env['fac.equipment'].create({
            'name': 'Test Lathe',
            'code': 'T-001',
        })

    def test_default_state(self):
        self.assertEqual(self.equipment.state, 'available')
        self.assertFalse(self.equipment.status_log_ids)

    def test_normal_cycle_is_logged(self):
        self.equipment.action_set_in_use()
        self.equipment.action_set_maintenance()
        self.equipment.action_set_available()
        self.assertEqual(self.equipment.state, 'available')
        logs = self.equipment.status_log_ids.sorted('id')
        self.assertEqual(
            [(log.old_state, log.new_state) for log in logs],
            [('available', 'in_use'), ('in_use', 'maintenance'), ('maintenance', 'available')],
        )
        self.assertEqual(self.equipment.status_log_count, 3)
        self.assertEqual(logs[0].changed_by_id, self.env.user)

    def test_broken_must_go_through_maintenance(self):
        self.equipment.action_set_broken()
        with self.assertRaises(UserError):
            self.equipment.action_set_available()
        with self.assertRaises(UserError):
            self.equipment.action_set_in_use()
        self.equipment.action_set_maintenance()
        self.equipment.action_set_available()
        self.assertEqual(self.equipment.state, 'available')

    def test_same_state_is_rejected(self):
        with self.assertRaises(UserError):
            self.equipment.action_set_available()

    def test_maintenance_cannot_start_use(self):
        self.equipment.action_set_maintenance()
        with self.assertRaises(UserError):
            self.equipment.action_set_in_use()

    def test_rejected_transition_is_not_logged(self):
        with self.assertRaises(UserError):
            self.equipment.action_set_available()
        self.assertFalse(self.equipment.status_log_ids)

    def test_code_is_unique(self):
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.env['fac.equipment'].create({'name': 'Duplicate', 'code': 'T-001'})
            self.env.flush_all()
