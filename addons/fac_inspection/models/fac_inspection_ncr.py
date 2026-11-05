from odoo import _, api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('open', 'Open'),
    ('closed', 'Closed'),
]

DISPOSITIONS = [
    ('rework', 'Rework'),
    ('scrap', 'Scrap'),
    ('use_as_is', 'Use As Is'),
    ('return', 'Return to Supplier'),
]


class FacInspectionNcr(models.Model):
    _name = 'fac.inspection.ncr'
    _description = 'Non-Conformance Report'
    _order = 'id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    inspection_id = fields.Many2one('fac.inspection', string='Inspection', required=True,
                                    ondelete='cascade', index=True)
    spec_id = fields.Many2one(related='inspection_id.spec_id', store=True)
    lot_ref = fields.Char(related='inspection_id.lot_ref', store=True)
    workorder_ref = fields.Char(related='inspection_id.workorder_ref', store=True)
    description = fields.Text(string='Description', required=True)
    disposition = fields.Selection(DISPOSITIONS, string='Disposition')
    responsible_id = fields.Many2one('res.users', string='Responsible')
    closed_on = fields.Datetime(string='Closed On', readonly=True, copy=False)
    state = fields.Selection(STATES, string='Status', required=True, default='open',
                             readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') != 'New':
                continue
            number = self.env['ir.sequence'].next_by_code('fac.inspection.ncr')
            if number:
                vals['name'] = number
        return super().create(vals_list)

    # EB: execution steps without business meaning of their own.

    @api.model
    def _create_for(self, inspection):
        """Create one NCR describing the failed measurement of inspection."""
        description = _(
            "%(char)s measured %(value)s %(unit)s, outside %(low)s - %(high)s.",
            char=inspection.characteristic, value=inspection.measured_value,
            unit=inspection.unit or '', low=inspection.lower_limit, high=inspection.upper_limit,
        )
        return self.create({'inspection_id': inspection.id, 'description': description})

    def _check_state(self, allowed_states, action_label):
        """Raise if any record is not in one of allowed_states."""
        for ncr in self:
            if ncr.state not in allowed_states:
                raise UserError(_(
                    "NCR %(name)s cannot be %(action)s while it is %(state)s.",
                    name=ncr.name, action=action_label, state=dict(STATES)[ncr.state],
                ))

    def _require_value(self, field_name, message):
        """Raise message (with %(name)s) for the first record whose field_name is empty."""
        for ncr in self:
            if not ncr[field_name]:
                raise UserError(message % {'name': ncr.name})

    def _set_state(self, new_state):
        """Write the new status."""
        self.write({'state': new_state})

    def _stamp(self, field_name):
        """Write the current time into field_name."""
        self.write({field_name: fields.Datetime.now()})

    # BM: one business rule each.

    @api.model
    def raise_for(self, inspections):
        """Each failed inspection without an NCR gets one NCR."""
        for inspection in inspections:
            if inspection.state == 'failed' and not inspection.ncr_ids:
                self._create_for(inspection)

    def close(self):
        """An open NCR is closed once a disposition is chosen; the closing time is recorded."""
        self._check_state({'open'}, _("closed"))
        self._require_value('disposition', _("Choose a disposition before closing NCR %(name)s."))
        self._set_state('closed')
        self._stamp('closed_on')

    # FA step (NCR handling flow): the form button calls this.

    def action_close(self):
        """NCR flow step: Open -> Closed."""
        self.close()
