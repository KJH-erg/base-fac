from odoo import _, api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('draft', 'To Judge'),
    ('passed', 'Passed'),
    ('failed', 'Failed'),
]


class FacInspection(models.Model):
    _name = 'fac.inspection'
    _description = 'Quality Inspection'
    _order = 'inspection_date desc, id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    spec_id = fields.Many2one('fac.inspection.spec', string='Inspection Standard', required=True,
                              ondelete='restrict')
    characteristic = fields.Char(related='spec_id.characteristic')
    unit = fields.Char(related='spec_id.unit')
    lower_limit = fields.Float(related='spec_id.lower_limit')
    upper_limit = fields.Float(related='spec_id.upper_limit')
    # Lot and work order are plain text so this FAC stays independent of other FACs.
    lot_ref = fields.Char(string='Lot / Serial')
    workorder_ref = fields.Char(string='Work Order', help="Work order reference, e.g. WO/00001")
    measured_value = fields.Float(string='Measured Value', digits=(16, 4))
    inspector_id = fields.Many2one('res.users', string='Inspector', default=lambda self: self.env.user)
    inspection_date = fields.Datetime(string='Inspected On', default=fields.Datetime.now)
    judged_on = fields.Datetime(string='Judged On', readonly=True, copy=False)
    state = fields.Selection(STATES, string='Result', required=True, default='draft',
                             readonly=True, copy=False)
    ncr_ids = fields.One2many('fac.inspection.ncr', 'inspection_id', string='NCRs', readonly=True)
    ncr_count = fields.Integer(string='NCR Count', compute='_compute_ncr_count')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') != 'New':
                continue
            number = self.env['ir.sequence'].next_by_code('fac.inspection')
            if number:
                vals['name'] = number
        return super().create(vals_list)

    # EB: execution steps without business meaning of their own.

    @api.depends('ncr_ids')
    def _compute_ncr_count(self):
        for inspection in self:
            inspection.ncr_count = len(inspection.ncr_ids)

    def _check_state(self, allowed_states, action_label):
        """Raise if any record is not in one of allowed_states."""
        for inspection in self:
            if inspection.state not in allowed_states:
                raise UserError(_(
                    "Inspection %(name)s cannot be %(action)s while it is %(state)s.",
                    name=inspection.name, action=action_label,
                    state=dict(STATES)[inspection.state],
                ))

    def _set_state(self, new_state):
        """Write the new result."""
        self.write({'state': new_state})

    def _stamp(self, field_name):
        """Write the current time into field_name."""
        self.write({field_name: fields.Datetime.now()})

    def _clear(self, field_name):
        """Empty field_name."""
        self.write({field_name: False})

    # BM: one business rule each.

    def judge(self):
        """A measured value outside the lower/upper limit fails; inside (limits included) passes."""
        self._check_state({'draft'}, _("judged"))
        for inspection in self:
            if inspection.spec_id._is_within_limits(inspection.measured_value):
                inspection._set_state('passed')
            else:
                inspection._set_state('failed')
        self._stamp('judged_on')

    def reset_judgement(self):
        """Only a passed inspection may be measured again. Failed ones keep their NCR."""
        self._check_state({'passed'}, _("reset"))
        self._set_state('draft')
        self._clear('judged_on')

    # FA steps (inspection judgement flow): the form buttons call these.

    def action_judge(self):
        """Judge, then raise an NCR for each failed inspection (NCR handling flow)."""
        self.judge()
        self.env['fac.inspection.ncr'].raise_for(self)

    def action_reset_to_draft(self):
        """Inspection flow step: Passed -> To Judge."""
        self.reset_judgement()

    # AC part: screen navigation.

    def action_view_ncr(self):
        """Open the NCRs raised by this inspection."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Non-Conformance Reports'),
            'res_model': 'fac.inspection.ncr',
            'view_mode': 'list,form',
            'domain': [('inspection_id', '=', self.id)],
            'context': {'default_inspection_id': self.id},
        }
