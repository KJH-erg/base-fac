from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestFacMaterial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.material = cls.env['fac.material'].create({
            'name': 'Test Bar',
            'code': 'T-BAR',
            'uom': 'm',
            'min_qty': 10,
        })

    def _move(self, move_type, quantity, confirm=True):
        move = self.env['fac.material.move'].create({
            'material_id': self.material.id,
            'move_type': move_type,
            'quantity': quantity,
        })
        if confirm:
            move.action_confirm()
        return move

    def test_on_hand_counts_done_moves_only(self):
        self._move('in', 30)
        self._move('out', 12)
        self._move('in', 100, confirm=False)
        self.assertEqual(self.material.qty_on_hand, 18)

    def test_cancelled_move_does_not_count(self):
        move = self._move('in', 30, confirm=False)
        move.action_cancel()
        self.assertEqual(move.state, 'cancelled')
        self.assertEqual(self.material.qty_on_hand, 0)

    def test_issue_cannot_exceed_on_hand(self):
        self._move('in', 5)
        move = self._move('out', 6, confirm=False)
        with self.assertRaises(UserError):
            move.action_confirm()
        self.assertEqual(move.state, 'draft')
        self.assertEqual(self.material.qty_on_hand, 5)

    def test_issue_whole_stock(self):
        self._move('in', 5)
        self._move('out', 5)
        self.assertEqual(self.material.qty_on_hand, 0)

    def test_issues_checked_one_by_one(self):
        self._move('in', 10)
        first = self._move('out', 6, confirm=False)
        second = self._move('out', 6, confirm=False)
        with self.assertRaises(UserError):
            (first | second).action_confirm()

    def test_below_minimum_flag(self):
        self.assertTrue(self.material.is_below_min)
        self._move('in', 10)
        self.assertFalse(self.material.is_below_min)
        self._move('out', 1)
        self.assertTrue(self.material.is_below_min)
        below = self.env['fac.material'].search([('is_below_min', '=', True)])
        self.assertIn(self.material, below)

    def test_cannot_confirm_twice(self):
        move = self._move('in', 1)
        with self.assertRaises(UserError):
            move.action_confirm()
        with self.assertRaises(UserError):
            move.action_cancel()

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._move('in', 0, confirm=False)

    def test_move_reference_from_sequence(self):
        move = self._move('in', 1, confirm=False)
        self.assertTrue(move.name.startswith('MV/'))

    def test_code_is_unique(self):
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.env['fac.material'].create({'name': 'Duplicate', 'code': 'T-BAR'})
            self.env.flush_all()
