from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFacInspection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spec = cls.env['fac.inspection.spec'].create({
            'name': 'Test OD',
            'code': 'T-OD',
            'characteristic': 'Outer Diameter',
            'unit': 'mm',
            'lower_limit': 9.9,
            'upper_limit': 10.1,
        })

    def _inspect(self, value):
        return self.env['fac.inspection'].create({
            'spec_id': self.spec.id,
            'lot_ref': 'LOT-T',
            'workorder_ref': 'WO/T',
            'measured_value': value,
        })

    def test_within_limits_passes(self):
        inspection = self._inspect(10.0)
        inspection.action_judge()
        self.assertEqual(inspection.state, 'passed')
        self.assertTrue(inspection.judged_on)
        self.assertFalse(inspection.ncr_ids)

    def test_limits_are_inclusive(self):
        low, high = self._inspect(9.9), self._inspect(10.1)
        (low | high).action_judge()
        self.assertEqual(low.state, 'passed')
        self.assertEqual(high.state, 'passed')

    def test_above_upper_fails_and_opens_ncr(self):
        inspection = self._inspect(10.2)
        inspection.action_judge()
        self.assertEqual(inspection.state, 'failed')
        self.assertEqual(inspection.ncr_count, 1)
        ncr = inspection.ncr_ids
        self.assertEqual(ncr.state, 'open')
        self.assertTrue(ncr.name.startswith('NCR/'))
        self.assertEqual(ncr.lot_ref, 'LOT-T')
        self.assertEqual(ncr.workorder_ref, 'WO/T')

    def test_below_lower_fails(self):
        inspection = self._inspect(9.8)
        inspection.action_judge()
        self.assertEqual(inspection.state, 'failed')
        self.assertEqual(inspection.ncr_count, 1)

    def test_cannot_judge_twice(self):
        inspection = self._inspect(10.5)
        inspection.action_judge()
        with self.assertRaises(UserError):
            inspection.action_judge()
        self.assertEqual(inspection.ncr_count, 1)

    def test_only_passed_can_be_reset(self):
        passed, failed = self._inspect(10.0), self._inspect(11.0)
        (passed | failed).action_judge()
        passed.action_reset_to_draft()
        self.assertEqual(passed.state, 'draft')
        with self.assertRaises(UserError):
            failed.action_reset_to_draft()

    def test_spec_limits_order(self):
        with self.assertRaises(ValidationError):
            self.env['fac.inspection.spec'].create({
                'name': 'Bad', 'code': 'BAD', 'characteristic': 'X',
                'lower_limit': 5, 'upper_limit': 1,
            })

    def test_ncr_close_needs_disposition(self):
        inspection = self._inspect(12.0)
        inspection.action_judge()
        ncr = inspection.ncr_ids
        with self.assertRaises(UserError):
            ncr.action_close()
        ncr.disposition = 'scrap'
        ncr.action_close()
        self.assertEqual(ncr.state, 'closed')
        with self.assertRaises(UserError):
            ncr.action_close()

    def test_judge_alone_does_not_raise_ncr(self):
        inspection = self._inspect(10.5)
        inspection.judge()
        self.assertEqual(inspection.state, 'failed')
        self.assertFalse(inspection.ncr_ids)

    def test_raise_for_only_failed_and_once(self):
        passed, failed = self._inspect(10.0), self._inspect(10.5)
        (passed | failed).judge()
        ncr_model = self.env['fac.inspection.ncr']
        ncr_model.raise_for(passed | failed)
        ncr_model.raise_for(passed | failed)
        self.assertFalse(passed.ncr_ids)
        self.assertEqual(failed.ncr_count, 1)
