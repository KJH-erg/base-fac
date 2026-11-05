from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FacInspectionSpec(models.Model):
    _name = 'fac.inspection.spec'
    _description = 'Inspection Standard'
    _order = 'code'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, copy=False)
    characteristic = fields.Char(string='Characteristic', required=True, help="What is measured, e.g. Outer Diameter")
    unit = fields.Char(string='Unit', help="e.g. mm, kg, °C")
    lower_limit = fields.Float(string='Lower Limit', required=True, digits=(16, 4))
    upper_limit = fields.Float(string='Upper Limit', required=True, digits=(16, 4))
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')

    _code_unique = models.Constraint('unique(code)', 'Inspection standard code must be unique.')

    @api.constrains('lower_limit', 'upper_limit')
    def _check_limits(self):
        for spec in self:
            if spec.lower_limit > spec.upper_limit:
                raise ValidationError(_(
                    "Lower limit must not exceed upper limit (%(code)s).", code=spec.code,
                ))

    # EB: execution step without business meaning of its own.

    def _is_within_limits(self, value):
        """Return True if value lies inside [lower_limit, upper_limit] (limits included)."""
        self.ensure_one()
        return self.lower_limit <= value <= self.upper_limit
