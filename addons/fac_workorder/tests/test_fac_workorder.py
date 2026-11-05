from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFacWorkorder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workorder = cls.env['fac.workorder'].create({
            'product_name': 'Test Part',
            'quantity': 5,
            'equipment_ref': 'EQ-T-01',
            'assignee_id': cls.env.user.id,
        })

    def test_reference_from_sequence(self):
        self.assertTrue(self.workorder.name.startswith('WO/'))
        other = self.env['fac.workorder'].create({'product_name': 'Other', 'quantity': 1})
        self.assertNotEqual(self.workorder.name, other.name)

    def test_normal_flow_with_hold(self):
        self.assertEqual(self.workorder.state, 'planned')
        self.workorder.action_start()
        self.assertEqual(self.workorder.state, 'in_progress')
        self.assertTrue(self.workorder.date_started)
        self.workorder.hold_reason = 'Waiting for material'
        self.workorder.action_hold()
        self.assertEqual(self.workorder.state, 'on_hold')
        self.workorder.action_resume()
        self.assertEqual(self.workorder.state, 'in_progress')
        self.assertFalse(self.workorder.hold_reason)
        self.workorder.action_done()
        self.assertEqual(self.workorder.state, 'done')
        self.assertTrue(self.workorder.date_done)

    def test_cannot_finish_before_start(self):
        with self.assertRaises(UserError):
            self.workorder.action_done()

    def test_cannot_hold_planned(self):
        with self.assertRaises(UserError):
            self.workorder.action_hold()

    def test_cannot_finish_while_on_hold(self):
        self.workorder.action_start()
        self.workorder.action_hold()
        with self.assertRaises(UserError):
            self.workorder.action_done()

    def test_done_is_final(self):
        self.workorder.action_start()
        self.workorder.action_done()
        for action in ('action_start', 'action_hold', 'action_resume', 'action_done'):
            with self.subTest(action=action), self.assertRaises(UserError):
                getattr(self.workorder, action)()

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.env['fac.workorder'].create({'product_name': 'Bad', 'quantity': 0})
